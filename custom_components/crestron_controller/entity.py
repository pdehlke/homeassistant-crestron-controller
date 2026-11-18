"""Shared plumbing for every entity built from a join map entry."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .cipcore.joinmap import Entity as MapEntity
from .const import DOMAIN
from .hub import Hub, HubError


def device_info(entry: ConfigEntry, hub: Hub) -> DeviceInfo:
    """One device per processor link, named after the config entry."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="Crestron (via CIP panel emulation)",
        model=f"Panel slot IP-ID 0x{hub.client.ipid:02X}",
        configuration_url=None,
    )


def entities_of(entry: ConfigEntry, kind: str) -> list[MapEntity]:
    return [e for e in entry.runtime_data.hub.joinmap.entities if e.type == kind]


class CrestronControllerEntity(Entity):
    """Pushed, never polled: redraws whenever a join it reads changes."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, item: MapEntity) -> None:
        self._hub: Hub = entry.runtime_data.hub
        self._item = item
        self._attr_unique_id = f"{entry.entry_id}_{item.id}"
        self._attr_name = item.name
        self._attr_device_info = device_info(entry, self._hub)
        if item.icon:
            self._attr_icon = item.icon

    async def async_added_to_hass(self) -> None:
        @callback
        def _changed() -> None:
            self.async_write_ha_state()

        self.async_on_remove(
            self._hub.subscribe(self._item.reads(), _changed, self._item.smart_object or 0)
        )

    @property
    def available(self) -> bool:
        return self._hub.available(self._item)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        attrs: dict[str, object] = {"joins_read": [f"{k}:{j}" for k, j in self._item.reads()]}
        if self._item.subsystem is not None:
            attrs["subsystem"] = self._item.subsystem
        if self._item.smart_object is not None:
            attrs["smart_object"] = self._item.smart_object
        return attrs

    async def _run(self, coro) -> None:
        """Await a hub command, turning its failure into a message the UI shows."""
        try:
            await coro
        except HubError as err:
            raise HomeAssistantError(str(err)) from err
