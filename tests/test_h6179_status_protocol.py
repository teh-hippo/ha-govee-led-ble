"""H6179 status and schedule protocol checks."""

from __future__ import annotations

import io
import os
import sys
from importlib import import_module
from typing import Any

import pytest
from kaitaistruct import KaitaiStream

_GENERATED_DIR = os.environ.get("KAITAI_GENERATED_DIR")
if _GENERATED_DIR:
    sys.path.insert(0, _GENERATED_DIR)

_MODULE_PREFIX = "" if _GENERATED_DIR else "custom_components.ha_govee_led_ble.generated_protocol."


def _generated(module: str, class_name: str) -> type[Any]:
    module_name = f"{_MODULE_PREFIX}{module}"
    try:
        generated = import_module(module_name)
    except ModuleNotFoundError as error:
        if error.name != module_name:
            raise
        pytest.skip("H6179 runtime generation is not integrated yet", allow_module_level=True)
    return getattr(generated, class_name)


H6179StatusQuery = _generated("h6179_status_query", "H6179StatusQuery")
H6179StatusReply = _generated("h6179_status_reply", "H6179StatusReply")
H6179ScheduleWrite = _generated("h6179_schedule_write", "H6179ScheduleWrite")

POWER_QUERY = bytes.fromhex("aa010000000000000000000000000000000000ab")
BRIGHTNESS_QUERY = bytes.fromhex("aa040000000000000000000000000000000000ae")
MODE_QUERY = bytes.fromhex("aa050100000000000000000000000000000000ae")
FIRMWARE_QUERY = bytes.fromhex("aa060000000000000000000000000000000000ac")
HARDWARE_QUERY = bytes.fromhex("aa070300000000000000000000000000000000ae")
LIMIT_QUERY = bytes.fromhex("aa0e0000000000000000000000000000000000a4")
SLEEP_QUERY = bytes.fromhex("aa110000000000000000000000000000000000bb")
WAKE_QUERY = bytes.fromhex("aa120000000000000000000000000000000000b8")
TIMERS_QUERY = bytes.fromhex("aa23ff0000000000000000000000000000000076")


def _frame(header: int, domain: int, body: bytes) -> bytes:
    packet = bytes((header, domain)) + body.ljust(17, b"\x00")
    checksum = 0
    for value in packet:
        checksum ^= value
    return packet + bytes((checksum,))


POWER_REPLY = _frame(0xAA, 0x01, b"\x01")
BRIGHTNESS_REPLY = _frame(0xAA, 0x04, b"\x88")
FIRMWARE_REPLY = _frame(0xAA, 0x06, b"1.00.08\x00")
HARDWARE_REPLY = _frame(0xAA, 0x07, b"\x03" + b"1.00.00\x00")
STATIC_REPLY = _frame(0xAA, 0x05, bytes.fromhex("0d1234560000000000"))
TEMPERATURE_REPLY = _frame(0xAA, 0x05, bytes.fromhex("0dffffff0bb8ffb170"))
SCENE_REPLY = _frame(0xAA, 0x05, bytes.fromhex("041000"))
MUSIC_AUTO_REPLY = _frame(0xAA, 0x05, bytes.fromhex("0e006300"))
MUSIC_FIXED_REPLY = _frame(0xAA, 0x05, bytes.fromhex("0e013201123456"))
DIY_REPLY = _frame(0xAA, 0x05, bytes.fromhex("0a3412"))
TIMERS_REPLY = _frame(
    0xAA,
    0x23,
    bytes.fromhex("ff81061e8080160f00810c009500000080"),
)
SLEEP_REPLY = _frame(0xAA, 0x11, bytes((1, 30, 45, 20)))
WAKE_ONE_TIME_REPLY = _frame(0xAA, 0x12, bytes((1, 100, 7, 15, 0x80, 30)))
WAKE_EVERY_DAY_REPLY = _frame(0xAA, 0x12, bytes((1, 100, 7, 15, 0, 30)))
WAKE_SUBSET_REPLY = _frame(0xAA, 0x12, bytes((1, 100, 7, 15, 0x95, 30)))
LIMIT_REPLY = _frame(0xAA, 0x0E, b"\x01")

