import time
from dataclasses import replace
from datetime import time as dtime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak import BleakError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.ha_govee_led_ble import protocol as proto
from custom_components.ha_govee_led_ble.const import DOMAIN, MODEL_PROFILES
from custom_components.ha_govee_led_ble.coordinator import IDENTITY_RETRY_TICKS, GoveeBLECoordinator

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
    assert (coord.music_mode, coord.video_mode, coord.active_custom_id) == ("off", "off", None)
    assert coord.profile == MODEL_PROFILES["H617A"] and coord.profile.state_readable
    assert (
        coord.profile.supports_music_mode
        and coord.profile.supports_music_style
        and not coord.profile.supports_video_mode
    )
    assert h6199.profile == MODEL_PROFILES["H6199"] and h6199.profile.state_readable
    assert (
        h6199.profile.supports_video_mode
        and h6199.profile.supports_white_brightness
        and not h6199.profile.supports_music_style
    )
    coord.is_on, coord.brightness_pct, coord.rgb_color = True, 75, (255, 0, 128)
    exp = {"is_on": True, "brightness_pct": 75, "rgb_color": (255, 0, 128), "color_temp_kelvin": None, "effect": None}
    with (
        patch.object(coord, "_ensure_connected", new_callable=AsyncMock),
        patch.object(coord, "_send_state_queries", new_callable=AsyncMock),
    ):
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
    assert (h6199.video_mode, h6199.video_full_screen, h6199.video_saturation) == ("game", False, 42)
    cb(None, bytearray([0xAA, 0x05, 0x13, 0x04, 66, 0x00, 0x01, 1, 2, 3]))
    assert (h6199.music_mode, h6199.music_sensitivity, h6199.music_calm, h6199.music_color) == (
        "spectrum",
        66,
        False,
        (1, 2, 3),
    )
    assert h6199.effect is None
    cb(None, bytearray([0xAA, 0x05, 0x04, 0x9D, 0x08]))
    assert h6199.effect == "candy"
    h6199.is_on = False
    cb(None, bytearray([0xAA]))
    cb(None, bytearray([0x33, 0x01, 0x01, 0x00]))
    assert h6199.is_on is False


