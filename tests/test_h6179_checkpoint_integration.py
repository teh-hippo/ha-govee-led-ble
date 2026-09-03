"""CP-30 integration checks for the H6179 wire family."""

from datetime import datetime, time, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from bleak import BleakError

from custom_components.ha_govee_led_ble.control_arbiter import ControlIntent
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_expectations import expectations_from_packet
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    WIRE_PROTOCOL_CODECS,
    ProtocolParseRejection,
    build_brightness,
    build_brightness_query,
    build_colour_mode_query,
    build_colour_temperature,
    build_firmware_query,
    build_h6179_clock_sync,
    build_h6179_diy_activation,
    build_h6179_limit,
    build_h6179_scene,
    build_h6179_schedule_slot,
    build_h6179_sleep,
    build_h6179_wake,
    build_hardware_query,
    build_limit_query,
    build_mode_query,
    build_music_mode,
    build_power,
    build_power_query,
    build_schedules_query,
    build_sleep_query,
    build_wake_query,
    decode_h6179_brightness,
    encode_h6179_brightness,
    parse_command,
    parse_command_result,
    parse_h6179_command,
    parse_h6179_schedule_write,
    parse_h6179_status,
    parse_h6179_status_query,
    parse_h6179_status_result,
    parse_status,
    parse_status_query,
    parse_status_result,
)
from custom_components.ha_govee_led_ble.h6179_schedule import (
    ClockSync,
    LimitState,
    RepeatDay,
    ScheduleAction,
    ScheduleSlot,
    SleepState,
    WakeState,
)
from custom_components.ha_govee_led_ble.light_commands import (
    build_color_rgb,
    parse_static_write,
)
from custom_components.ha_govee_led_ble.music_commands import build_music_params
from custom_components.ha_govee_led_ble.transport import (
    WRITE_UUID,
    fragment_h6179_a1_02,
    xor_checksum,
)

M = "custom_components.ha_govee_led_ble.coordinator"
H = bytes.fromhex


def _status(domain: int, body: bytes) -> bytes:
    packet = bytearray((0xAA, domain))
    packet.extend(body)
    packet.extend(bytes(19 - len(packet)))
    packet.append(xor_checksum(packet))
    return bytes(packet)


def _command(opcode: int, body: bytes) -> bytes:
    packet = bytearray((0x33, opcode))
    packet.extend(body)
    packet.extend(bytes(19 - len(packet)))
    packet.append(xor_checksum(packet))
    return bytes(packet)


@pytest.fixture
def h6179(hass):
    return GoveeBLECoordinator(
        hass,
        "AA:BB:CC:DD:EE:79",
        "H6179",
        configuration_url="homeassistant://ha-govee-led-ble/editor/test-entry",
    )


def test_codec_registry_is_explicit_and_cross_model_parsing_fails_closed() -> None:
    assert tuple(WIRE_PROTOCOL_CODECS) == ("H617A", "H6179", "H6199")
    h6179_static = H("33050d0a141e000000000000000000000000003b")
    h617a_static = H("330515010000000e10ffcb8dff7f000000000005")

    assert parse_command(h6179_static, "H617A") is None
    assert parse_command(h6179_static, "H6199") is None
    assert parse_command(h617a_static, "H6179") is not None
    assert parse_h6179_command(h617a_static) is None
    assert parse_status(_status(0xA5, b"\x01"), "H6179") is not None
    assert parse_h6179_status(_status(0xA5, b"\x01")) is None
    assert parse_h6179_status_query(build_colour_mode_query("H617A")) is None
    with pytest.raises(ValueError, match="mode status-query operation"):
        build_mode_query("H6199")
    with pytest.raises(ValueError, match="command codec"):
        build_power(True, "H9999")

    semantic = parse_command_result(h6179_static, "H617A")
    speculative = parse_command_result(h617a_static, "H6179")
    unsupported = parse_command_result(h6179_static, "H9999")
    assert (semantic.parser, semantic.rejection) == (
        "command_write",
        ProtocolParseRejection.SEMANTIC_REJECTED,
    )
    assert (speculative.parser, speculative.rejection) == (
        "speculative/h6179_command_write",
        None,
    )
    assert speculative.parsed is not None
    assert unsupported.rejection is ProtocolParseRejection.UNSUPPORTED_MODEL


