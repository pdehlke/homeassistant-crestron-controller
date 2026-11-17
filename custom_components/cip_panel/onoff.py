"""What lights and switches share: the three press modes.

Toggle and on_off entities read their state from feedback and are driven to a
discrete state by the hub. Momentary entities have no feedback at all, so their
state is whatever Home Assistant last asked for, and they say so through
assumed_state, which makes the frontend show separate on and off buttons
rather than a switch that pretends to know. See docs/configuration/press-modes.md.
"""

from __future__ import annotations

from homeassistant.helpers.restore_state import RestoreEntity

from .cipcore.joinmap import PRESS_MOMENTARY
from .entity import CipPanelEntity


class OnOffEntity(CipPanelEntity, RestoreEntity):
    def __init__(self, entry, item) -> None:
        super().__init__(entry, item)
        self._assumed_on: bool | None = None
        self._attr_assumed_state = item.press == PRESS_MOMENTARY

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._attr_assumed_state and (last := await self.async_get_last_state()):
            self._assumed_on = last.state == "on"

    @property
    def is_on(self) -> bool | None:
        if self._attr_assumed_state:
            return self._assumed_on
        return self._hub.is_on(self._item)

    async def _async_drive(self, want_on: bool) -> None:
        item = self._item
        if self._attr_assumed_state:
            await self._run(self._hub.async_press(item, item.press_for(want_on)))
            self._assumed_on = want_on
            self.async_write_ha_state()
        else:
            await self._run(self._hub.async_set(item, want_on))
