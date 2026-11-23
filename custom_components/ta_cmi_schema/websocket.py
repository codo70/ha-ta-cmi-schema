"""Websocket commands for the schema view (sidebar dashboard and card)."""

from __future__ import annotations

import base64
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import entity_registry as er

from .api import CMIError
from .const import DOMAIN
from .coordinator import CMISchemaCoordinator
from .parser import file_name

# classes of the C.M.I. page that the view needs (everything else is dropped)
_SAFE_CLASS = frozenset(
    {"changex2", "buttonx2", "taster", "durchsichtig", "bord", "hide", "visibleerror", "init", "can_busy"}
)


@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_pages)
    websocket_api.async_register_command(hass, ws_page)
    websocket_api.async_register_command(hass, ws_file)
    websocket_api.async_register_command(hass, ws_press)


def _coordinator(hass: HomeAssistant, entry_id: str | None) -> CMISchemaCoordinator:
    coordinators: dict[str, CMISchemaCoordinator] = hass.data.get(DOMAIN, {})
    if entry_id:
        if entry_id not in coordinators:
            raise CMIError("Unknown C.M.I.")
        return coordinators[entry_id]
    if not coordinators:
        raise CMIError("No C.M.I. set up")
    return next(iter(coordinators.values()))


def _page_names(coordinator: CMISchemaCoordinator) -> list[dict[str, Any]]:
    return [
        {"page": int(page), "name": info.get("device") or f"Seite {page}"}
        for page, info in sorted(
            coordinator.discovery["pages"].items(), key=lambda item: int(item[0])
        )
    ]


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/pages"})
@callback
def ws_pages(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """All set up C.M.I. with their schema pages."""
    connection.send_result(
        msg["id"],
        [
            {
                "entry_id": entry_id,
                "title": coordinator.config_entry.title,
                "pages": _page_names(coordinator),
            }
            for entry_id, coordinator in hass.data.get(DOMAIN, {}).items()
        ],
    )


def _entity_lookup(
    hass: HomeAssistant, coordinator: CMISchemaCoordinator, page: int
) -> tuple[dict[str, str], dict[str, str]]:
    """Entity ids of this page: by position and by short address."""
    registry = er.async_get(hass)
    entry_id = coordinator.config_entry.entry_id
    by_pos: dict[str, str] = {}
    by_address: dict[str, str] = {}
    for param in coordinator.discovery["params"]:
        entity_id = registry.async_get_entity_id(
            param["kind"], DOMAIN, f"{entry_id}_{param['key']}"
        )
        if entity_id is None:
            continue
        if param.get("address"):
            # a value shown on several pages has its entity on the first one
            by_address[param["address"]] = entity_id
        if param["page"] == page:
            by_pos[param["pos"]] = entity_id
    return by_pos, by_address


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/page",
        vol.Optional("entry_id"): str,
        vol.Required("page"): vol.All(vol.Coerce(int), vol.Range(min=1, max=999)),
        vol.Optional("fresh", default=False): bool,
    }
)
@websocket_api.async_response
async def ws_page(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Layout and current content of one schema page."""
    try:
        coordinator = _coordinator(hass, msg.get("entry_id"))
        page = msg["page"]
        layout = await coordinator.async_page_layout(page)
        values = await coordinator.async_page_values(page, max_age=0 if msg["fresh"] else 5)
    except (CMIError, ConfigEntryAuthFailed) as err:
        connection.send_error(msg["id"], "cmi_error", str(err))
        return

    by_pos, by_address = _entity_lookup(hass, coordinator, page)
    elements = []
    for pos, el in values.items():
        text = el.text
        if {"visibleerror", "init", "can_busy"} & set(el.classes):
            text = el.changefrom or ""  # the C.M.I. page shows this attribute instead
        if el.is_taster:
            action = "taster"
        elif el.is_button:
            action = "press"
        elif el.link_page is not None:
            action = "link"
        else:
            action = None
        elements.append(
            {
                "pos": pos,
                "cls": [
                    c for c in el.classes if c in _SAFE_CLASS or c.startswith("visible")
                ],
                "visible": el.visible_state,
                "text": text,
                "spans": el.spans,
                "imgs": el.images,
                "link": el.link_page,
                "action": action,
                "entity": by_pos.get(pos)
                or (by_address.get(el.address) if el.address else None),
            }
        )
    name = coordinator.discovery["pages"].get(str(page), {}).get("device")
    connection.send_result(
        msg["id"],
        {
            "entry_id": coordinator.config_entry.entry_id,
            "page": page,
            "name": name or layout.title or f"Seite {page}",
            "width": layout.width or 1440,
            "height": layout.height or 816,
            "background": layout.background,
            "image": layout.image,
            "refresh": layout.refresh,
            "css": layout.css,
            "elements": elements,
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/file",
        vol.Optional("entry_id"): str,
        vol.Required("name"): str,
    }
)
@websocket_api.async_response
async def ws_file(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """A picture of the schema as base64 (the C.M.I. itself needs a login)."""
    name = file_name(msg["name"])
    if name is None:
        connection.send_error(msg["id"], "invalid_name", "Invalid file name")
        return
    try:
        coordinator = _coordinator(hass, msg.get("entry_id"))
        data, content_type = await coordinator.async_file(name)
    except (CMIError, ConfigEntryAuthFailed) as err:
        connection.send_error(msg["id"], "cmi_error", str(err))
        return
    if not content_type.startswith("image/"):
        content_type = "image/svg+xml" if name.lower().endswith(".svg") else "image/png"
    connection.send_result(
        msg["id"], {"mime": content_type, "data": base64.b64encode(data).decode("ascii")}
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/press",
        vol.Optional("entry_id"): str,
        vol.Required("page"): vol.All(vol.Coerce(int), vol.Range(min=1, max=999)),
        vol.Required("pos"): vol.Match(r"^pos\d+$"),
        vol.Optional("value"): vol.In([0, 1]),
    }
)
@websocket_api.async_response
async def ws_press(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Click on a button of the schema (on/off button or push button)."""
    try:
        coordinator = _coordinator(hass, msg.get("entry_id"))
        await coordinator.async_press(msg["page"], msg["pos"], msg.get("value"))
    except (CMIError, ConfigEntryAuthFailed) as err:
        connection.send_error(msg["id"], "cmi_error", str(err))
        return
    connection.send_result(msg["id"], {})