@pytest.mark.parametrize(
    ("parse_result", "frame"),
    [
        (parse_command_result, H("3301010000000000000000000000000000000033")),
        (parse_status_result, _status(0x01, b"\x01")),
    ],
)
def test_h6179_shared_parse_results_enforce_length_and_checksum(parse_result, frame: bytes) -> None:
    assert parse_result(frame[:-1], "H6179").rejection is ProtocolParseRejection.INVALID_LENGTH

    corrupted = bytearray(frame)
    corrupted[-1] ^= 0x01
    assert parse_result(bytes(corrupted), "H6179").rejection is ProtocolParseRejection.INVALID_CHECKSUM


@pytest.mark.parametrize(
    "frame",
    [
        _command(0xA5, b"\x01"),
        _command(0x01, b"\x02"),
        _command(0x04, b"\x13"),
        _command(0x04, b"\xff"),
        _command(0x05, b"\x7f"),
        _command(0x05, H("0dffffff0001ffb170")),
        _command(0x05, b"\x04\x07\x01"),
        _command(0x05, b"\x0e\x02\x63\x00"),
        _command(0x05, b"\x0e\x00\x64\x00"),
        _command(0x05, b"\x0e\x00\x63\x02\x00\x00\x00"),
    ],
)
def test_h6179_raw_commands_parse_but_semantics_fail_closed(frame: bytes) -> None:
    structural = parse_command_result(frame, "H6179")

    assert structural.parsed is not None
    assert structural.parser == "speculative/h6179_command_write"
    assert structural.rejection is None
    assert parse_h6179_command(frame) is None


@pytest.mark.parametrize(
    "frame",
    [
        _status(0xA5, b"\x01"),
        _status(0x01, b"\x02"),
        _status(0x04, b"\x13"),
        _status(0x04, b"\xff"),
        _status(0x05, b"\x7f"),
        _status(0x05, H("0dffffff0001ffb170")),
        _status(0x05, b"\x04\x07\x00\x01"),
        _status(0x05, b"\x0e\x02\x63\x00"),
        _status(0x23, b"\x04\x80\x06\x1e\x00"),
        _status(0x11, bytes((1, 101, 45, 20))),
        _status(0x12, bytes((1, 100, 24, 15, 0, 30))),
        _status(0x0E, b"\x02"),
    ],
)
def test_h6179_raw_statuses_parse_but_semantics_reject_without_state(frame: bytes) -> None:
    structural = parse_status_result(frame, "H6179")
    semantic = parse_h6179_status_result(frame)

    assert structural.parsed is not None
    assert structural.parser == "speculative/h6179_status_reply"
    assert structural.rejection is None
    assert semantic.parsed is None
    assert semantic.parser == structural.parser
    assert semantic.rejection is ProtocolParseRejection.SEMANTIC_REJECTED


@pytest.mark.parametrize(
    "frame",
    [
        _status(0xA5, b"\x01"),
        _status(0x01, b"\x01"),
        _status(0x05, b"\x00"),
        _status(0x07, b"\x02"),
        _status(0x23, b"\x00"),
    ],
)
def test_h6179_raw_queries_parse_but_semantics_fail_closed(frame: bytes) -> None:
    assert parse_status_query(frame, "H6179") is not None
    assert parse_h6179_status_query(frame) is None


@pytest.mark.parametrize(
    "frame",
    [
        _command(0x7F, b"\x01"),
        _command(0x09, bytes((24, 0, 0, 1, 1, 0, 0))),
        _command(0x09, bytes((0, 0, 0, 1, 2, 0, 0))),
        _command(0x23, bytes.fromhex("0481061e80")),
        _command(0x23, bytes.fromhex("0002061e80")),
        _command(0x23, bytes.fromhex("0081061e15")),
        _command(0x11, bytes((1, 101, 45, 45))),
        _command(0x12, bytes((1, 100, 24, 15, 0, 30))),
        _command(0x0E, b"\x02"),
    ],
)
def test_h6179_raw_schedule_writes_parse_but_semantics_fail_closed(frame: bytes) -> None:
    assert parse_h6179_schedule_write(frame) is None


