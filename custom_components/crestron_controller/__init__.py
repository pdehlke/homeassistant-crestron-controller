"""Crestron Controller: impersonate a Crestron touch panel from Home Assistant.

One config entry is one processor link: a host, the IP-ID of a panel slot the
program defines, and a join map file under /config that says which joins are
which entities. Editing the join map takes effect on a reload of the entry, so
no restart is needed.

Not affiliated with or endorsed by Crestron Electronics.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass
from pathlib import Path

import yaml
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import issue_registry as ir

from .cipcore import client as cip
from .cipcore.joinmap import JoinMap, JoinMapError, parse
from .const import (
    CONF_ALLOW_WRITES,
    CONF_FINGERPRINT,
    CONF_IPID,
    CONF_JOIN_MAP,
    CONF_LEGACY_TLS,
    CONF_TLS,
    DISPLACEMENT_REPAIR_COUNT,
    DOMAIN,
    HEALTH_CHECK_INTERVAL,
    UNREACHABLE_REPAIR_SECONDS,
)
from .hub import Hub

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]


@dataclass
class RuntimeData:
    hub: Hub
    health_task: asyncio.Task


type CrestronControllerConfigEntry = ConfigEntry[RuntimeData]


def join_map_path(hass: HomeAssistant, relative: str) -> Path:
    """Resolve a join map path the user typed, relative to the config directory."""
    return Path(hass.config.path(relative))


def load_join_map(path: Path) -> JoinMap:
    """Read and validate one join map. Blocking; run in the executor."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as err:
        raise JoinMapError(f"join map {path} does not exist") from err
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as err:
        raise JoinMapError(f"join map {path} is not valid YAML: {err}") from err
    return parse(raw)


async def async_setup_entry(hass: HomeAssistant, entry: CrestronControllerConfigEntry) -> bool:
    path = join_map_path(hass, entry.data[CONF_JOIN_MAP])
    try:
        joinmap = await hass.async_add_executor_job(load_join_map, path)
    except JoinMapError as err:
        # ConfigEntryError rather than NotReady: retrying will not fix a typo,
        # and the message lands on the integration card where the user looks.
        raise ConfigEntryError(str(err)) from err

    hub = Hub(
        name=entry.data[CONF_NAME],
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        ipid=entry.data[CONF_IPID],
        joinmap=joinmap,
        writes_enabled=entry.options.get(CONF_ALLOW_WRITES, False),
        # Entries created before TLS support have neither key and stay plain.
        tls=entry.data.get(CONF_TLS, False),
        legacy_tls=entry.data.get(CONF_LEGACY_TLS, False),
        pinned_fingerprint=entry.data.get(CONF_FINGERPRINT),
    )
    await hub.async_start()
    health = entry.async_create_background_task(
        hass, _watch_health(hass, entry, hub), name=f"{DOMAIN}-health-{entry.entry_id}"
    )
    entry.runtime_data = RuntimeData(hub, health)
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CrestronControllerConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        data = entry.runtime_data
        data.health_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await data.health_task
        await data.hub.async_stop()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: CrestronControllerConfigEntry) -> None:
    for issue in _ISSUES:
        ir.async_delete_issue(hass, DOMAIN, _issue_id(entry, issue))


async def _options_updated(hass: HomeAssistant, entry: CrestronControllerConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


# ---- link health -------------------------------------------------------------

ISSUE_UNREACHABLE = "unreachable"
ISSUE_IPID_MISSING = "ipid_missing"
ISSUE_REFUSED = "refused"
ISSUE_DISPLACED = "displaced"
ISSUE_CERT_CHANGED = "cert_changed"
_ISSUES = (
    ISSUE_UNREACHABLE,
    ISSUE_IPID_MISSING,
    ISSUE_REFUSED,
    ISSUE_DISPLACED,
    ISSUE_CERT_CHANGED,
)


def _issue_id(entry: ConfigEntry, issue: str) -> str:
    return f"{entry.entry_id}_{issue}"


def evaluate_health(hub: Hub, now: float) -> set[str]:
    """Which repairs should be open for this link right now.

    Pure so it can be tested without a running Home Assistant. A link that
    retries a dead address forever and surfaces nothing a person would see is
    the failure this exists to prevent: see
    docs/case-study/post-mortem-dhcp-address-change.md.
    """
    client = hub.client
    issues: set[str] = set()
    if client.recent_displacements() >= DISPLACEMENT_REPAIR_COUNT:
        issues.add(ISSUE_DISPLACED)
    if hub.connected:
        return issues
    kind = client.last_error_kind
    if kind == cip.ERROR_IPID_MISSING:
        issues.add(ISSUE_IPID_MISSING)
    elif kind == cip.ERROR_REFUSED:
        issues.add(ISSUE_REFUSED)
    elif kind == cip.ERROR_CERT_CHANGED:
        issues.add(ISSUE_CERT_CHANGED)
    since = client.disconnected_since
    if since is not None and now - since >= UNREACHABLE_REPAIR_SECONDS:
        issues.add(ISSUE_UNREACHABLE)
    return issues


async def _watch_health(hass: HomeAssistant, entry: ConfigEntry, hub: Hub) -> None:
    open_issues: set[str] = set()
    while True:
        await asyncio.sleep(HEALTH_CHECK_INTERVAL)
        wanted = evaluate_health(hub, time.monotonic())
        for issue in wanted - open_issues:
            ir.async_create_issue(
                hass,
                DOMAIN,
                _issue_id(entry, issue),
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key=issue,
                translation_placeholders={
                    "name": hub.name,
                    "host": hub.client.host,
                    "ipid": f"0x{hub.client.ipid:02X}",
                    "error": hub.client.last_error or "none recorded",
                },
            )
        for issue in open_issues - wanted:
            ir.async_delete_issue(hass, DOMAIN, _issue_id(entry, issue))
        open_issues = wanted
