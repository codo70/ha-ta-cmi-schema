"""Editable clock times (time programs, switching times)."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import CMISchemaEntity, params_of_kind
from .parser import KIND_TIME, parse_time_minutes

# The controller knows 24:00 (= end of day); Home Assistant does not.
END_OF_DAY = time(23, 59, 59)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        CMISchemaTime(coordinator, p) for p in params_of_kind(coordinator, KIND_TIME)
    )


class CMISchemaTime(CMISchemaEntity, TimeEntity):
    @property
    def native_value(self) -> time | None:
        if (el := self.element) is None:
            return None
        minutes = parse_time_minutes(el.split_label()[1])
        if minutes is None:
            return None
        if minutes >= 1440:
            return END_OF_DAY
        return time(minutes // 60, minutes % 60)

    async def async_set_value(self, value: time) -> None:
        minutes = 1440 if value == END_OF_DAY else value.hour * 60 + value.minute
        await self._write(minutes)
