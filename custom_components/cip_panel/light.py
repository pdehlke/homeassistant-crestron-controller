"""Lights, optionally dimmable through an analog level join."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .cipcore.joinmap import LIGHT
from .cipcore.protocol import ANALOG_MAX
from .entity import entities_of
from .onoff import OnOffEntity


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(JoinLight(entry, item) for item in entities_of(entry, LIGHT))


class JoinLight(OnOffEntity, LightEntity):
    def __init__(self, entry, item) -> None:
        super().__init__(entry, item)
        # Only a writable level makes a dimmer from Home Assistant's point of
        # view. A read-only level is still reported, as the `level` attribute,
        # because seeing it move is how a user confirms they found the right join.
        mode = ColorMode.BRIGHTNESS if item.brightness_writable else ColorMode.ONOFF
        self._attr_color_mode = mode
        self._attr_supported_color_modes = {mode}

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        attrs = super().extra_state_attributes
        # Home Assistant drops `brightness` from an on/off light's state, so a
        # read-only level would otherwise be invisible.
        if self._item.brightness_join is not None and not self._item.brightness_writable:
            attrs["level"] = self.brightness
        return attrs

    @property
    def brightness(self) -> int | None:
        if self._item.brightness_join is None:
            return None
        raw = self._hub.analog(self._item.subsystem, self._item.brightness_join)
        return None if raw is None else round(raw * 255 / ANALOG_MAX)

    async def async_turn_on(self, **kwargs: Any) -> None:
        item = self._item
        if ATTR_BRIGHTNESS in kwargs and item.brightness_writable:
            # The level alone is sent. Whether a level write also switches the
            # load on is up to the program, so this does not press the on join
            # as well: on a toggle that could switch it straight back off.
            level = round(kwargs[ATTR_BRIGHTNESS] * ANALOG_MAX / 255)
            await self._run(self._hub.async_set_analog(item, item.brightness_join, level))
            return
        await self._async_drive(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_drive(False)
