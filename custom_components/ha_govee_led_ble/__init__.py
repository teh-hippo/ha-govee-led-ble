"""HA Govee LED BLE integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_MODEL
from .coordinator import GoveeBLECoordinator

_LOGGER = logging.getLogger(__name__)
type GoveeBLEConfigEntry = ConfigEntry[GoveeBLECoordinator]
PLATFORMS = [Platform.LIGHT, Platform.NUMBER, Platform.SELECT, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: GoveeBLEConfigEntry) -> bool:
    assert entry.unique_id is not None
    coordinator = GoveeBLECoordinator(hass, entry.unique_id, entry.data.get(CONF_MODEL, "H617A"))
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GoveeBLEConfigEntry) -> bool:
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.disconnect()
    return unload_ok
