"""Tests for integration setup and unload lifecycle."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.govee_ble_lights import async_setup_entry, async_unload_entry
from custom_components.govee_ble_lights.const import CONF_MODEL, DOMAIN


def _make_entry():
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.unique_id = "AA:BB:CC:DD:EE:FF"
    entry.data = {CONF_MODEL: "H617A"}
    entry.domain = DOMAIN
    entry.state = ConfigEntryState.LOADED
    entry.runtime_data = None
    return entry


async def test_setup_entry(hass: HomeAssistant):
    entry = _make_entry()
    with (
        patch("custom_components.govee_ble_lights.GoveeBLECoordinator", autospec=True) as cls,
        patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock) as fwd,
    ):
        cls.return_value.async_config_entry_first_refresh = AsyncMock()
        assert await async_setup_entry(hass, entry) is True
    cls.assert_called_once_with(hass, "AA:BB:CC:DD:EE:FF", "H617A")
    assert entry.runtime_data is cls.return_value
    fwd.assert_awaited_once()


async def test_setup_entry_defaults_model(hass: HomeAssistant):
    entry = _make_entry()
    entry.data = {}
    with (
        patch("custom_components.govee_ble_lights.GoveeBLECoordinator", autospec=True) as cls,
        patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock),
    ):
        cls.return_value.async_config_entry_first_refresh = AsyncMock()
        await async_setup_entry(hass, entry)
    cls.assert_called_once_with(hass, "AA:BB:CC:DD:EE:FF", "H617A")


async def test_unload_entry_disconnects(hass: HomeAssistant):
    entry = _make_entry()
    entry.runtime_data = MagicMock(disconnect=AsyncMock())
    with patch.object(hass.config_entries, "async_unload_platforms", new_callable=AsyncMock, return_value=True):
        assert await async_unload_entry(hass, entry) is True
    entry.runtime_data.disconnect.assert_awaited_once()


async def test_unload_entry_skips_disconnect_on_failure(hass: HomeAssistant):
    entry = _make_entry()
    entry.runtime_data = MagicMock(disconnect=AsyncMock())
    with patch.object(hass.config_entries, "async_unload_platforms", new_callable=AsyncMock, return_value=False):
        assert await async_unload_entry(hass, entry) is False
    entry.runtime_data.disconnect.assert_not_awaited()
