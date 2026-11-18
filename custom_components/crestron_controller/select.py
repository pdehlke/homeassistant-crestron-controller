"""Choosing one of several options, such as a source from a panel's list."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .cipcore.joinmap import SELECT
from .entity import CrestronControllerEntity, entities_of


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(JoinSelect(entry, item) for item in entities_of(entry, SELECT))


class JoinSelect(CrestronControllerEntity, SelectEntity):
    @property
    def options(self) -> list[str]:
        # Read on every redraw: a label can come from a serial the processor
        # sends after setup, or changes later.
        return self._hub.option_labels(self._item)

    @property
    def current_option(self) -> str | None:
        chosen = self._hub.selected(self._item)
        if chosen is None:
            return None
        return self.options[self._item.options.index(chosen)]

    async def async_select_option(self, option: str) -> None:
        try:
            index = self.options.index(option)
        except ValueError as err:
            raise HomeAssistantError(f"{self._item.name}: no option called {option!r}") from err
        await self._run(self._hub.async_select(self._item, self._item.options[index]))
