"""Tests for the Govee BLE coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak import BleakError

from custom_components.govee_ble_lights.coordinator import GoveeBLECoordinator
from custom_components.govee_ble_lights.protocol import build_power


@pytest.fixture
def coordinator(hass):
    """Create a coordinator for testing."""
    return GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A")


def test_initial_state(coordinator):
    """Test coordinator initializes with expected defaults."""
    assert coordinator.is_on is False
    assert coordinator.brightness_pct == 100
    assert coordinator.rgb_color == (255, 255, 255)
    assert coordinator.color_temp_kelvin is None
    assert coordinator.effect is None
    assert coordinator.address == "AA:BB:CC:DD:EE:FF"
    assert coordinator.model == "H617A"


@pytest.mark.asyncio
async def test_send_command_retries_on_failure(coordinator):
    """Test that send_command retries up to 3 times."""
    mock_client = MagicMock()
    mock_client.is_connected = True
    mock_client.write_gatt_char = AsyncMock(side_effect=[BleakError("fail"), BleakError("fail"), None])

    with patch.object(coordinator, "_ensure_connected", return_value=mock_client):
        await coordinator.send_command(build_power(True))

    assert mock_client.write_gatt_char.call_count == 3


@pytest.mark.asyncio
async def test_send_command_raises_after_retries_exhausted(coordinator):
    """Test that send_command raises after 3 failed attempts."""
    mock_client = MagicMock()
    mock_client.is_connected = True
    mock_client.write_gatt_char = AsyncMock(side_effect=BleakError("fail"))

    with (
        patch.object(coordinator, "_ensure_connected", return_value=mock_client),
        pytest.raises(BleakError),
    ):
        await coordinator.send_command(build_power(True))

    assert mock_client.write_gatt_char.call_count == 3


@pytest.mark.asyncio
async def test_send_command_clears_client_on_error(coordinator):
    """Test that client is cleared after a BLE error for reconnection."""
    mock_client = MagicMock()
    mock_client.is_connected = True
    mock_client.write_gatt_char = AsyncMock(side_effect=BleakError("fail"))

    with (
        patch.object(coordinator, "_ensure_connected", return_value=mock_client),
        pytest.raises(BleakError),
    ):
        await coordinator.send_command(build_power(True))

    assert coordinator._client is None


@pytest.mark.asyncio
async def test_disconnect_cleans_up(coordinator):
    """Test disconnect clears client and timer."""
    mock_client = MagicMock()
    mock_client.is_connected = True
    mock_client.disconnect = AsyncMock()
    coordinator._client = mock_client

    mock_timer = MagicMock()
    coordinator._disconnect_timer = mock_timer

    await coordinator.disconnect()

    mock_client.disconnect.assert_called_once()
    mock_timer.cancel.assert_called_once()
    assert coordinator._client is None
    assert coordinator._disconnect_timer is None


@pytest.mark.asyncio
async def test_disconnect_handles_bleak_error(coordinator):
    """Test disconnect handles BleakError gracefully."""
    mock_client = MagicMock()
    mock_client.is_connected = True
    mock_client.disconnect = AsyncMock(side_effect=BleakError("error"))
    coordinator._client = mock_client

    await coordinator.disconnect()

    assert coordinator._client is None


@pytest.mark.asyncio
async def test_disconnect_noop_when_not_connected(coordinator):
    """Test disconnect is safe when no client exists."""
    coordinator._client = None
    coordinator._disconnect_timer = None
    await coordinator.disconnect()  # Should not raise


@pytest.mark.asyncio
async def test_async_update_data_returns_state(coordinator):
    """Test _async_update_data returns current optimistic state."""
    coordinator.is_on = True
    coordinator.brightness_pct = 75
    coordinator.rgb_color = (255, 0, 128)

    data = await coordinator._async_update_data()

    assert data["is_on"] is True
    assert data["brightness_pct"] == 75
    assert data["rgb_color"] == (255, 0, 128)
    assert data["color_temp_kelvin"] is None
    assert data["effect"] is None
