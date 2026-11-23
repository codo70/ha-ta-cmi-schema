"""Editable numeric values (setpoints, differences, ...)."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import CMISchemaEntity, params_of_kind
from .parser import KIND_NUMBER, decimals_for_step, parse_number


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        CMISchemaNumber(coordinator, p) for p in params_of_kind(coordinator, KIND_NUMBER)
    )


class CMISchemaNumber(CMISchemaEntity, NumberEntity):
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, param) -> None:
        super().__init__(coordinator, param)
        if param.get("min") is not None:
            self._attr_native_min_value = param["min"]
        if param.get("max") is not None:
            self._attr_native_max_value = param["max"]
        self._attr_native_step = param.get("step") or 1.0
        self._decimals = decimals_for_step(self._attr_native_step)
        unit = param.get("unit")
        if unit == "°C":
            self._attr_device_class = NumberDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        else:
            self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self) -> float | None:
        if (el := self.element) is None:
            return None
        number = parse_number(el.split_label()[1])
        return number.value if number else None

    async def async_set_native_value(self, value: float) -> None:
        await self._write(f"{value:.{self._decimals}f}")