CLOCK_WRITE = _frame(0x33, 0x09, bytes((19, 20, 4, 4, 1, 9, 30)))
TIMER_ONE_TIME_WRITE = _frame(0x33, 0x23, bytes.fromhex("0081061e80"))
TIMER_EVERY_DAY_WRITE = _frame(0x33, 0x23, bytes.fromhex("0180160f00"))
TIMER_SUBSET_WRITE = _frame(0x33, 0x23, bytes.fromhex("02810c0095"))
SLEEP_WRITE = _frame(0x33, 0x11, bytes((1, 30, 45, 45)))
WAKE_ONE_TIME_WRITE = _frame(0x33, 0x12, bytes((1, 100, 7, 15, 0x80, 30)))
WAKE_EVERY_DAY_WRITE = _frame(0x33, 0x12, bytes((1, 100, 7, 15, 0, 30)))
WAKE_SUBSET_WRITE = _frame(0x33, 0x12, bytes((1, 100, 7, 15, 0x95, 30)))
LIMIT_WRITE = _frame(0x33, 0x0E, b"\x01")


def _parse(root_type: type[Any], data: bytes) -> Any:
    stream = KaitaiStream(io.BytesIO(data))
    parsed = root_type(stream)
    parsed._read()
    assert stream.pos() == len(data)
    return parsed


def _round_trip(root_type: type[Any], data: bytes) -> Any:
    parsed = _parse(root_type, data)
    parsed._fetch_instances()
    parsed._check()
    output = KaitaiStream(io.BytesIO(bytes(len(data))))
    parsed._write(output)
    assert output.to_byte_array() == data
    return parsed


@pytest.mark.parametrize(
    "data",
    [
        POWER_QUERY,
        BRIGHTNESS_QUERY,
        MODE_QUERY,
        FIRMWARE_QUERY,
        HARDWARE_QUERY,
        LIMIT_QUERY,
        SLEEP_QUERY,
        WAKE_QUERY,
        TIMERS_QUERY,
    ],
)
def test_h6179_queries_round_trip(data: bytes) -> None:
    _round_trip(H6179StatusQuery, data)


def test_h6179_mode_query_candidate_fields() -> None:
    query = _parse(H6179StatusQuery, MODE_QUERY)
    assert query.domain == 0x05
    assert query.body.selector == 0x01
    assert MODE_QUERY == bytes.fromhex("aa050100000000000000000000000000000000ae")


@pytest.mark.parametrize(
    "data",
    [
        POWER_REPLY,
        BRIGHTNESS_REPLY,
        FIRMWARE_REPLY,
        HARDWARE_REPLY,
        STATIC_REPLY,
        TEMPERATURE_REPLY,
        SCENE_REPLY,
        MUSIC_AUTO_REPLY,
        MUSIC_FIXED_REPLY,
        DIY_REPLY,
        TIMERS_REPLY,
        SLEEP_REPLY,
        WAKE_ONE_TIME_REPLY,
        WAKE_EVERY_DAY_REPLY,
        WAKE_SUBSET_REPLY,
        LIMIT_REPLY,
    ],
)
def test_h6179_replies_round_trip(data: bytes) -> None:
    _round_trip(H6179StatusReply, data)


def test_h6179_status_candidate_fields_are_structured() -> None:
    power = _parse(H6179StatusReply, POWER_REPLY)
    brightness = _parse(H6179StatusReply, BRIGHTNESS_REPLY)
    firmware = _parse(H6179StatusReply, FIRMWARE_REPLY)
    hardware = _parse(H6179StatusReply, HARDWARE_REPLY)
    static = _parse(H6179StatusReply, STATIC_REPLY).body.detail
    temperature = _parse(H6179StatusReply, TEMPERATURE_REPLY).body.detail

    assert power.body.is_on
    assert brightness.body.raw_brightness == 0x88
    assert firmware.body.text == "1.00.08"
    assert (hardware.body.selector, hardware.body.text) == (0x03, "1.00.00")
    assert (static.colour.red, static.colour.green, static.colour.blue, static.kelvin) == (0x12, 0x34, 0x56, 0)
    assert (
        temperature.colour.red,
        temperature.colour.green,
        temperature.colour.blue,
        temperature.kelvin,
        temperature.temperature_colour.red,
        temperature.temperature_colour.green,
        temperature.temperature_colour.blue,
    ) == (255, 255, 255, 3000, 255, 177, 112)


