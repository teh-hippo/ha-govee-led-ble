"""HA Govee LED BLE integration."""

from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .const import CONF_MODEL, DOMAIN
from .coordinator import GoveeBLECoordinator
from .coordinator_effects import build_effect_store

type GoveeBLEConfigEntry = ConfigEntry[GoveeBLECoordinator]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = [
    Platform.IMAGE,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
]
_LEGACY_ENTITY_SUFFIXES = {
    "_video_brightness",
    "_white_brightness",
    "_video_saturation",
    "_video_sound_effects",
    "_video_sound_effects_softness",
    "_music_calm",
    "_music_mode",
}
# The 2.x experimental options flag, removed in 3.0.0; stripped from migrated entries.
_LEGACY_EXPERIMENTAL_OPTION = "experimental"
_CARD_URL = "/ha_govee_led_ble/govee-led-ble-card.js"
_CARD_FILE = Path(__file__).parent / "www" / "govee-led-ble-card.js"
_CARD_REGISTERED = "card_registered"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    data = hass.data.setdefault(DOMAIN, {})
    if data.get(_CARD_REGISTERED) or not _CARD_FILE.is_file():
        return True
    await hass.http.async_register_static_paths([StaticPathConfig(_CARD_URL, str(_CARD_FILE), False)])
    integration = await async_get_integration(hass, DOMAIN)
    frontend.add_extra_js_url(hass, f"{_CARD_URL}?v={integration.version}")
    data[_CARD_REGISTERED] = True
    return True


async def _async_cleanup_legacy_entities(hass: HomeAssistant, entry: GoveeBLEConfigEntry) -> None:
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.unique_id and any(entity.unique_id.endswith(suffix) for suffix in _LEGACY_ENTITY_SUFFIXES):
            registry.async_remove(entity.entity_id)


def _addr(entry: GoveeBLEConfigEntry) -> str:
    assert entry.unique_id is not None
    return entry.unique_id.replace(":", "").lower()


async def async_migrate_entry(hass: HomeAssistant, entry: GoveeBLEConfigEntry) -> bool:
    if entry.version < 2:
        options = {k: v for k, v in entry.options.items() if k != _LEGACY_EXPERIMENTAL_OPTION}
        # Capture the old switch.music_calm id now; select.music_style is registered only after setup.
        old_id = er.async_get(hass).async_get_entity_id("switch", DOMAIN, f"{_addr(entry)}_music_calm")
        if old_id:
            hass.data.setdefault(DOMAIN, {})[f"{entry.entry_id}_music_calm_from"] = old_id
        hass.config_entries.async_update_entry(entry, options=options, version=2)
    return True


def _maybe_flag_music_calm_replaced(hass: HomeAssistant, entry: GoveeBLEConfigEntry) -> None:
    """Warn migrated entries that switch.music_calm is now select.music_style (both ids resolved)."""
    old_id = hass.data.get(DOMAIN, {}).pop(f"{entry.entry_id}_music_calm_from", None)
    if old_id is None:
        return
    new_id = er.async_get(hass).async_get_entity_id("select", DOMAIN, f"{_addr(entry)}_music_style")
    ir.async_create_issue(
        hass,
        DOMAIN,
        "music_calm_replaced",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="music_calm_replaced",
        translation_placeholders={"old": old_id, "new": new_id or "select.music_style"},
    )


def _maybe_flag_music_mode_replaced(hass: HomeAssistant, entry: GoveeBLEConfigEntry) -> None:
    """Warn that select.music_mode is gone: music is now chosen from the light effect list."""
    old_id = er.async_get(hass).async_get_entity_id("select", DOMAIN, f"{_addr(entry)}_music_mode")
    if old_id is None:
        return
    ir.async_create_issue(
        hass,
        DOMAIN,
        "music_mode_replaced",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="music_mode_replaced",
        translation_placeholders={"old": old_id},
    )


async def async_setup_entry(hass: HomeAssistant, entry: GoveeBLEConfigEntry) -> bool:
    assert entry.unique_id is not None
    coordinator = GoveeBLECoordinator(hass, entry.unique_id, entry.data.get(CONF_MODEL, "H617A"))
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    coordinator.attach_effect_store(build_effect_store(hass, entry.entry_id))
    await coordinator.async_load_effects()
    _maybe_flag_music_mode_replaced(hass, entry)
    await _async_cleanup_legacy_entities(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _maybe_flag_music_calm_replaced(hass, entry)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GoveeBLEConfigEntry) -> bool:
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.disconnect()
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: GoveeBLEConfigEntry) -> None:
    await build_effect_store(hass, entry.entry_id).async_remove()
