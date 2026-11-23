"""Button to re-read the schema structure after it was changed in TA Designer."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([CMIRediscoverButton(entry, coordinator.client.base_url)])


class CMIRediscoverButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "rediscover"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: ConfigEntry, url: str) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_rediscover"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Technische Alternative",
            model="C.M.I.",
            configuration_url=url,
        )

    async def async_press(self) -> None:
        await self.hass.services.async_call(
            DOMAIN, "rediscover", {"config_entry_id": self._entry.entry_id}
        )
