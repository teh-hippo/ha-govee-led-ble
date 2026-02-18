"""Tests for integration setup and unload lifecycle."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.govee_ble_lights import async_setup_entry, async_unload_entry
from custom_components.govee_ble_lights.const import CONF_MODEL, DOMAIN


def _make_config_entry(hass: HomeAssistant) -> MagicMock:
    """Create a mock ConfigEntry wired into hass."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.unique_id = "AA:BB:CC:DD:EE:FF"
    entry.data = {CONF_MODEL: "H617A"}
    entry.domain = DOMAIN
    entry.state = ConfigEntryState.LOADED
    entry.runtime_data = None
    return entry


async def test_setup_entry_creates_coordinator(hass: HomeAssistant):
    """Test async_setup_entry creates a coordinator and stores it in runtime_data."""
    entry = _make_config_entry(hass)

    with (
        patch(
            "custom_components.govee_ble_lights.GoveeBLECoordinator",
            autospec=True,
        ) as mock_cls,
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            new_callable=AsyncMock,
        ) as mock_fwd,
    ):
        coordinator = mock_cls.return_value
        coordinator.async_config_entry_first_refresh = AsyncMock()

        result = await async_setup_entry(hass, entry)

    assert result is True
    mock_cls.assert_called_once_with(hass, "AA:BB:CC:DD:EE:FF", "H617A")
    coordinator.async_config_entry_first_refresh.assert_awaited_once()
    assert entry.runtime_data is coordinator
    mock_fwd.assert_awaited_once()


async def test_setup_entry_defaults_model_to_h617a(hass: HomeAssistant):
    """Test that missing model key defaults to H617A."""
    entry = _make_config_entry(hass)
    entry.data = {}  # no CONF_MODEL

    with (
        patch(
            "custom_components.govee_ble_lights.GoveeBLECoordinator",
            autospec=True,
        ) as mock_cls,
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            new_callable=AsyncMock,
        ),
    ):
        mock_cls.return_value.async_config_entry_first_refresh = AsyncMock()
        await async_setup_entry(hass, entry)

    mock_cls.assert_called_once_with(hass, "AA:BB:CC:DD:EE:FF", "H617A")


async def test_unload_entry_disconnects(hass: HomeAssistant):
    """Test async_unload_entry disconnects the coordinator on success."""
    entry = _make_config_entry(hass)
    coordinator = MagicMock()
    coordinator.disconnect = AsyncMock()
    entry.runtime_data = coordinator

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        new_callable=AsyncMock,
        return_value=True,
    ):
        result = await async_unload_entry(hass, entry)

    assert result is True
    coordinator.disconnect.assert_awaited_once()


async def test_unload_entry_skips_disconnect_on_failure(hass: HomeAssistant):
    """Test async_unload_entry does NOT disconnect when unload fails."""
    entry = _make_config_entry(hass)
    coordinator = MagicMock()
    coordinator.disconnect = AsyncMock()
    entry.runtime_data = coordinator

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        new_callable=AsyncMock,
        return_value=False,
    ):
        result = await async_unload_entry(hass, entry)

    assert result is False
    coordinator.disconnect.assert_not_awaited()
