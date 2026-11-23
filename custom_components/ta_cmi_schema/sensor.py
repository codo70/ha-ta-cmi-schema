"""Read-only values shown on the schema pages (disabled by default)."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import KIND_SENSOR
from .entity import CMISchemaEntity, params_of_kind
from .parser import parse_number

_UNITS = {
    "°C": (SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS),
    "W": (SensorDeviceClass.POWER, UnitOfPower.WATT),
    "kW": (SensorDeviceClass.POWER, UnitOfPower.KILO_WATT),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        CMISchemaSensor(coordinator, p) for p in params_of_kind(coordinator, KIND_SENSOR)
    )


class CMISchemaSensor(CMISchemaEntity, SensorEntity):
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator, param) -> None:
        super().__init__(coordinator, param)
        unit = param.get("unit")
        if unit in _UNITS:
            self._attr_device_class, self._attr_native_unit_of_measurement = _UNITS[unit]
        else:
            self._attr_native_unit_of_measurement = unit
        if unit not in ("kWh", "MWh", "Wh"):
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        if (el := self.element) is None:
            return None
        number = parse_number(el.split_label()[1])
        if number is None or abs(number.value) >= 9999:
            return None  # 9999.9 = sensor not connected
        return number.value
