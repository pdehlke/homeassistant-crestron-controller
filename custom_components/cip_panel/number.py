"""Analog joins with a range, writable when the map says so and writes are on.

Analog writes use an encoding this project has not yet seen a processor accept;
see docs/protocol/cip-wire-format.md before relying on one.
"""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .cipcore.joinmap import NUMBER, SCALE_PERCENT
from .cipcore.protocol import ANALOG_MAX
from .entity import CipPanelEntity, entities_of


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(JoinNumber(entry, item) for item in entities_of(entry, NUMBER))


class JoinNumber(CipPanelEntity, NumberEntity):
    _attr_mode = NumberMode.SLIDER

    def __init__(self, entry, item) -> None:
        super().__init__(entry, item)
        self._attr_native_min_value = item.minimum
        self._attr_native_max_value = item.maximum
        self._attr_native_step = item.step
        self._attr_native_unit_of_measurement = item.unit or (
            "%" if item.scale == SCALE_PERCENT else None
        )

    @property
    def native_value(self) -> float | None:
        raw = self._hub.analog(self._item.subsystem, self._item.analog)
        if raw is None:
            return None
        if self._item.scale == SCALE_PERCENT:
            return round(raw * 100.0 / ANALOG_MAX, 1)
        return float(raw)

    async def async_set_native_value(self, value: float) -> None:
        if not self._item.writable:
            raise HomeAssistantError(f"{self._item.name} is read-only in the join map")
        raw = value * ANALOG_MAX / 100.0 if self._item.scale == SCALE_PERCENT else value
        await self._run(self._hub.async_set_analog(self._item, self._item.analog, round(raw)))
