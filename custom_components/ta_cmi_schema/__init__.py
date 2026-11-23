"""TA C.M.I. Schema - read and write every value of a C.M.I. schema page."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import CMIClient, CMIError
from .const import (
    ATTR_ENTRY_ID,
    ATTR_SHORT_ADDRESS,
    ATTR_VALUE,
    DOMAIN,
    PLATFORMS,
    SERVICE_REDISCOVER,
    SERVICE_WRITE_VALUE,
)
from .coordinator import CMISchemaCoordinator

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

WRITE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Required(ATTR_SHORT_ADDRESS): cv.string,
        vol.Required(ATTR_VALUE): vol.Any(cv.string, vol.Coerce(float)),
    }
)
REDISCOVER_SCHEMA = vol.Schema({vol.Optional(ATTR_ENTRY_ID): cv.string})


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    hass.data.setdefault(DOMAIN, {})

    def _coordinator(call: ServiceCall) -> CMISchemaCoordinator:
        coordinators: dict[str, CMISchemaCoordinator] = hass.data[DOMAIN]
        if entry_id := call.data.get(ATTR_ENTRY_ID):
            if entry_id not in coordinators:
                raise HomeAssistantError(f"Unknown config entry {entry_id}")
            return coordinators[entry_id]
        if len(coordinators) != 1:
            raise HomeAssistantError("Please specify config_entry_id")
        return next(iter(coordinators.values()))

    async def write_value(call: ServiceCall) -> None:
        coordinator = _coordinator(call)
        try:
            await coordinator.client.write(call.data[ATTR_SHORT_ADDRESS], call.data[ATTR_VALUE])
        except CMIError as err:
            raise HomeAssistantError(f"C.M.I. write failed: {err}") from err
        await coordinator.async_request_refresh()

    async def rediscover(call: ServiceCall) -> None:
        coordinator = _coordinator(call)
        entry = coordinator.config_entry

        async def _run() -> None:
            try:
                await coordinator.async_load_discovery(force=True)
            except CMIError as err:
                _LOGGER.error("Re-reading the C.M.I. schema failed: %s", err)
                return
            hass.config_entries.async_schedule_reload(entry.entry_id)

        # crawling all pages takes a while - do not block the caller
        entry.async_create_background_task(hass, _run(), f"{DOMAIN}_rediscover")

    hass.services.async_register(DOMAIN, SERVICE_WRITE_VALUE, write_value, schema=WRITE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REDISCOVER, rediscover, schema=REDISCOVER_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = CMIClient(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    coordinator = CMISchemaCoordinator(hass, entry, client)
    try:
        await coordinator.async_load_discovery()
    except CMIError as err:
        raise ConfigEntryNotReady(f"C.M.I. not reachable: {err}") from err

    hub = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="Technische Alternative",
        model="C.M.I.",
        configuration_url=client.base_url,
    )
    coordinator.hub_device_id = hub.id

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # reading all pages takes a few seconds - do it in the background so the
    # Home Assistant start is not delayed (entities are unavailable until then)
    entry.async_create_background_task(
        hass, coordinator.async_refresh(), f"{DOMAIN}_first_refresh"
    )
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    coordinator: CMISchemaCoordinator = hass.data[DOMAIN][entry.entry_id]
    # page selection / sensor option changed -> crawl again
    await coordinator.async_load_discovery(force=True)
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
