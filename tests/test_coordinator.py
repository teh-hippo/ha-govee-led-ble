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
    return GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A")


@pytest.fixture
def h6199_coordinator(hass):
    return GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199")


def test_initial_state(coordinator):
    assert coordinator.is_on is False
    assert coordinator.brightness_pct == 100
    assert coordinator.rgb_color == (255, 255, 255)
    assert coordinator.effect is None
    assert coordinator.address == "AA:BB:CC:DD:EE:FF"
    assert coordinator.model == "H617A"


def test_profile_loaded(coordinator, h6199_coordinator):
    assert coordinator.profile == MODEL_PROFILES["H617A"]
    assert not coordinator.profile.state_readable
    assert h6199_coordinator.profile == MODEL_PROFILES["H6199"]
    assert h6199_coordinator.profile.state_readable


async def test_send_command_retries(coordinator):
    client = MagicMock(is_connected=True)
    client.write_gatt_char = AsyncMock(side_effect=[BleakError("f"), BleakError("f"), None])
    with patch.object(coordinator, "_ensure_connected", return_value=client):
        await coordinator.send_command(build_power(True))
    assert client.write_gatt_char.call_count == 3


async def test_send_command_raises_after_retries(coordinator):
    client = MagicMock(is_connected=True)
    client.write_gatt_char = AsyncMock(side_effect=BleakError("fail"))
    with patch.object(coordinator, "_ensure_connected", return_value=client), pytest.raises(BleakError):
        await coordinator.send_command(build_power(True))
    assert client.write_gatt_char.call_count == 3
    assert coordinator._client is None


async def test_send_commands_sends_all(coordinator):
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    with patch.object(coordinator, "_ensure_connected", return_value=client):
        await coordinator.send_commands([build_power(True), build_power(False)])
    assert client.write_gatt_char.call_count == 2


async def test_async_update_data(coordinator):
    coordinator.is_on = True
    coordinator.brightness_pct = 75
    coordinator.rgb_color = (255, 0, 128)
    data = await coordinator._async_update_data()
    assert data == {
        "is_on": True,
        "brightness_pct": 75,
        "rgb_color": (255, 0, 128),
        "color_temp_kelvin": None,
        "effect": None,
    }


async def test_disconnect_cleans_up(coordinator):
    client = MagicMock(is_connected=True, disconnect=AsyncMock())
    coordinator._client = client
    cancel = MagicMock()
    coordinator._cancel_disconnect = cancel
    await coordinator.disconnect()
    client.disconnect.assert_called_once()
    cancel.assert_called_once()
    assert coordinator._client is None and coordinator._cancel_disconnect is None


async def test_disconnect_handles_bleak_error(coordinator):
    client = MagicMock(is_connected=True, disconnect=AsyncMock(side_effect=BleakError("e")))
    coordinator._client = client
    await coordinator.disconnect()
    assert coordinator._client is None


async def test_disconnect_noop_when_not_connected(coordinator):
    coordinator._client = None
    await coordinator.disconnect()  # Should not raise


async def test_disconnect_stops_keep_alive(h6199_coordinator):
    task = MagicMock(done=MagicMock(return_value=False), cancel=MagicMock())
    h6199_coordinator._keep_alive_task = task
    client = MagicMock(is_connected=True, disconnect=AsyncMock())
    h6199_coordinator._client = client
    await h6199_coordinator.disconnect()
    task.cancel.assert_called_once()


@pytest.mark.parametrize(
    "data,attr,expected",
    [
        (bytearray([0xAA, 0x01, 0x01, 0x00]), "is_on", True),
        (bytearray([0xAA, 0x01, 0x00, 0x00]), "is_on", False),
        (bytearray([0xAA, 0x04, 0x4B] + [0x00] * 5), "brightness_pct", 75),
    ],
)
def test_notify_callback_simple(h6199_coordinator, data, attr, expected):
    h6199_coordinator._notify_callback(None, data)
    assert getattr(h6199_coordinator, attr) == expected


def test_notify_callback_video_mode(h6199_coordinator):
    h6199_coordinator._notify_callback(None, bytearray([0xAA, 0x05, 0x00, 0x00, 0x01, 42]))
    assert h6199_coordinator.effect == "video: game"
    assert h6199_coordinator.video_full_screen is False
    assert h6199_coordinator.video_saturation == 42


