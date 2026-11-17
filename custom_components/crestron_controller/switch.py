"""Switches: a light that is not a light, or any on/off thing behind a button."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .cipcore.joinmap import SWITCH
from .entity import entities_of
from .onoff import OnOffEntity


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(JoinSwitch(entry, item) for item in entities_of(entry, SWITCH))


class JoinSwitch(OnOffEntity, SwitchEntity):
    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_drive(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_drive(False)
