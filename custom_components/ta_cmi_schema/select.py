"""Editable selections (operating modes, ...)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import CMISchemaEntity, params_of_kind
from .parser import KIND_SELECT


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        CMISchemaSelect(coordinator, p) for p in params_of_kind(coordinator, KIND_SELECT)
    )


class CMISchemaSelect(CMISchemaEntity, SelectEntity):
    def __init__(self, coordinator, param) -> None:
        super().__init__(coordinator, param)
        self._values = {label: value for value, label in param["options"]}
        self._attr_options = list(self._values)

    @property
    def current_option(self) -> str | None:
        if (el := self.element) is None:
            return None
        text = el.split_label()[1]
        if text in self._values:
            return text
        # the schema may show a shortened text, e.g. "Standby" for "Standby/Frostschutz"
        for label in self._attr_options:
            if label.startswith(text) or text.startswith(label):
                return label
        return None

    async def async_select_option(self, option: str) -> None:
        if option not in self._values:
            raise HomeAssistantError(f"Unknown option {option}")
        await self._write(self._values[option])