def test_h6179_mode_replies_expose_scene_music_and_diy() -> None:
    scene_reply = _parse(H6179StatusReply, SCENE_REPLY).body
    music_auto_reply = _parse(H6179StatusReply, MUSIC_AUTO_REPLY).body
    music_fixed_reply = _parse(H6179StatusReply, MUSIC_FIXED_REPLY).body
    diy_reply = _parse(H6179StatusReply, DIY_REPLY).body
    scene = scene_reply.detail
    music_auto = music_auto_reply.detail
    music_fixed = music_fixed_reply.detail
    diy = diy_reply.detail

    assert (scene_reply.mode, music_auto_reply.mode, music_fixed_reply.mode, diy_reply.mode) == (0x04, 0x0E, 0x0E, 0x0A)
    assert scene.scene_id == 0x10
    assert (music_auto.music_id, music_auto.sensitivity, music_auto.automatic_colour) == (0, 99, True)
    assert not hasattr(music_auto, "fixed_colour")
    assert (music_fixed.music_id, music_fixed.sensitivity, music_fixed.automatic_colour) == (1, 50, False)
    assert (music_fixed.fixed_colour.red, music_fixed.fixed_colour.green, music_fixed.fixed_colour.blue) == (
        0x12,
        0x34,
        0x56,
    )
    assert diy.diy_id == 0x1234


def test_h6179_schedule_replies_expose_four_slots_sleep_wake_and_limit() -> None:
    timers = _parse(H6179StatusReply, TIMERS_REPLY).body
    sleep = _parse(H6179StatusReply, SLEEP_REPLY).body
    wake = _parse(H6179StatusReply, WAKE_EVERY_DAY_REPLY).body
    limit = _parse(H6179StatusReply, LIMIT_REPLY).body

    assert timers.selector == 0xFF
    assert [(slot.is_enabled, slot.turns_on, slot.hour, slot.minute) for slot in timers.slots] == [
        (True, True, 6, 30),
        (True, False, 22, 15),
        (True, True, 12, 0),
        (False, False, 0, 0),
    ]
    assert timers.slots[0].is_one_time
    assert timers.slots[1].repeats_every_day
    assert timers.slots[2].has_explicit_weekdays
    assert timers.slots[2].explicit_weekday_mask == 0x15
    assert (sleep.is_enabled, sleep.start_brightness, sleep.duration_minutes, sleep.remaining_minutes) == (
        True,
        30,
        45,
        20,
    )
    assert (wake.is_enabled, wake.target_brightness, wake.hour, wake.minute, wake.duration_minutes) == (
        True,
        100,
        7,
        15,
        30,
    )
    assert limit.is_enabled


@pytest.mark.parametrize(
    "data",
    [
        CLOCK_WRITE,
        TIMER_ONE_TIME_WRITE,
        TIMER_EVERY_DAY_WRITE,
        TIMER_SUBSET_WRITE,
        SLEEP_WRITE,
        WAKE_ONE_TIME_WRITE,
        WAKE_EVERY_DAY_WRITE,
        WAKE_SUBSET_WRITE,
        LIMIT_WRITE,
    ],
)
def test_h6179_schedule_writes_round_trip(data: bytes) -> None:
    _round_trip(H6179ScheduleWrite, data)


def test_h6179_compact_clock_and_schedule_fields() -> None:
    clock = _parse(H6179ScheduleWrite, CLOCK_WRITE).body
    one_time = _parse(H6179ScheduleWrite, TIMER_ONE_TIME_WRITE).body
    every_day = _parse(H6179ScheduleWrite, TIMER_EVERY_DAY_WRITE).body
    subset = _parse(H6179ScheduleWrite, TIMER_SUBSET_WRITE).body

    assert (clock.hour, clock.minute, clock.second, clock.weekday) == (19, 20, 4, 4)
    assert clock.format_marker == 1
    assert (clock.timezone_hours, clock.timezone_minutes) == (9, 30)
    assert (one_time.slot, one_time.is_enabled, one_time.turns_on, one_time.hour, one_time.minute) == (
        0,
        True,
        True,
        6,
        30,
    )
    assert one_time.is_one_time
    assert every_day.repeats_every_day
    assert subset.has_explicit_weekdays
    assert subset.explicit_weekday_mask == 0x15


