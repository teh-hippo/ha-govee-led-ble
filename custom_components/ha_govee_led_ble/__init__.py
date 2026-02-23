"""HA Govee LED BLE integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import CONF_MODEL
from .coordinator import GoveeBLECoordinator

type GoveeBLEConfigEntry = ConfigEntry[GoveeBLECoordinator]
PLATFORMS = [Platform.LIGHT, Platform.NUMBER, Platform.SELECT, Platform.SWITCH]
_LEGACY_ENTITY_SUFFIXES = {"_video_brightness", "_white_brightness"}


async def _async_cleanup_legacy_entities(hass: HomeAssistant, entry: GoveeBLEConfigEntry) -> None:
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.unique_id and any(entity.unique_id.endswith(suffix) for suffix in _LEGACY_ENTITY_SUFFIXES):
            registry.async_remove(entity.entity_id)


async def async_setup_entry(hass: HomeAssistant, entry: GoveeBLEConfigEntry) -> bool:
    assert entry.unique_id is not None
    coordinator = GoveeBLECoordinator(hass, entry.unique_id, entry.data.get(CONF_MODEL, "H617A"))
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await _async_cleanup_legacy_entities(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GoveeBLEConfigEntry) -> bool:
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.disconnect()
    return unload_ok
