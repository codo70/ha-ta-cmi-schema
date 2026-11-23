"""Status pictures of the schema (pumps, valves, "Heizen", "STOPP", ...)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import KIND_BINARY_SENSOR
from .entity import CMISchemaEntity, params_of_kind
from .parser import parse_on_off


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        CMISchemaBinarySensor(coordinator, p)
        for p in params_of_kind(coordinator, KIND_BINARY_SENSOR)
    )


class CMISchemaBinarySensor(CMISchemaEntity, BinarySensorEntity):
    # like the read-only sensors: many pages show a lot of them
    _attr_entity_registry_enabled_default = False

    @property
    def is_on(self) -> bool | None:
        if (el := self.element) is None:
            return None
        if not el.is_lamp:
            return parse_on_off(el.split_label()[1])  # "Pumpe: ON"
        state = el.visible_state
        if state is None or state < 0:
            return None
        return state >= 1