def test_h6179_wake_repeat_semantics() -> None:
    reply_one_time = _parse(H6179StatusReply, WAKE_ONE_TIME_REPLY).body
    reply_every_day = _parse(H6179StatusReply, WAKE_EVERY_DAY_REPLY).body
    reply_subset = _parse(H6179StatusReply, WAKE_SUBSET_REPLY).body
    write_one_time = _parse(H6179ScheduleWrite, WAKE_ONE_TIME_WRITE).body
    write_every_day = _parse(H6179ScheduleWrite, WAKE_EVERY_DAY_WRITE).body
    write_subset = _parse(H6179ScheduleWrite, WAKE_SUBSET_WRITE).body

    assert reply_one_time.is_one_time and write_one_time.is_one_time
    assert reply_every_day.repeats_every_day and write_every_day.repeats_every_day
    assert reply_subset.has_explicit_weekdays and write_subset.has_explicit_weekdays
    assert reply_subset.explicit_weekday_mask == write_subset.explicit_weekday_mask == 0x15


def test_h6179_reply_preserves_opaque_bytes() -> None:
    data = _frame(0xAA, 0x01, b"\x01" + bytes.fromhex("102030405060708090a0b0c0d0e0f001"))
    reply = _round_trip(H6179StatusReply, data)
    assert reply.body.opaque == bytes.fromhex("102030405060708090a0b0c0d0e0f001")


@pytest.mark.parametrize(
    "selector",
    [0x00, 0x15, 0x7F],
)
def test_h6179_reply_preserves_unknown_mode_selectors(selector: int) -> None:
    detail = bytes.fromhex("102030405060708090a0b0c0d0e0f001")
    reply = _round_trip(H6179StatusReply, _frame(0xAA, 0x05, bytes((selector,)) + detail))
    assert reply.body.mode == selector
    assert reply.body.detail == detail


@pytest.mark.parametrize(
    "data",
    [
        _frame(0xAA, 0xA5, b"\x01"),
        _frame(0xAA, 0xAE, b"\x01"),
    ],
)
def test_h6179_reply_preserves_unknown_domains(data: bytes) -> None:
    reply = _round_trip(H6179StatusReply, data)
    assert reply.body == data[2:19]


@pytest.mark.parametrize(
    "data",
    [
        _frame(0xAA, 0x05, b"\x00"),
        _frame(0xAA, 0xA5, b"\x01"),
        _frame(0xAA, 0xAE, b"\x01"),
    ],
)
def test_h6179_query_preserves_unknown_domains_and_selectors(data: bytes) -> None:
    query = _round_trip(H6179StatusQuery, data)
    if query.domain in {0xA5, 0xAE}:
        assert query.body == data[2:19]
    else:
        assert query.body.selector == 0
        assert query.body.opaque == bytes(16)


@pytest.mark.parametrize(
    "data",
    [
        _frame(0x33, 0x09, bytes((24, 0, 0, 1, 1, 0, 0))),
        _frame(0x33, 0x09, bytes((0, 60, 0, 1, 1, 0, 0))),
        _frame(0x33, 0x09, bytes((0, 0, 60, 1, 1, 0, 0))),
        _frame(0x33, 0x09, bytes((0, 0, 0, 0, 1, 0, 0))),
        _frame(0x33, 0x09, bytes((0, 0, 0, 1, 1, 0, 60))),
        _frame(0x33, 0x23, bytes.fromhex("0081180080")),
        _frame(0x33, 0x23, bytes.fromhex("0081003c80")),
        _frame(0x33, 0x23, bytes.fromhex("0081000015")),
        _frame(0x33, 0x11, bytes((1, 101, 45, 45))),
        _frame(0x33, 0x12, bytes((1, 101, 7, 15, 0, 30))),
        _frame(0x33, 0x12, bytes((1, 100, 24, 15, 0, 30))),
        _frame(0x33, 0x12, bytes((1, 100, 7, 60, 0, 30))),
    ],
)
def test_h6179_schedule_writes_preserve_uncertain_values(data: bytes) -> None:
    _round_trip(H6179ScheduleWrite, data)


def test_h6179_schedule_preserves_unknown_operation_and_opaque_tail() -> None:
    body = bytes.fromhex("102030405060708090a0b0c0d0e0f00102")
    unknown = _round_trip(H6179ScheduleWrite, _frame(0x33, 0x7F, body))
    assert unknown.body == body

    limit = _round_trip(H6179ScheduleWrite, _frame(0x33, 0x0E, b"\x02" + bytes.fromhex("102030")))
    assert limit.body.is_enabled == 2
    assert limit.body.opaque == bytes.fromhex("102030") + bytes(13)
