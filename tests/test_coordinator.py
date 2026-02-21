from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak import BleakError

from custom_components.ha_govee_led_ble import protocol as proto
from custom_components.ha_govee_led_ble.const import MODEL_PROFILES
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator

M = "custom_components.ha_govee_led_ble.coordinator"


@pytest.fixture
def coord(hass):
    return GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A")


@pytest.fixture
def h6199(hass):
    return GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199")


def _c(**kw):
    return MagicMock(is_connected=True, **kw)


async def test_initial_state_and_update(coord, h6199):
    assert (coord.is_on, coord.brightness_pct, coord.rgb_color) == (False, 100, (255, 255, 255))
    assert coord.effect is None and coord.address == "AA:BB:CC:DD:EE:FF" and coord.model == "H617A"
    assert coord.profile == MODEL_PROFILES["H617A"] and not coord.profile.state_readable
    assert h6199.profile == MODEL_PROFILES["H6199"] and h6199.profile.state_readable
    coord.is_on, coord.brightness_pct, coord.rgb_color = True, 75, (255, 0, 128)
    exp = {"is_on": True, "brightness_pct": 75, "rgb_color": (255, 0, 128), "color_temp_kelvin": None, "effect": None}
    assert await coord._async_update_data() == exp


async def test_send_command(coord):
    c = _c(write_gatt_char=AsyncMock(side_effect=[BleakError("f"), BleakError("f"), None]))
    with patch.object(coord, "_ensure_connected", return_value=c):
        await coord.send_command(proto.build_power(True))
    assert c.write_gatt_char.call_count == 3
    c2 = _c(write_gatt_char=AsyncMock(side_effect=BleakError("f")))
    with patch.object(coord, "_ensure_connected", return_value=c2), pytest.raises(BleakError):
        await coord.send_command(proto.build_power(True))
    assert c2.write_gatt_char.call_count == 3 and coord._client is None


async def test_disconnect(coord, h6199):
    c = _c(disconnect=AsyncMock())
    coord._client, coord._cancel_disconnect = c, (cancel := MagicMock())
    await coord.disconnect()
    c.disconnect.assert_called_once()
    cancel.assert_called_once()
    assert coord._client is None and coord._cancel_disconnect is None
    coord._client = _c(disconnect=AsyncMock(side_effect=BleakError("e")))
    await coord.disconnect()
    assert coord._client is None
    coord._client = None
    await coord.disconnect()
    task = MagicMock(done=MagicMock(return_value=False), cancel=MagicMock())
    h6199._keep_alive_task, h6199._client = task, _c(disconnect=AsyncMock())
    await h6199.disconnect()
    task.cancel.assert_called_once()


def test_notify_callback(h6199):
    cb = h6199._notify_callback
    cb(None, bytearray([0xAA, 0x01, 0x01, 0x00]))
    assert h6199.is_on is True
    cb(None, bytearray([0xAA, 0x01, 0x00, 0x00]))
    assert h6199.is_on is False
    cb(None, bytearray([0xAA, 0x04, 0x4B] + [0x00] * 5))
    assert h6199.brightness_pct == 75
    cb(None, bytearray([0xAA, 0x05, 0x00, 0x00, 0x01, 42]))
    assert (h6199.effect, h6199.video_full_screen, h6199.video_saturation) == ("video: game", False, 42)
    cb(None, bytearray([0xAA, 0x05, 0x13, 0x04, 66, 0x00, 0x01, 1, 2, 3]))
    assert (h6199.effect, h6199.music_sensitivity, h6199.music_color) == ("music: spectrum", 66, (1, 2, 3))
    h6199.is_on = False
    cb(None, bytearray([0xAA]))
    cb(None, bytearray([0x33, 0x01, 0x01, 0x00]))
    assert h6199.is_on is False


async def test_ensure_connected(coord):
    coord._client = (c := _c())
    assert await coord._ensure_connected() is c
    coord._client = None
    with (
        patch(f"{M}.bluetooth") as bt,
        patch(f"{M}.asyncio.sleep", new_callable=AsyncMock),
        pytest.raises(BleakError, match="not found"),
    ):
        bt.async_ble_device_from_address.return_value = None
        await coord._ensure_connected()


async def test_start_notify(coord, h6199):
    c = _c(start_notify=AsyncMock(), write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    with patch(f"{M}.bluetooth") as bt, patch(f"{M}.establish_connection", return_value=c):
        bt.async_ble_device_from_address.return_value = MagicMock()
        assert await h6199._ensure_connected() is c
    c.start_notify.assert_called_once()
    for q in (proto.KEEP_ALIVE, proto.BRIGHTNESS_QUERY, proto.COLOR_MODE_QUERY):
        c.write_gatt_char.assert_any_await(proto.WRITE_UUID, q, response=False)
    await h6199.disconnect()
    c2 = _c(start_notify=AsyncMock(), disconnect=AsyncMock())
    with patch(f"{M}.bluetooth") as bt, patch(f"{M}.establish_connection", return_value=c2):
        bt.async_ble_device_from_address.return_value = MagicMock()
        await coord._ensure_connected()
    c2.start_notify.assert_not_called()
    await coord.disconnect()
    h6199._client = _c(start_notify=AsyncMock(side_effect=BleakError("fail")))
    await h6199._start_notify()


async def test_misc_helpers(coord, h6199):
    h6199._keep_alive_task = None
    h6199._stop_keep_alive()
    h6199._client = MagicMock(is_connected=False)
    await h6199._keep_alive_loop()
    h6199._client = None
    assert await h6199._send_state_queries() is False
    assert await coord.refresh_state() is False
    coord._cancel_disconnect = (cancel := MagicMock())
    coord._client = _c()
    coord._reset_disconnect_timer()
    cancel.assert_called_once()
    assert coord._cancel_disconnect is not cancel