def test_h6179_command_echo_is_diagnostic_only(h6179) -> None:
    h6179.is_on = False
    frame = H("3301010000000000000000000000000000000033")

    h6179._notify_callback(None, bytearray(frame))

    assert h6179.is_on is False
    assert h6179.packet_log[-1]["outcome"] == "parsed"
    assert h6179.packet_log[-1]["reason"] == "command_echo_parsed"
    assert h6179.packet_log[-1]["parser"] == "speculative/h6179_command_write"


def test_h6179_core_builders_and_semantic_parsers_are_exact() -> None:
    frames = {
        build_power(True, "H6179"): "3301010000000000000000000000000000000033",
        build_brightness(100, "H6179"): "3304fe00000000000000000000000000000000c9",
        build_color_rgb(10, 20, 30, "H6179"): "33050d0a141e000000000000000000000000003b",
        build_colour_temperature(3600, (255, 203, 141), 0, "H6179"): ("33050dffffff0e10ffcb8d000000000000000063"),
        build_h6179_scene(0x07): "3305040700000000000000000000000000000035",
        build_music_mode(0, 99, None, True, "H6179"): "33050e006300000000000000000000000000005b",
        build_music_mode(1, 50, (0x12, 0x34, 0x56), False, "H6179"): ("33050e013201123456000000000000000000007a"),
        build_h6179_diy_activation(0x1234): "33050a341200000000000000000000000000001a",
    }

    for frame, expected in frames.items():
        assert frame == H(expected)
        assert parse_h6179_command(frame) is not None

    static = parse_static_write(build_color_rgb(10, 20, 30, "H6179"), "H6179")
    assert static is not None
    assert static.rgb == (10, 20, 30)
    assert static.segment_mask is None
    assert static.whole_strip
    assert expectations_from_packet(build_brightness(50, "H6179"), "H6179") == {"brightness_pct": 50}
    assert expectations_from_packet(build_h6179_scene(0x04), "H6179") == {
        "color_mode": (ParsedMode.SCENE, None),
        "effect": "movie",
        "unknown_scene_code": None,
    }


@pytest.mark.parametrize("scene_code", [0x00, 0x06, 0x7F, 0xFF])
def test_h6179_scene_builder_accepts_any_one_byte_catalogue_selector(scene_code: int) -> None:
    parsed = parse_h6179_command(build_h6179_scene(scene_code))

    assert parsed is not None
    assert parsed.values["scene_code"] == scene_code


@pytest.mark.parametrize("scene_code", [-1, 0x100, True])
def test_h6179_scene_builder_rejects_values_outside_one_byte_range(scene_code: int) -> None:
    with pytest.raises(ValueError, match="0 to 255"):
        build_h6179_scene(scene_code)


def test_h6179_brightness_conversion_is_exact_monotonic_and_round_trips() -> None:
    assert {percent: encode_h6179_brightness(percent) for percent in (1, 10, 50, 100)} == {
        1: 20,
        10: 41,
        50: 136,
        100: 254,
    }
    raw_values = [encode_h6179_brightness(percent) for percent in range(1, 101)]
    assert raw_values == sorted(raw_values)
    assert len(set(raw_values)) == 100
    assert [decode_h6179_brightness(raw) for raw in raw_values] == list(range(1, 101))
    assert decode_h6179_brightness(20) == 1
    assert decode_h6179_brightness(136) == 50
    assert decode_h6179_brightness(254) == 100
    assert [decode_h6179_brightness(raw) for raw in range(20, 255)] == sorted(
        decode_h6179_brightness(raw) for raw in range(20, 255)
    )
    for invalid in (0, 19, 255, True):
        with pytest.raises(ValueError, match="20 to 254"):
            decode_h6179_brightness(invalid)
    for invalid in (0, 101, True):
        with pytest.raises(ValueError, match="1 to 100"):
            build_brightness(invalid, "H6179")


