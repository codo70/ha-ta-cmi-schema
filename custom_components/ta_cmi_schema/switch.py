"""On/off buttons of the schema (e.g. weekdays of a time program)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import CMIError
from .const import DOMAIN
from .coordinator import KIND_SWITCH
from .entity import CMISchemaEntity, params_of_kind


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        CMISchemaSwitch(coordinator, p) for p in params_of_kind(coordinator, KIND_SWITCH)
    )


class CMISchemaSwitch(CMISchemaEntity, SwitchEntity):
    # no entity category: weekdays belong next to the switching times

    @property
    def available(self) -> bool:
        el = self.element
        return super().available and el is not None and el.visible_state in (0, 1)

    @property
    def is_on(self) -> bool | None:
        if (el := self.element) is None:
            return None
        return el.visible_state == 1

    async def _set(self, on: bool) -> None:
        el = self.element
        if el is None or not el.address:
            raise HomeAssistantError("Button not available")
        try:
            # buttons carry their write address directly in the page
            await self.coordinator.client.change(el.address, 1 if on else 0)
        except CMIError as err:
            raise HomeAssistantError(f"C.M.I. write failed: {err}") from err
        await self.coordinator.async_refresh_page(self.param["page"])

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