def test_notify_callback_music_mode(h6199_coordinator):
    h6199_coordinator._notify_callback(None, bytearray([0xAA, 0x05, 0x13, 0x04, 66, 0x00, 0x01, 1, 2, 3]))
    assert h6199_coordinator.effect == "music: spectrum"
    assert h6199_coordinator.music_sensitivity == 66
    assert h6199_coordinator.music_color == (1, 2, 3)


def test_notify_callback_ignores_invalid(h6199_coordinator):
    h6199_coordinator.is_on = False
    h6199_coordinator._notify_callback(None, bytearray([0xAA]))  # too short
    h6199_coordinator._notify_callback(None, bytearray([0x33, 0x01, 0x01, 0x00]))  # wrong header
    assert h6199_coordinator.is_on is False


async def test_ensure_connected_raises_when_not_found(coordinator):
    with (
        patch("custom_components.govee_ble_lights.coordinator.bluetooth") as bt,
        patch("custom_components.govee_ble_lights.coordinator.asyncio.sleep", new_callable=AsyncMock),
        pytest.raises(BleakError, match="not found"),
    ):
        bt.async_ble_device_from_address.return_value = None
        await coordinator._ensure_connected()


async def test_ensure_connected_reuses_client(coordinator):
    client = MagicMock(is_connected=True)
    coordinator._client = client
    assert await coordinator._ensure_connected() is client


async def test_start_notify_for_state_readable(h6199_coordinator):
    client = MagicMock(is_connected=True, start_notify=AsyncMock(), write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    with (
        patch("custom_components.govee_ble_lights.coordinator.bluetooth") as bt,
        patch("custom_components.govee_ble_lights.coordinator.establish_connection", return_value=client),
    ):
        bt.async_ble_device_from_address.return_value = MagicMock()
        result = await h6199_coordinator._ensure_connected()
    client.start_notify.assert_called_once()
    client.write_gatt_char.assert_any_await(WRITE_UUID, build_keep_alive(), response=False)
    client.write_gatt_char.assert_any_await(WRITE_UUID, build_brightness_query(), response=False)
    client.write_gatt_char.assert_any_await(WRITE_UUID, build_color_mode_query(), response=False)
    assert result is client
    await h6199_coordinator.disconnect()


async def test_start_notify_not_called_for_write_only(coordinator):
    client = MagicMock(is_connected=True, start_notify=AsyncMock(), disconnect=AsyncMock())
    with (
        patch("custom_components.govee_ble_lights.coordinator.bluetooth") as bt,
        patch("custom_components.govee_ble_lights.coordinator.establish_connection", return_value=client),
    ):
        bt.async_ble_device_from_address.return_value = MagicMock()
        await coordinator._ensure_connected()
    client.start_notify.assert_not_called()
    await coordinator.disconnect()


async def test_start_notify_handles_bleak_error(h6199_coordinator):
    client = MagicMock(is_connected=True, start_notify=AsyncMock(side_effect=BleakError("fail")))
    h6199_coordinator._client = client
    await h6199_coordinator._start_notify()  # Should not raise


async def test_stop_keep_alive_noop(h6199_coordinator):
    h6199_coordinator._keep_alive_task = None
    h6199_coordinator._stop_keep_alive()  # Should not raise


async def test_keep_alive_exits_on_disconnect(h6199_coordinator):
    h6199_coordinator._client = MagicMock(is_connected=False)
    await h6199_coordinator._keep_alive_loop()


async def test_send_state_queries_no_client(h6199_coordinator):
    h6199_coordinator._client = None
    assert await h6199_coordinator._send_state_queries() is False


async def test_refresh_state_non_readable(coordinator):
    assert await coordinator.refresh_state() is False


async def test_send_keep_alive_no_client(h6199_coordinator):
    h6199_coordinator._client = None
    assert await h6199_coordinator._send_keep_alive_only() is False


async def test_reset_disconnect_timer_cancels_previous(coordinator):
    cancel = MagicMock()
    coordinator._cancel_disconnect = cancel
    coordinator._client = MagicMock(is_connected=True)
    coordinator._reset_disconnect_timer()
    cancel.assert_called_once()
    assert coordinator._cancel_disconnect is not cancel
