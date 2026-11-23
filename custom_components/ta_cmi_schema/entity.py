"""Base entity for the T.A. C.M.I. Schema integration."""

from __future__ import annotations

from typing import Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import CMIError
from .const import DOMAIN
from .coordinator import CMISchemaCoordinator
from .parser import SchemaElement

_VIA_DEVICE_ID = "via_device_id" in DeviceInfo.__annotations__


class CMISchemaEntity(CoordinatorEntity[CMISchemaCoordinator]):
    """One value of a C.M.I. schema page."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: CMISchemaCoordinator, param: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self.param = param
        entry = coordinator.config_entry
        page = str(param["page"])
        page_info = coordinator.discovery["pages"].get(page, {})
        self._attr_unique_id = f"{entry.entry_id}_{param['key']}"
        self._attr_name = param["name"]
        device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_page_{page}")},
            name=page_info.get("device") or f"Seite {page}",
            manufacturer="Technische Alternative",
            model="C.M.I. Schema",
            configuration_url=f"{coordinator.client.base_url}/schema.html#{page}",
        )
        # newer Home Assistant versions want the device id, older ones the identifier
        if _VIA_DEVICE_ID and coordinator.hub_device_id:
            device_info["via_device_id"] = coordinator.hub_device_id
        else:
            device_info["via_device"] = (DOMAIN, entry.entry_id)
        self._attr_device_info = device_info

    @property
    def element(self) -> SchemaElement | None:
        return self.coordinator.element(self.param)

    @property
    def available(self) -> bool:
        return super().available and self.element is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {"page": self.param["page"], "position": self.param["pos"]}
        if self.param.get("address"):
            attrs["short_address"] = self.param["address"]
        return attrs

    async def _write(self, value: str | int | float) -> None:
        try:
            await self.coordinator.client.write(self.param["address"], value)
        except CMIError as err:
            raise HomeAssistantError(f"C.M.I. write failed: {err}") from err
        await self.coordinator.async_refresh_page(self.param["page"])


def params_of_kind(coordinator: CMISchemaCoordinator, kind: str) -> list[dict[str, Any]]:
    return [p for p in coordinator.discovery["params"] if p["kind"] == kind]