def test_h6179_queries_and_schedule_writes_are_exact_semantic_apis() -> None:
    queries = {
        build_power_query("H6179"): ("aa010000000000000000000000000000000000ab", "power"),
        build_brightness_query("H6179"): ("aa040000000000000000000000000000000000ae", "brightness"),
        build_mode_query(): ("aa050100000000000000000000000000000000ae", "mode"),
        build_firmware_query("H6179"): ("aa060000000000000000000000000000000000ac", "firmware"),
        build_hardware_query("H6179"): ("aa070300000000000000000000000000000000ae", "hardware"),
        build_limit_query(): ("aa0e0000000000000000000000000000000000a4", "limit"),
        build_sleep_query(): ("aa110000000000000000000000000000000000bb", "sleep"),
        build_wake_query(): ("aa120000000000000000000000000000000000b8", "wake"),
        build_schedules_query(): ("aa23ff0000000000000000000000000000000076", "schedules"),
    }
    for query, (expected, domain) in queries.items():
        assert query == H(expected)
        assert parse_h6179_status_query(query) == domain

    clock = ClockSync(datetime(2026, 9, 3, 19, 20, 4, tzinfo=timezone(timedelta(hours=9, minutes=30))))
    slot = ScheduleSlot(
        2,
        True,
        ScheduleAction.ON,
        time(12),
        int(RepeatDay.MONDAY | RepeatDay.WEDNESDAY | RepeatDay.FRIDAY),
    )
    sleep = SleepState(True, 30, 45, 20)
    wake = WakeState(True, time(7, 15), slot.repeat_day_mask, 30, 100)
    writes = {
        build_h6179_clock_sync(clock): "33091314040401091e000000000000000000002b",
        build_h6179_schedule_slot(slot): "332302810c00950000000000000000000000000a",
        build_h6179_sleep(sleep): "3311011e2d2d000000000000000000000000003d",
        build_h6179_wake(wake): "33120164070f951e0000000000000000000000c7",
        build_h6179_limit(LimitState(True)): "330e01000000000000000000000000000000003c",
    }
    for frame, expected in writes.items():
        assert frame == H(expected)
        assert parse_h6179_schedule_write(frame) is not None

    one_time = build_h6179_schedule_slot(
        ScheduleSlot(0, True, ScheduleAction.ON, time(6, 30), 0),
        one_time=True,
    )
    assert one_time == H("33230081061e8000000000000000000000000009")
    parsed_one_time = parse_h6179_schedule_write(one_time)
    assert parsed_one_time is not None and parsed_one_time.values["one_time"] is True


def test_h6179_status_parser_returns_semantic_percentages_and_optional_domains() -> None:
    brightness = parse_h6179_status(_status(0x04, b"\x88"))
    mode = parse_h6179_status(_status(0x05, H("0e013201123456")))
    schedules = parse_h6179_status(_status(0x23, H("ff81061e8080160f00810c009500000080")))

    assert brightness is not None and brightness.values["brightness_pct"] == 50
    assert mode is not None
    assert dict(mode.values) == {
        "mode": "music",
        "music_mode": "mode_1",
        "music_mode_id": 1,
        "sensitivity": 50,
        "colour": (0x12, 0x34, 0x56),
    }
    assert schedules is not None and schedules.domain == "schedules"
    assert len(schedules.values["slots"]) == 4


def test_music_helpers_emit_no_h6179_companion_or_style_write() -> None:
    assert build_music_params(0, {}, model="H6179") == []
    assert build_music_params(1, {}, model="H6179") == []
    assert build_music_mode(0, 50, None, False, "H6179") == build_music_mode(0, 50, None, True, "H6179")


def test_existing_wire_routes_remain_byte_identical() -> None:
    power = H("3301010000000000000000000000000000000033")
    brightness = H("3304250000000000000000000000000000000012")
    query = H("aa050000000000000000000000000000000000af")

    for model in ("H617A", "H617E", "H6076", "H6199"):
        assert build_power(True, model) == power
        assert build_brightness(37, model) == brightness
    for model in ("H617A", "H617E", "H6076"):
        assert build_colour_mode_query(model) == query


async def test_h6179_setup_requires_only_core_status_and_ignores_optional_failure(h6179) -> None:
    client = MagicMock(is_connected=True)
    h6179._client = client
    h6179.rgb_color = (12, 34, 56)
    sent_domains: list[frozenset[str]] = []

    async def send(domains: frozenset[str]) -> bool:
        sent_domains.append(domains)
        if domains == h6179.profile.setup_required_status_domains:
            h6179._notify_callback(None, bytearray(_status(0x01, b"\x01")))
            h6179._notify_callback(None, bytearray(_status(0x04, b"\x88")))
            return True
        return False

    with (
        patch.object(h6179, "_ensure_connected", new=AsyncMock(return_value=client)),
        patch.object(h6179, "_send_h6179_status_queries", new=AsyncMock(side_effect=send)),
    ):
        state = await h6179._async_update_data()

    assert (state["is_on"], state["brightness_pct"]) == (True, 50)
    assert h6179.rgb_color == (12, 34, 56)
    assert sent_domains == [
        frozenset({"power", "brightness"}),
        frozenset({"mode", "schedules", "sleep", "wake", "limit"}),
    ]


