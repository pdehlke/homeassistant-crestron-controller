"""UI setup for one processor link, and the options that switch writes on.

The flow asks for the four things a novice can find out (see
docs/getting-started/finding-your-control-processor.md), creates a starter join
map if there is none yet, and registers once to prove the address and IP-ID
before saving anything. Registering presses nothing.
"""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import callback

from . import join_map_path, load_join_map
from .cipcore import client as cip
from .cipcore.joinmap import JoinMapError
from .cipcore.protocol import CIP_PORT
from .const import (
    CONF_ALLOW_WRITES,
    CONF_IPID,
    CONF_JOIN_MAP,
    DEFAULT_JOIN_MAP_DIR,
    DOMAIN,
    STARTER_JOIN_MAP,
)

PROBE_ERRORS = {
    cip.ERROR_UNREACHABLE: "cannot_connect",
    cip.ERROR_IPID_MISSING: "ipid_missing",
    cip.ERROR_REFUSED: "refused",
    cip.ERROR_DISPLACED: "refused",
    cip.ERROR_CLOSED: "refused",
}


def parse_ipid(text: str) -> int:
    """Accept '0x2A', '2A' (read as hex, the way Crestron writes IP-IDs) or '42d'."""
    value = text.strip().lower()
    if value.endswith("d") and value[:-1].isdigit():
        number = int(value[:-1])
    elif re.fullmatch(r"(0x)?[0-9a-f]{1,2}", value):
        number = int(value.removeprefix("0x"), 16)
    else:
        raise ValueError(text)
    if not 0x03 <= number <= 0xFE:
        raise ValueError(text)
    return number


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "processor"


def _ensure_join_map(path) -> bool:
    """Create the starter join map if none exists. Returns True if it created one."""
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(STARTER_JOIN_MAP, encoding="utf-8")
    return True


class CrestronControllerConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        defaults = user_input or {}
        if user_input is not None:
            try:
                ipid = parse_ipid(user_input[CONF_IPID])
            except ValueError:
                errors[CONF_IPID] = "invalid_ipid"
            else:
                host = user_input[CONF_HOST].strip()
                await self.async_set_unique_id(f"{host}:{ipid:02x}")
                self._abort_if_unique_id_configured()

                relative = user_input.get(CONF_JOIN_MAP) or (
                    f"{DEFAULT_JOIN_MAP_DIR}/{_slug(user_input[CONF_NAME])}.yaml"
                )
                path = join_map_path(self.hass, relative)
                try:
                    await self.hass.async_add_executor_job(_ensure_join_map, path)
                    await self.hass.async_add_executor_job(load_join_map, path)
                except (JoinMapError, OSError) as err:
                    errors[CONF_JOIN_MAP] = "invalid_join_map"
                    placeholders["detail"] = str(err)

                if not errors:
                    result = await cip.async_probe(host, ipid, user_input[CONF_PORT])
                    if result != cip.PROBE_OK:
                        errors["base"] = PROBE_ERRORS.get(result, "refused")

                if not errors:
                    return self.async_create_entry(
                        title=user_input[CONF_NAME],
                        data={
                            CONF_NAME: user_input[CONF_NAME],
                            CONF_HOST: host,
                            CONF_PORT: user_input[CONF_PORT],
                            CONF_IPID: ipid,
                            CONF_JOIN_MAP: relative,
                        },
                        options={CONF_ALLOW_WRITES: False},
                    )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, "Crestron")): str,
                vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
                vol.Required(CONF_IPID, default=defaults.get(CONF_IPID, "")): str,
                vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, CIP_PORT)): int,
                vol.Optional(CONF_JOIN_MAP, default=defaults.get(CONF_JOIN_MAP, "")): str,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders=placeholders or {"detail": ""},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the address, port or IP-ID without losing entities or their history.

        Exists because a processor on an unreserved DHCP lease can move overnight,
        and deleting and re-adding the entry would orphan every entity id and
        automation built on it. See docs/case-study/post-mortem-dhcp-address-change.md.
        """
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        current = {
            CONF_HOST: entry.data[CONF_HOST],
            CONF_PORT: entry.data[CONF_PORT],
            CONF_IPID: f"0x{entry.data[CONF_IPID]:02X}",
        }
        if user_input is not None:
            current = user_input
            try:
                ipid = parse_ipid(user_input[CONF_IPID])
            except ValueError:
                errors[CONF_IPID] = "invalid_ipid"
            else:
                host = user_input[CONF_HOST].strip()
                unique_id = f"{host}:{ipid:02x}"
                taken = any(
                    other.unique_id == unique_id and other.entry_id != entry.entry_id
                    for other in self._async_current_entries(include_ignore=False)
                )
                if taken:
                    return self.async_abort(reason="already_configured")
                result = await cip.async_probe(host, ipid, user_input[CONF_PORT])
                if result != cip.PROBE_OK:
                    errors["base"] = PROBE_ERRORS.get(result, "refused")
                else:
                    return self.async_update_reload_and_abort(
                        entry,
                        unique_id=unique_id,
                        data_updates={
                            CONF_HOST: host,
                            CONF_PORT: user_input[CONF_PORT],
                            CONF_IPID: ipid,
                        },
                    )
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=current[CONF_HOST]): str,
                vol.Required(CONF_IPID, default=current[CONF_IPID]): str,
                vol.Required(CONF_PORT, default=current[CONF_PORT]): int,
            }
        )
        return self.async_show_form(step_id="reconfigure", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return CrestronControllerOptionsFlow()


class CrestronControllerOptionsFlow(OptionsFlow):
    """Writes are off until the user turns them on here, on purpose."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_ALLOW_WRITES, False)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({vol.Required(CONF_ALLOW_WRITES, default=current): bool}),
        )
