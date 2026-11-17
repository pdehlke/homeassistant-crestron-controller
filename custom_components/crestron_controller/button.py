"""Momentary presses: scenes, macros, anything that is a press and nothing else."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .cipcore.joinmap import BUTTON
from .entity import CrestronControllerEntity, entities_of


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(JoinButton(entry, item) for item in entities_of(entry, BUTTON))


class JoinButton(CrestronControllerEntity, ButtonEntity):
    @property
    def available(self) -> bool:
        # A button has nothing to read, so it is available whenever the link is.
        return self._hub.connected

    async def async_press(self) -> None:
        await self._run(self._hub.async_press(self._item, self._item.join, self._item.hold_seconds))