async def test_h6179_starts_notifications_but_releases_the_connection_on_default_idle(h6179) -> None:
    assert h6179.profile.state_readable is False
    assert h6179.profile.supports_notifications is True
    assert h6179.update_interval is None
    with patch(f"{M}.async_call_later") as call_later:
        h6179._reset_disconnect_timer()
    assert call_later.call_args.args[1] == 15

    client = MagicMock(
        is_connected=True,
        start_notify=AsyncMock(),
        write_gatt_char=AsyncMock(),
    )
    with (
        patch(f"{M}.async_establish_ble_connection", new=AsyncMock(return_value=client)),
        patch(
            f"{M}.dt_util.now",
            return_value=datetime(2026, 9, 3, 20, 26, 35, tzinfo=timezone(timedelta(hours=10))),
        ),
        patch.object(h6179, "_reset_disconnect_timer"),
        patch.object(h6179, "_start_keep_alive"),
    ):
        assert await h6179._ensure_connected() is client

    client.start_notify.assert_awaited_once()
    assert client.write_gatt_char.await_args_list == [
        call(WRITE_UUID, build_hardware_query("H6179"), response=False),
        call(WRITE_UUID, build_firmware_query("H6179"), response=False),
        call(
            WRITE_UUID,
            build_h6179_clock_sync(ClockSync(datetime(2026, 9, 3, 20, 26, 35, tzinfo=timezone(timedelta(hours=10))))),
            response=False,
        ),
    ]
    assert h6179.h6179_schedule_state.clock_sync == ClockSync(
        datetime(2026, 9, 3, 20, 26, 35, tzinfo=timezone(timedelta(hours=10)))
    )


async def test_h6179_automatic_clock_sync_failure_does_not_fail_connection(h6179) -> None:
    client = MagicMock(
        is_connected=True,
        start_notify=AsyncMock(),
        write_gatt_char=AsyncMock(side_effect=(None, None, BleakError("clock rejected"))),
    )
    with (
        patch(f"{M}.async_establish_ble_connection", new=AsyncMock(return_value=client)),
        patch.object(h6179, "_reset_disconnect_timer"),
        patch.object(h6179, "_start_keep_alive"),
    ):
        assert await h6179._ensure_connected() is client

    assert client.write_gatt_char.await_count == 3
    assert h6179.h6179_schedule_state.clock_sync is None
    assert h6179._client is client


async def test_coordinator_packet_log_covers_rx_tx_and_effect_correlation(h6179) -> None:
    h6179._notify_callback(None, bytearray(b"\xaa\x05"))
    h6179._notify_callback(None, bytearray(_status(0x01, b"\x01")))

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    h6179._client = client
    with patch.object(h6179, "_ensure_connected", new=AsyncMock(return_value=client)):
        await h6179.send_command(build_power(True, "H6179"))
        packets = fragment_h6179_a1_02(b"abc")
        await h6179.async_write_effect_sequence(
            packets,
            intent=ControlIntent.PREVIEW,
            operation_id="11111111-1111-1111-1111-111111111111",
        )

    events = h6179.packet_log
    assert [(event["dir"], event["outcome"], event["reason"]) for event in events[:3]] == [
        ("rx", "rejected", "invalid_length"),
        ("rx", "parsed", "status_parsed"),
        ("tx", "sent", "write_succeeded"),
    ]
    effect_events = events[3:]
    assert all(key not in event for event in events[:3] for key in ("operation_id", "part_index", "part_count"))
    assert {event["operation_id"] for event in effect_events} == {"11111111-1111-1111-1111-111111111111"}
    assert [event["part_index"] for event in effect_events] == list(range(1, len(packets) + 1))
    assert all(event["part_count"] == len(packets) for event in effect_events)
    assert "AA:BB:CC:DD:EE:79" not in str(events)

    failed = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=BleakError("failed")))
    h6179._client = failed
    before = len(events)
    with pytest.raises(BleakError):
        await h6179.async_preview_write(build_power(False, "H6179"))
    assert len(h6179.packet_log) == before
