"""Stable frontend route contract for per-device configuration."""

from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http.server import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN

EDITOR_PANEL_PATH = "ha-govee-led-ble"
EDITOR_ROUTE_SEGMENT = "editor"
EDITOR_ELEMENT_NAME = "ha-govee-led-ble-editor"
EDITOR_STATIC_URL = f"/{DOMAIN}_static"
EDITOR_MODULE_URL = f"{EDITOR_STATIC_URL}/editor.js"
_EDITOR_STATIC_PATH = Path(__file__).parent / "frontend"


def editor_url(config_entry_id: str) -> str:
    """Return the canonical internal editor URL for a config entry."""
    return f"homeassistant://{EDITOR_PANEL_PATH}/{EDITOR_ROUTE_SEGMENT}/{config_entry_id}"


async def async_register_editor_panel(hass: HomeAssistant) -> None:
    """Register the stable hidden panel served by the device configuration link."""
    await hass.http.async_register_static_paths(
        [StaticPathConfig(EDITOR_STATIC_URL, str(_EDITOR_STATIC_PATH), cache_headers=False)]
    )
    if frontend.async_panel_exists(hass, EDITOR_PANEL_PATH):
        return
    frontend.async_register_built_in_panel(
        hass,
        component_name="custom",
        frontend_url_path=EDITOR_PANEL_PATH,
        config={
            "configuration_path": f"/config/integrations/integration/{DOMAIN}",
            "_panel_custom": {
                "name": EDITOR_ELEMENT_NAME,
                "module_url": EDITOR_MODULE_URL,
                "embed_iframe": False,
                "trust_external": False,
            },
        },
        require_admin=True,
        show_in_sidebar=False,
    )