def test_notify_callback_parses_full_frame_with_checksum(h6199):
    cb = h6199._notify_callback
    cb(None, bytearray(proto.build_packet(0xAA, 0x05, [0x04, 0x9D, 0x08])))
    assert h6199.effect == "candy"
    cb(None, bytearray(proto.build_packet(0xAA, 0x05, [0x04, 0x09])))
    assert h6199.effect == "candlelight"


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
    c2 = _c(start_notify=AsyncMock(), write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    with patch(f"{M}.bluetooth") as bt, patch(f"{M}.establish_connection", return_value=c2):
        bt.async_ble_device_from_address.return_value = MagicMock()
        await coord._ensure_connected()
    c2.start_notify.assert_called_once()
    for q in (proto.KEEP_ALIVE, proto.BRIGHTNESS_QUERY, proto.COLOR_MODE_QUERY):
        c2.write_gatt_char.assert_any_await(proto.WRITE_UUID, q, response=False)
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
    failing_client = _c(write_gatt_char=AsyncMock(side_effect=BleakError("fail")))
    coord._client = failing_client
    with patch.object(coord, "_ensure_connected", return_value=failing_client):
        assert await coord.refresh_state() is False
    coord._cancel_disconnect = (cancel := MagicMock())
    coord._client = _c()
    coord._reset_disconnect_timer()
    cancel.assert_called_once()
    assert coord._cancel_disconnect is not cancel


async def test_send_state_queries_selective(coord):
    c = _c(write_gatt_char=AsyncMock())
    coord._client = c

    assert await coord._send_state_queries(query_power=False, query_brightness=True, query_color_mode=False) is True
    c.write_gatt_char.assert_awaited_once_with(proto.WRITE_UUID, proto.BRIGHTNESS_QUERY, response=False)

    c.write_gatt_char.reset_mock()
    assert await coord._send_state_queries(query_power=True, query_brightness=False, query_color_mode=True) is True
    calls = [args.args[1] for args in c.write_gatt_char.await_args_list]
    assert calls == [proto.KEEP_ALIVE, proto.COLOR_MODE_QUERY]


async def test_send_command_sets_expected_brightness(coord):
    c = _c(write_gatt_char=AsyncMock())
    with patch.object(coord, "_ensure_connected", return_value=c):
        assert "brightness_pct" not in coord._expected_state
        await coord.send_command(proto.build_brightness(42))
        assert coord._expected_state["brightness_pct"][0] == 42


def test_notify_callback_brightness_expectation(h6199):
    cb = h6199._notify_callback
    h6199.brightness_pct = 99
    h6199._expected_state["brightness_pct"] = (10, time.monotonic() + 60)
    cb(None, bytearray([0xAA, 0x04, 0x4B] + [0x00] * 5))
    assert h6199.brightness_pct == 99  # ignored

    h6199._expected_state["brightness_pct"] = (75, time.monotonic() + 60)
    cb(None, bytearray([0xAA, 0x04, 0x4B] + [0x00] * 5))
    assert h6199.brightness_pct == 75 and "brightness_pct" not in h6199._expected_state

    with patch(f"{M}.time.monotonic", return_value=1000):
        h6199._expected_state["brightness_pct"] = (10, 0)
        cb(None, bytearray([0xAA, 0x04, 0x01] + [0x00] * 5))
        assert h6199.brightness_pct == 1 and "brightness_pct" not in h6199._expected_state


def test_notify_callback_color_temp_window(h6199):
    """A stale aa05 STATIC reply must not clear an optimistic color temp within the window."""
    cb = h6199._notify_callback
    reply = bytearray(proto.build_packet(0xAA, 0x05, [0x15, 0x01, 10, 20, 30]))

    h6199.color_temp_kelvin = 4000
    h6199.rgb_color = (1, 2, 3)
    h6199._expected_state["color_temp_kelvin"] = (4000, time.monotonic() + 60)
    cb(None, reply)
    assert h6199.color_temp_kelvin == 4000
    assert h6199.rgb_color == (1, 2, 3)
    assert "color_temp_kelvin" in h6199._expected_state

    # Past the deadline the device reply wins: kelvin cleared, rgb adopted.
    h6199._expected_state["color_temp_kelvin"] = (4000, time.monotonic() - 1)
    cb(None, reply)
    assert h6199.color_temp_kelvin is None
    assert h6199.rgb_color == (10, 20, 30)
    assert "color_temp_kelvin" not in h6199._expected_state


def test_notify_callback_effect_window(h6199):
    """A stale aa05 reply must not clobber a just-set effect within the window."""
    cb = h6199._notify_callback
    h6199.effect = "candy"
    h6199._expected_state["effect"] = ("candy", time.monotonic() + 60)
    cb(None, bytearray(proto.build_packet(0xAA, 0x05, [0x15, 0x01, 10, 20, 30])))
    assert h6199.effect == "candy"
    assert "effect" in h6199._expected_state


def test_active_custom_id_sticky_clear(h6199):
    """active_custom_id survives a bare-colour aa05 but clears on scene/music/video."""
    cb = h6199._notify_callback
    for payload, expected_field, expected_value in (
        ([0x15, 0x01, 10, 20, 30], "rgb_color", (10, 20, 30)),
        ([0x15, 0x02, 50], "white_brightness", 50),
    ):
        h6199.active_custom_id = "flame"
        cb(None, bytearray(proto.build_packet(0xAA, 0x05, payload)))
        assert h6199.active_custom_id == "flame"
        assert getattr(h6199, expected_field) == expected_value
    for payload in ([0x04, 0x9D, 0x08], [0x13, 0x04, 66, 0x00, 0x01, 1, 2, 3], [0x00, 0x00, 0x01, 42]):
        h6199.active_custom_id = "flame"
        cb(None, bytearray(proto.build_packet(0xAA, 0x05, payload)))
        assert h6199.active_custom_id is None


def test_readback_mode_mutual_exclusion(h6199):
    """Each parsed readback mode leaves exactly one mode truthful, clearing any stale others."""
    cb = h6199._notify_callback
    music = bytearray(proto.build_packet(0xAA, 0x05, [0x13, 0x04, 66, 0x00, 0x01, 1, 2, 3]))
    video = bytearray(proto.build_packet(0xAA, 0x05, [0x00, 0x00, 0x01, 42]))
    scene = bytearray(proto.build_packet(0xAA, 0x05, [0x04, 0x9D, 0x08]))

    h6199.video_mode, h6199.effect, h6199.active_custom_id = "game", "candy", "flame"
    cb(None, music)
    assert (h6199.music_mode, h6199.video_mode, h6199.effect, h6199.active_custom_id) == (
        "spectrum",
        "off",
        None,
        None,
    )

    h6199.music_mode, h6199.effect, h6199.active_custom_id = "rhythm", "candy", "flame"
    cb(None, video)
    assert (h6199.video_mode, h6199.music_mode, h6199.effect, h6199.active_custom_id) == (
        "game",
        "off",
        None,
        None,
    )

    h6199.music_mode, h6199.video_mode, h6199.active_custom_id = "rhythm", "movie", "flame"
    cb(None, scene)
    assert (h6199.effect, h6199.music_mode, h6199.video_mode, h6199.active_custom_id) == (
        "candy",
        "off",
        "off",
        None,
    )


async def test_send_command_arms_expected_state(coord):
    c = _c(write_gatt_char=AsyncMock())
    with patch.object(coord, "_ensure_connected", return_value=c):
        await coord.send_command(proto.build_color_temp(4000))
        assert coord._expected_state["color_temp_kelvin"][0] == 4000

        await coord.send_command(proto.build_color_rgb(10, 20, 30))
        assert coord._expected_state["rgb_color"][0] == (10, 20, 30)

        mode_id = next(iter(proto.MUSIC_SLUG_BY_ID))
        await coord.send_command(proto.build_music_mode_with_color(mode_id))
        assert coord._expected_state["music_mode"][0] == proto.MUSIC_SLUG_BY_ID[mode_id]


async def test_refresh_state_query_selection(coord):
    coord.is_on = True
    coord.effect = "video: movie"
    with (
        patch.object(coord, "_ensure_connected", new_callable=AsyncMock),
        patch.object(coord, "_send_state_queries", new=AsyncMock(return_value=True)) as sq,
    ):
        assert await coord.refresh_state(expected_effect=None, expected_on=True) is True
        sq.assert_awaited_with(query_power=True, query_brightness=False, query_color_mode=False)
        sq.reset_mock()

        assert await coord.refresh_state(expected_effect="video: movie", expected_on=None) is True
        sq.assert_awaited_with(query_power=False, query_brightness=False, query_color_mode=True)
        sq.reset_mock()

        assert await coord.refresh_state(expected_effect=None, expected_on=None) is True
        sq.assert_awaited_with(query_power=True, query_brightness=False, query_color_mode=True)


async def test_send_command_noop_during_shutdown(coord):
    """Commands must be silently dropped once HA is shutting down."""
    c = _c(write_gatt_char=AsyncMock())
    coord.hass.is_stopping = True
    with patch.object(coord, "_ensure_connected", return_value=c):
        await coord.send_command(proto.build_power(True))
    c.write_gatt_char.assert_not_awaited()


async def test_update_data_noop_during_shutdown(coord):
    """_async_update_data must return cached state without BLE activity during shutdown."""
    coord.is_on, coord.brightness_pct = True, 50
    coord.hass.is_stopping = True
    ensure = AsyncMock()
    with patch.object(coord, "_ensure_connected", ensure):
        result = await coord._async_update_data()
    ensure.assert_not_awaited()
    assert result["is_on"] is True and result["brightness_pct"] == 50


def test_segment_colors_initial_state(coord, h6199):
    assert coord.segment_colors == [(255, 255, 255)] * 15
    assert h6199.segment_colors == [(255, 255, 255)] * 15
    assert len(coord.segment_colors) == coord.profile.segment_count


def test_segment_colors_empty_for_unsupported(hass):
    flat = replace(MODEL_PROFILES["H617A"], segment_count=0)
    with patch(f"{M}.get_profile", return_value=flat):
        c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:00", "H617A")
    assert c.segment_colors == [] and c.profile.segment_count == 0


def test_whole_strip_reply_leaves_segments_untouched(h6199):
    """A color-mode read reply updates rgb_color but must not clobber painted segments."""
    h6199.segment_colors = [(1, 2, 3)] * 15
    h6199._notify_callback(None, bytearray(proto.build_packet(0xAA, 0x05, [0x15, 0x01, 10, 20, 30])))
    assert h6199.rgb_color == (10, 20, 30)
    assert h6199.segment_colors == [(1, 2, 3)] * 15


async def test_async_paint_segments_updates_slots_and_sends(coord):
    groups = [([1, 2], (255, 0, 0)), ([3], (0, 0, 255))]
    with (
        patch.object(coord, "send_command", new_callable=AsyncMock) as sc,
        patch.object(coord, "async_set_updated_data") as pushed,
    ):
        await coord.async_paint_segments(groups)
    assert [call.args[0] for call in sc.await_args_list] == proto.build_segment_paint(groups)
    assert sc.await_count == 2
    assert coord.segment_colors[:4] == [(255, 0, 0), (255, 0, 0), (0, 0, 255), (255, 255, 255)]
    pushed.assert_called_once()


async def test_async_paint_segments_rolls_back_on_failure(coord):
    before = list(coord.segment_colors)
    with (
        patch.object(coord, "send_command", new=AsyncMock(side_effect=BleakError("boom"))),
        pytest.raises(BleakError),
    ):
        await coord.async_paint_segments([([1, 2], (255, 0, 0))])
    assert coord.segment_colors == before


async def test_async_paint_segments_rejects_unsupported(coord):
    coord.profile = replace(coord.profile, segment_count=0)
    with (
        patch.object(coord, "send_command", new_callable=AsyncMock) as sc,
        pytest.raises(ValueError),
    ):
        await coord.async_paint_segments([([1], (1, 2, 3))])
    sc.assert_not_awaited()


@pytest.mark.parametrize("bad", [[0], [16], []])
async def test_async_paint_segments_rejects_invalid_segments(coord, bad):
    before = list(coord.segment_colors)
    with (
        patch.object(coord, "send_command", new_callable=AsyncMock) as sc,
        pytest.raises(ValueError),
    ):
        await coord.async_paint_segments([(bad, (1, 2, 3))])
    sc.assert_not_awaited()
    assert coord.segment_colors == before


def test_notify_callback_poweroff_memory(h6199):
    cb = h6199._notify_callback
    assert h6199.poweroff_memory is None
    cb(None, bytearray([0xAA, 0x41, 0x01, 0x00]))
    assert h6199.poweroff_memory is True
    cb(None, bytearray([0xAA, 0x41, 0x00, 0x00]))
    assert h6199.poweroff_memory is False


def test_notify_callback_poweroff_memory_full_frame(h6199):
    h6199._notify_callback(None, bytearray(proto.build_packet(0xAA, 0x41, [0x01, 0x02])))
    assert h6199.poweroff_memory is True


def test_notify_callback_unknown_domain_ignored(h6199):
    h6199.poweroff_memory = None
    h6199._notify_callback(None, bytearray([0xAA, 0x99, 0x01, 0x00]))
    assert h6199.poweroff_memory is None


def test_timer_initial_state(coord):
    assert coord.sleep_timer_enabled is None and coord.sleep_timer_minutes is None
    assert coord.wakeup_timer_enabled is None and coord.wakeup_timer_time is None
    assert coord.schedule_timers == [None, None, None, None]


async def test_set_sleep_timer_sends_and_updates(coord):
    with (
        patch.object(coord, "send_command", new_callable=AsyncMock) as sc,
        patch.object(coord, "async_set_updated_data") as pushed,
    ):
        await coord.async_set_sleep_timer(enabled=True, minutes=45)
    assert coord.sleep_timer_enabled is True and coord.sleep_timer_minutes == 45
    sc.assert_awaited_once_with(proto.build_timer_sleep(True, coord.brightness_pct, 45))
    pushed.assert_called_once()


async def test_set_sleep_timer_rollback(coord):
    with (
        patch.object(coord, "send_command", new=AsyncMock(side_effect=BleakError("boom"))),
        pytest.raises(BleakError),
    ):
        await coord.async_set_sleep_timer(enabled=True, minutes=45)
    assert coord.sleep_timer_enabled is None and coord.sleep_timer_minutes is None


async def test_set_sleep_timer_partial_updates(coord):
    with (
        patch.object(coord, "send_command", new_callable=AsyncMock) as sc,
        patch.object(coord, "async_set_updated_data"),
    ):
        await coord.async_set_sleep_timer(enabled=True)
        assert coord.sleep_timer_enabled is True and coord.sleep_timer_minutes is None
        assert sc.await_args.args[0] == proto.build_timer_sleep(True, coord.brightness_pct, 0)
        await coord.async_set_sleep_timer(minutes=30)
    assert coord.sleep_timer_enabled is True and coord.sleep_timer_minutes == 30


async def test_set_wakeup_timer_sends_and_updates(coord):
    with (
        patch.object(coord, "send_command", new_callable=AsyncMock) as sc,
        patch.object(coord, "async_set_updated_data"),
    ):
        await coord.async_set_wakeup_timer(enabled=True, wake_time=dtime(7, 30))
    assert coord.wakeup_timer_enabled is True and coord.wakeup_timer_time == dtime(7, 30)
    sc.assert_awaited_once_with(proto.build_timer_wakeup(True, 100, 7, 30))


async def test_set_wakeup_timer_rollback(coord):
    with (
        patch.object(coord, "send_command", new=AsyncMock(side_effect=BleakError("boom"))),
        pytest.raises(BleakError),
    ):
        await coord.async_set_wakeup_timer(enabled=True, wake_time=dtime(6, 0))
    assert coord.wakeup_timer_enabled is None and coord.wakeup_timer_time is None


async def test_set_wakeup_timer_partial_updates(coord):
    with (
        patch.object(coord, "send_command", new_callable=AsyncMock) as sc,
        patch.object(coord, "async_set_updated_data"),
    ):
        await coord.async_set_wakeup_timer(enabled=True)
        assert coord.wakeup_timer_enabled is True and coord.wakeup_timer_time is None
        assert sc.await_args.args[0] == proto.build_timer_wakeup(True, 100, 0, 0)
        await coord.async_set_wakeup_timer(wake_time=dtime(8, 0))
    assert coord.wakeup_timer_time == dtime(8, 0)


async def test_set_schedule_timer_sends_and_updates(coord):
    days = [proto.Weekday.MON, proto.Weekday.FRI]
    with (
        patch.object(coord, "send_command", new_callable=AsyncMock) as sc,
        patch.object(coord, "async_set_updated_data"),
    ):
        await coord.async_set_schedule_timer(1, on_action=True, hour=6, minute=15, days=days)
    record = coord.schedule_timers[1]
    assert record is not None and record.enabled and record.on_action and (record.hour, record.minute) == (6, 15)
    assert record.repeat_days == frozenset(days)
    sc.assert_awaited_once_with(proto.build_timer_schedule(1, True, True, 6, 15, frozenset(days)))


async def test_clear_schedule_timer_sends_and_updates(coord):
    coord.schedule_timers[2] = MagicMock()
    with (
        patch.object(coord, "send_command", new_callable=AsyncMock) as sc,
        patch.object(coord, "async_set_updated_data"),
    ):
        await coord.async_clear_schedule_timer(2)
    assert coord.schedule_timers[2] is None
    sc.assert_awaited_once_with(proto.build_timer_schedule(2, False, False, 0, 0))


async def test_set_schedule_timer_rollback(coord):
    before = list(coord.schedule_timers)
    with (
        patch.object(coord, "send_command", new=AsyncMock(side_effect=BleakError("boom"))),
        pytest.raises(BleakError),
    ):
        await coord.async_set_schedule_timer(0, on_action=True, hour=1, minute=2)
    assert coord.schedule_timers == before


def test_notify_callback_sleep_timer(coord):
    # EXPERIMENTAL: harness=G encoding=decode-only
    coord._notify_callback(None, bytearray([0xAA, 0x11, 0x01, 80, 45, 0]))
    assert coord.sleep_timer_enabled is True and coord.sleep_timer_minutes == 45


def test_notify_callback_wakeup_timer(coord):
    # EXPERIMENTAL: harness=G encoding=decode-only
    coord._notify_callback(None, bytearray([0xAA, 0x12, 0x01, 100, 7, 30, 0x80, 10]))
    assert coord.wakeup_timer_enabled is True and coord.wakeup_timer_time == dtime(7, 30)


def test_notify_callback_schedule_timer(coord):
    # aa 23 reply is the full table: 0xff prefix + four 4-byte slot records.
    table = [0xFF, 0x81, 6, 15, 0x83, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    coord._notify_callback(None, bytearray(proto.build_packet(0xAA, 0x23, table)))
    record = coord.schedule_timers[0]
    assert record is not None and record.enabled and record.on_action and (record.hour, record.minute) == (6, 15)
    assert record.repeat_days == frozenset({proto.Weekday.MON, proto.Weekday.TUE})


def test_notify_callback_timer_full_frames(coord):
    # EXPERIMENTAL: harness=G encoding=decode-only
    coord._notify_callback(None, bytearray(proto.build_packet(0xAA, 0x11, [1, 90, 20, 0])))
    coord._notify_callback(None, bytearray(proto.build_packet(0xAA, 0x12, [1, 100, 5, 0, 0x80, 15])))
    assert coord.sleep_timer_minutes == 20 and coord.wakeup_timer_time == dtime(5, 0)


def test_notify_callback_sleep_timer_short_payload_ignored(coord):
    coord._notify_callback(None, bytearray([0xAA, 0x11, 0x01, 80]))
    assert coord.sleep_timer_enabled is None and coord.sleep_timer_minutes is None


def test_notify_callback_schedule_out_of_range_slot_ignored(coord):
    coord._notify_callback(None, bytearray([0xAA, 0x23, 0x09, 0x81, 6, 15, 0x80]))
    assert coord.schedule_timers == [None, None, None, None]


def test_available_reflects_link_or_presence(coord):
    coord._client, coord._present = None, False
    assert coord.available is False
    coord._present = True
    assert coord.available is True
    coord._present, coord._client = False, MagicMock(is_connected=True)
    assert coord.available is True
    coord._client = MagicMock(is_connected=False)
    assert coord.available is False


def test_device_info_carries_versions_and_omits_connections(coord):
    coord.fw_version, coord.hw_version = "3.02.24", "3.01.01"
    info = coord.device_info
    assert info["sw_version"] == "3.02.24" and info["hw_version"] == "3.01.01"
    assert info["identifiers"] == {(DOMAIN, coord.address)}
    assert "connections" not in info


def test_notify_callback_sets_fw_hw_versions(coord):
    fw = proto.build_packet(proto.STATUS_HEADER, proto.FIRMWARE_PACKET_TYPE, list(b"3.02.24"))
    hw = proto.build_packet(proto.STATUS_HEADER, proto.HARDWARE_PACKET_TYPE, list(b"3.01.01"))
    coord._notify_callback(None, bytearray(fw))
    coord._notify_callback(None, bytearray(hw))
    assert coord.fw_version == "3.02.24" and coord.hw_version == "3.01.01"


def test_notify_callback_pushes_identity_to_registry(coord):
    """#97: fw/hw arrive after entities snapshot device_info, so the coordinator must push the
    version into the device registry itself or the device page stays blank."""
    fw = proto.build_packet(proto.STATUS_HEADER, proto.FIRMWARE_PACKET_TYPE, list(b"3.02.24"))
    registry = MagicMock()
    registry.async_get_device.return_value = MagicMock(id="dev-1")
    with patch(f"{M}.dr.async_get", return_value=registry):
        coord._notify_callback(None, bytearray(fw))
        registry.async_update_device.assert_called_once_with("dev-1", sw_version="3.02.24", hw_version=None)
        # A repeat reply carrying the same value must not re-write the registry.
        registry.async_update_device.reset_mock()
        coord._notify_callback(None, bytearray(fw))
        registry.async_update_device.assert_not_called()


def test_note_identity_skips_registry_when_device_absent(coord):
    """No device yet (identity read races entity setup): store the value, never crash."""
    registry = MagicMock()
    registry.async_get_device.return_value = None
    with patch(f"{M}.dr.async_get", return_value=registry):
        coord._note_identity(fw_version="3.02.24")
    assert coord.fw_version == "3.02.24"
    registry.async_update_device.assert_not_called()


async def test_send_identity_queries_only_unknown(coord):
    c = _c(write_gatt_char=AsyncMock())
    coord._client = c
    await coord._send_identity_queries()
    c.write_gatt_char.assert_any_await(proto.WRITE_UUID, proto.HW_QUERY, response=False)
    c.write_gatt_char.assert_any_await(proto.WRITE_UUID, proto.FW_QUERY, response=False)
    # Only the still-unknown value is re-queried.
    coord.fw_version, coord.hw_version = "3.02.24", None
    c.write_gatt_char.reset_mock()
    await coord._send_identity_queries()
    c.write_gatt_char.assert_awaited_once_with(proto.WRITE_UUID, proto.HW_QUERY, response=False)
    # Both known -> nothing sent.
    coord.hw_version = "3.01.01"
    c.write_gatt_char.reset_mock()
    await coord._send_identity_queries()
    c.write_gatt_char.assert_not_awaited()
    # include_hw=False (keep-alive retry path): only firmware, even when hw is unknown.
    coord.fw_version = coord.hw_version = None
    c.write_gatt_char.reset_mock()
    await coord._send_identity_queries(include_hw=False)
    c.write_gatt_char.assert_awaited_once_with(proto.WRITE_UUID, proto.FW_QUERY, response=False)


def test_keep_alive_started_as_background_task(coord):
    """#86 guard: the lifetime keep-alive loop must be a background task (never a tracked
    setup task), or HA bootstrap waits on it and logs a "blocking start up" warning."""
    created = {}

    def _capture(coro, name):
        coro.close()
        created["name"] = name
        return MagicMock()

    with patch.object(coord.hass, "async_create_background_task", side_effect=_capture) as spy:
        coord._start_keep_alive()
    spy.assert_called_once()
    assert "keep-alive" in created["name"]


async def test_keep_alive_retries_identity_until_bounded(coord):
    """#97: a connect-time identity reply can be missed, so keep-alive re-queries while a
    version is unknown, bounded by IDENTITY_RETRY_TICKS so an unanswered aa07 is not polled forever."""
    coord._client = _c(write_gatt_char=AsyncMock())
    coord.fw_version = coord.hw_version = None
    calls = {"n": 0}

    async def _state(**_kw):
        calls["n"] += 1
        return calls["n"] < IDENTITY_RETRY_TICKS + 2  # break two ticks past the cap

    with (
        patch.object(coord, "_send_identity_queries", new_callable=AsyncMock) as ident,
        patch.object(coord, "_send_state_queries", side_effect=_state),
        patch(f"{M}.asyncio.sleep", new_callable=AsyncMock),
    ):
        await coord._keep_alive_loop()
    assert ident.await_count == IDENTITY_RETRY_TICKS


async def test_keep_alive_skips_identity_when_fw_known(coord):
    """#97: keep-alive re-queries firmware only; a known fw stops retries even if hw stays null."""
    coord._client = _c(write_gatt_char=AsyncMock())
    coord.fw_version, coord.hw_version = "3.02.24", None
    with (
        patch.object(coord, "_send_identity_queries", new_callable=AsyncMock) as ident,
        patch.object(coord, "_send_state_queries", new_callable=AsyncMock, return_value=False),
        patch(f"{M}.asyncio.sleep", new_callable=AsyncMock),
    ):
        await coord._keep_alive_loop()
    ident.assert_not_awaited()


async def test_async_setup_registers_presence_and_callbacks_flip(coord):
    with patch(f"{M}.bluetooth") as bt:
        bt.async_address_present.return_value = False
        await coord._async_setup()
        bt.async_address_present.assert_called_once()
        bt.async_register_callback.assert_called_once()
        bt.async_track_unavailable.assert_called_once()
    assert coord._present is False
    with patch.object(coord, "async_update_listeners") as notify:
        coord._async_on_advertisement(MagicMock(), MagicMock())
        assert coord._present is True
        notify.assert_called_once()
        notify.reset_mock()
        coord._async_on_advertisement(MagicMock(), MagicMock())
        notify.assert_not_called()
        coord._async_on_unavailable(MagicMock())
        assert coord._present is False
        notify.assert_called_once()


async def test_first_refresh_reports_update_failed_then_degrades_silently(coord):
    with patch.object(coord, "_ensure_connected", new_callable=AsyncMock, side_effect=BleakError("down")):
        with pytest.raises(UpdateFailed):
            await coord._async_update_data()
        assert await coord._async_update_data() == coord._state_snapshot()


async def test_first_refresh_non_readable_requires_presence(hass):
    flat = replace(MODEL_PROFILES["H617A"], state_readable=False)
    with patch(f"{M}.get_profile", return_value=flat):
        c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:22", "H617A")
    c._present = False
    with pytest.raises(UpdateFailed):
        await c._async_update_data()
    assert await c._async_update_data() == c._state_snapshot()


async def test_config_entry_first_refresh_raises_config_entry_not_ready(coord):
    coord.config_entry = MagicMock(state=ConfigEntryState.SETUP_IN_PROGRESS)
    with (
        patch(f"{M}.bluetooth") as bt,
        patch.object(coord, "_ensure_connected", new_callable=AsyncMock, side_effect=BleakError("down")),
    ):
        bt.async_address_present.return_value = False
        with pytest.raises(ConfigEntryNotReady):
            await coord.async_config_entry_first_refresh()
