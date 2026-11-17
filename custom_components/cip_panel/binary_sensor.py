"""Read-only digital joins, plus one connectivity sensor per link."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .cipcore.joinmap import BINARY_SENSOR
from .entity import CipPanelEntity, device_info, entities_of


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    entities: list[BinarySensorEntity] = [LinkSensor(entry)]
    entities += [JoinSensor(entry, item) for item in entities_of(entry, BINARY_SENSOR)]
    async_add_entities(entities)


class JoinSensor(CipPanelEntity, BinarySensorEntity):
    def __init__(self, entry, item) -> None:
        super().__init__(entry, item)
        if item.device_class:
            self._attr_device_class = BinarySensorDeviceClass(item.device_class)

    @property
    def is_on(self) -> bool | None:
        value = self._hub.digital(self._item.subsystem, self._item.join)
        return None if value is None else bool(value)


class LinkSensor(BinarySensorEntity):
    """Whether the session is registered and synced.

    Always present, even with an empty join map, so the very first thing a
    new user sees is proof that Home Assistant reached the processor.
    """

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "link"

    def __init__(self, entry) -> None:
        self._hub = entry.runtime_data.hub
        self._attr_unique_id = f"{entry.entry_id}_link"
        self._attr_device_info = device_info(entry, self._hub)

    async def async_added_to_hass(self) -> None:
        @callback
        def _changed() -> None:
            self.async_write_ha_state()

        self.async_on_remove(self._hub.subscribe_state(_changed))

    @property
    def is_on(self) -> bool:
        return self._hub.connected

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        client = self._hub.client
        return {
            "host": client.host,
            "ipid": f"0x{client.ipid:02X}",
            "writes_enabled": self._hub.writes_enabled,
            "subsystem": client.current_subsystem,
            "last_error": client.last_error,
        }
