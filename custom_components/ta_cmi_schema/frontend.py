"""Schema view in the Home Assistant frontend: Lovelace card and sidebar dashboard."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN, PANEL_ICON, PANEL_TITLE, PANEL_URL

_LOGGER = logging.getLogger(__name__)

STATIC_URL = f"/{DOMAIN}_static"
SCRIPT = "ta-cmi-schema.js"
_DATA = f"{DOMAIN}_frontend"


async def _script_url(hass: HomeAssistant) -> str:
    integration = await async_get_integration(hass, DOMAIN)
    # version in the URL so browsers load the new script after an update
    return f"{STATIC_URL}/{SCRIPT}?v={integration.version}"


async def async_setup_frontend(hass: HomeAssistant) -> None:
    """Serve the script and make the card available on every dashboard (once)."""
    data = hass.data.setdefault(_DATA, {"panel": False})
    if data.get("static"):
        return
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "www"), False)]
    )
    url = await _script_url(hass)
    frontend.add_extra_js_url(hass, url)
    data["static"] = True
    data["url"] = url


async def async_register_panel(hass: HomeAssistant) -> None:
    """Sidebar entry "T.A. Schema" with one tab per schema page."""
    data = hass.data.setdefault(_DATA, {"panel": False})
    if data.get("panel"):
        return
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL,
        webcomponent_name="ta-cmi-schema-panel",
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        module_url=data.get("url") or await _script_url(hass),
        require_admin=False,
    )
    data["panel"] = True


def async_remove_panel(hass: HomeAssistant) -> None:
    data = hass.data.get(_DATA, {})
    if not data.get("panel"):
        return
    frontend.async_remove_panel(hass, PANEL_URL)
    data["panel"] = False
