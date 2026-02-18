"""Tests for the Govee BLE coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak import BleakError

from custom_components.govee_ble_lights.const import MODEL_PROFILES
from custom_components.govee_ble_lights.coordinator import GoveeBLECoordinator
from custom_components.govee_ble_lights.protocol import (
    WRITE_UUID,
    build_brightness_query,
    build_color_mode_query,
    build_keep_alive,
    build_power,
)


@pytest.fixture
def coordinator(hass):
    """Create an H617A coordinator (write-only, no state reading)."""
    return GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A")


@pytest.fixture
def h6199_coordinator(hass):
    """Create an H6199 coordinator (state-readable, video/music modes)."""
    return GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199")


def test_initial_state(coordinator):
    """Test coordinator initializes with expected defaults."""
    assert coordinator.is_on is False
    assert coordinator.brightness_pct == 100
    assert coordinator.rgb_color == (255, 255, 255)
    assert coordinator.color_temp_kelvin is None
    assert coordinator.effect is None
    assert coordinator.address == "AA:BB:CC:DD:EE:FF"
    assert coordinator.model == "H617A"


def test_profile_loaded(coordinator, h6199_coordinator):
    """Test model profile is loaded from registry."""
    assert coordinator.profile == MODEL_PROFILES["H617A"]
    assert coordinator.profile.state_readable is False
    assert h6199_coordinator.profile == MODEL_PROFILES["H6199"]
    assert h6199_coordinator.profile.state_readable is True


async def test_send_command_retries_on_failure(coordinator):
    """Test that send_command retries up to 3 times."""
    mock_client = MagicMock()
    mock_client.is_connected = True
    mock_client.write_gatt_char = AsyncMock(side_effect=[BleakError("fail"), BleakError("fail"), None])

    with patch.object(coordinator, "_ensure_connected", return_value=mock_client):
        await coordinator.send_command(build_power(True))

    assert mock_client.write_gatt_char.call_count == 3


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


async def test_disconnect_cleans_up(coordinator):
    """Test disconnect clears client and timer."""
    mock_client = MagicMock()
    mock_client.is_connected = True
    mock_client.disconnect = AsyncMock()
    coordinator._client = mock_client

    mock_cancel = MagicMock()
    coordinator._cancel_disconnect = mock_cancel

    await coordinator.disconnect()

    mock_client.disconnect.assert_called_once()
    mock_cancel.assert_called_once()
    assert coordinator._client is None
    assert coordinator._cancel_disconnect is None


async def test_disconnect_handles_bleak_error(coordinator):
    """Test disconnect handles BleakError gracefully."""
    mock_client = MagicMock()
    mock_client.is_connected = True
    mock_client.disconnect = AsyncMock(side_effect=BleakError("error"))
    coordinator._client = mock_client

    await coordinator.disconnect()

    assert coordinator._client is None


async def test_disconnect_noop_when_not_connected(coordinator):
    """Test disconnect is safe when no client exists."""
    coordinator._client = None
    coordinator._disconnect_timer = None
    await coordinator.disconnect()  # Should not raise


async def test_send_commands_sends_all_packets(coordinator):
    """Test send_commands sends every packet in sequence."""
    mock_client = MagicMock()
    mock_client.is_connected = True
    mock_client.write_gatt_char = AsyncMock()

    with patch.object(coordinator, "_ensure_connected", return_value=mock_client):
        packets = [build_power(True), build_power(False)]
        await coordinator.send_commands(packets)

    assert mock_client.write_gatt_char.call_count == 2


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


# --- Notify / state reading tests (H6199) ---


def test_notify_callback_power_on(h6199_coordinator):
    """Test notify callback parses power-on response."""
    # 0xAA 0x01 0x01 = power on
    data = bytearray([0xAA, 0x01, 0x01, 0x00])
    h6199_coordinator._notify_callback(None, data)
    assert h6199_coordinator.is_on is True


def test_notify_callback_power_off(h6199_coordinator):
    """Test notify callback parses power-off response."""
    data = bytearray([0xAA, 0x01, 0x00, 0x00])
    h6199_coordinator._notify_callback(None, data)
    assert h6199_coordinator.is_on is False


def test_notify_callback_brightness(h6199_coordinator):
    """Test notify callback parses brightness response."""
    data = bytearray([0xAA, 0x04, 0x4B] + [0x00] * 5)  # 75%
    h6199_coordinator._notify_callback(None, data)
    assert h6199_coordinator.brightness_pct == 75


def test_notify_callback_video_mode(h6199_coordinator):
    """Test notify callback parses video mode response."""
    # mode=video, full_screen=0(part), game_mode=1, saturation=42
    data = bytearray([0xAA, 0x05, 0x00, 0x00, 0x01, 42])
    h6199_coordinator._notify_callback(None, data)
    assert h6199_coordinator.effect == "video: game"
    assert h6199_coordinator.video_full_screen is False
    assert h6199_coordinator.video_saturation == 42


def test_notify_callback_music_mode(h6199_coordinator):
    """Test notify callback parses music mode response."""
    # mode=music, mode_id=spectrum(0x04), sensitivity=66, has_color=1, rgb=(1,2,3)
    data = bytearray([0xAA, 0x05, 0x13, 0x04, 66, 0x00, 0x01, 1, 2, 3])
    h6199_coordinator._notify_callback(None, data)
    assert h6199_coordinator.effect == "music: spectrum"
    assert h6199_coordinator.music_sensitivity == 66
    assert h6199_coordinator.music_color == (1, 2, 3)


def test_notify_callback_ignores_short_data(h6199_coordinator):
    """Test notify callback ignores packets shorter than 3 bytes."""
    h6199_coordinator.is_on = False
    h6199_coordinator._notify_callback(None, bytearray([0xAA]))
    assert h6199_coordinator.is_on is False  # unchanged


def test_notify_callback_ignores_non_status_header(h6199_coordinator):
    """Test notify callback ignores packets with non-0xAA header."""
    h6199_coordinator.is_on = False
    data = bytearray([0x33, 0x01, 0x01, 0x00])
    h6199_coordinator._notify_callback(None, data)
    assert h6199_coordinator.is_on is False  # unchanged


async def test_start_notify_called_for_state_readable(h6199_coordinator):
    """Test that _start_notify is called when connecting state_readable device."""
    mock_client = MagicMock()
    mock_client.is_connected = True
    mock_client.start_notify = AsyncMock()
    mock_client.write_gatt_char = AsyncMock()
    mock_client.disconnect = AsyncMock()

    mock_ble_device = MagicMock()
    with (
        patch("custom_components.govee_ble_lights.coordinator.bluetooth") as mock_bt,
        patch("custom_components.govee_ble_lights.coordinator.establish_connection", return_value=mock_client),
    ):
        mock_bt.async_ble_device_from_address.return_value = mock_ble_device
        client = await h6199_coordinator._ensure_connected()

    mock_client.start_notify.assert_called_once()
    mock_client.write_gatt_char.assert_any_await(WRITE_UUID, build_keep_alive(), response=False)
    mock_client.write_gatt_char.assert_any_await(WRITE_UUID, build_brightness_query(), response=False)
    mock_client.write_gatt_char.assert_any_await(WRITE_UUID, build_color_mode_query(), response=False)
    assert client is mock_client
    await h6199_coordinator.disconnect()


async def test_start_notify_not_called_for_write_only(coordinator):
    """Test that _start_notify is NOT called for write-only H617A."""
    mock_client = MagicMock()
    mock_client.is_connected = True
    mock_client.start_notify = AsyncMock()
    mock_client.disconnect = AsyncMock()

    mock_ble_device = MagicMock()
    with (
        patch("custom_components.govee_ble_lights.coordinator.bluetooth") as mock_bt,
        patch("custom_components.govee_ble_lights.coordinator.establish_connection", return_value=mock_client),
    ):
        mock_bt.async_ble_device_from_address.return_value = mock_ble_device
        await coordinator._ensure_connected()

    mock_client.start_notify.assert_not_called()
    await coordinator.disconnect()


async def test_disconnect_stops_keep_alive(h6199_coordinator):
    """Test that disconnect stops the keep-alive task."""
    mock_task = MagicMock()
    mock_task.done.return_value = False
    mock_task.cancel = MagicMock()
    h6199_coordinator._keep_alive_task = mock_task

    mock_client = MagicMock()
    mock_client.is_connected = True
    mock_client.disconnect = AsyncMock()
    h6199_coordinator._client = mock_client

    await h6199_coordinator.disconnect()

    mock_task.cancel.assert_called_once()


async def test_stop_keep_alive_noop_when_no_task(h6199_coordinator):
    """Test _stop_keep_alive is safe when no task exists."""
    h6199_coordinator._keep_alive_task = None
    h6199_coordinator._stop_keep_alive()  # Should not raise


async def test_start_notify_handles_bleak_error(h6199_coordinator):
    """Test that _start_notify handles BleakError gracefully."""
    mock_client = MagicMock()
    mock_client.is_connected = True
    mock_client.start_notify = AsyncMock(side_effect=BleakError("fail"))
    h6199_coordinator._client = mock_client

    await h6199_coordinator._start_notify()  # Should not raise


# --- Edge-case tests (T5) ---


async def test_ensure_connected_raises_when_device_not_found(coordinator):
    """Test _ensure_connected raises BleakError after discovery retries."""
    with (
        patch("custom_components.govee_ble_lights.coordinator.bluetooth") as mock_bt,
        patch("custom_components.govee_ble_lights.coordinator.asyncio.sleep", new_callable=AsyncMock),
        pytest.raises(BleakError, match="not found"),
    ):
        mock_bt.async_ble_device_from_address.return_value = None
        await coordinator._ensure_connected()


async def test_ensure_connected_reuses_existing_client(coordinator):
    """Test _ensure_connected returns existing client without reconnecting."""
    mock_client = MagicMock()
    mock_client.is_connected = True
    coordinator._client = mock_client

    result = await coordinator._ensure_connected()

    assert result is mock_client


async def test_keep_alive_loop_exits_on_disconnected_client(h6199_coordinator):
    """Test keep-alive loop exits when client disconnects."""
    mock_client = MagicMock()
    mock_client.is_connected = False
    h6199_coordinator._client = mock_client

    await h6199_coordinator._keep_alive_loop()  # Should exit without error


async def test_send_state_queries_returns_false_when_no_client(h6199_coordinator):
    """Test _send_state_queries returns False when no client."""
    h6199_coordinator._client = None
    result = await h6199_coordinator._send_state_queries()
    assert result is False


async def test_refresh_state_returns_false_for_non_state_readable(coordinator):
    """Test refresh_state returns False for write-only models."""
    result = await coordinator.refresh_state()
    assert result is False


async def test_send_keep_alive_only_returns_false_when_no_client(h6199_coordinator):
    """Test _send_keep_alive_only returns False with no client."""
    h6199_coordinator._client = None
    result = await h6199_coordinator._send_keep_alive_only()
    assert result is False


async def test_reset_disconnect_timer_cancels_previous(coordinator):
    """Test that resetting disconnect timer cancels the previous one."""
    mock_cancel = MagicMock()
    coordinator._cancel_disconnect = mock_cancel

    mock_client = MagicMock()
    mock_client.is_connected = True
    coordinator._client = mock_client

    coordinator._reset_disconnect_timer()

    mock_cancel.assert_called_once()
    assert coordinator._cancel_disconnect is not None
    assert coordinator._cancel_disconnect is not mock_cancel
