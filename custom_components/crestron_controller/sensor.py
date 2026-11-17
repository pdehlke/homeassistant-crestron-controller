"""Read-only analog and serial joins."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .cipcore.joinmap import SCALE_PERCENT, SENSOR
from .cipcore.protocol import ANALOG_MAX
from .entity import CrestronControllerEntity, entities_of


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(JoinValueSensor(entry, item) for item in entities_of(entry, SENSOR))


class JoinValueSensor(CrestronControllerEntity, SensorEntity):
    def __init__(self, entry, item) -> None:
        super().__init__(entry, item)
        if item.analog is not None:
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_native_unit_of_measurement = item.unit or (
                "%" if item.scale == SCALE_PERCENT else None
            )
        if item.device_class:
            self._attr_device_class = SensorDeviceClass(item.device_class)

    @property
    def available(self) -> bool:
        if self._item.serial is not None:
            return self._hub.connected
        return super().available

    @property
    def native_value(self) -> float | int | str | None:
        item = self._item
        if item.serial is not None:
            return self._hub.serial(item.serial)
        raw = self._hub.analog(item.subsystem, item.analog)
        if raw is None:
            return None
        if item.scale == SCALE_PERCENT:
            return round(raw * 100.0 / ANALOG_MAX, 1)
        return raw
