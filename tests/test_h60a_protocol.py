"""Reporter fork f8d4267 literals plus explicitly synthetic H60A protocol audits."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ha_govee_led_ble.const import ReadDomain, device_profile
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_status import decode_status_frame
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    ProtocolParseRejection,
    build_brightness,
    build_firmware_query,
    build_hardware_query,
    build_power_query,
    build_segment_brightness,
    build_segment_query,
    parse_status_result,
    require_profile_packet,
)
from custom_components.ha_govee_led_ble.light_commands import build_color_temp, build_segment_color
from custom_components.ha_govee_led_ble.transport import xor_checksum

CAPTURED_PAGES = {
    "H60A6": {
        "aaa501640000ff640000ff640000ff640000ff0e": [(100, (0, 0, 255))] * 4,
        "aaa50464ffd5a1000000000000000000000000e4": [(100, (255, 213, 161))],
    },
    "H60A1": {
        "aaa504640000ff64ff6d55000000000000000033": [(100, (0, 0, 255)), (100, (255, 109, 85))],
    },
}
POWER = bytes.fromhex("aa010100000000000000000000000000000000aa")


def frame(prefix: str) -> bytes:
    """Synthetic frame helper; the captured literals above never pass through it."""
    body = bytes.fromhex(prefix).ljust(19, b"\x00")
    assert len(body) == 19
    return body + bytes([xor_checksum(body)])


def qualified(model):
    return device_profile(model, None, None, hardware="1.04.03", firmware="1.02.20" if model == "H60A1" else "1.00.41")


@pytest.mark.parametrize(
    ("model", "hex_frame", "records"),
    [(model, packet, records) for model, pages in CAPTURED_PAGES.items() for packet, records in pages.items()],
)
def test_captured_pages_keep_exact_cardinality(model, hex_frame, records):
    parsed = parse_status_result(bytes.fromhex(hex_frame), model).parsed
    assert parsed is not None and parsed.body.num_segments == len(records)
    assert [(r.brightness, (r.colour.red, r.colour.green, r.colour.blue)) for r in parsed.body.segments] == records


@pytest.mark.parametrize("model", ["H60A1", "H60A6"])
def test_power_query_panel_rgb_and_complete_read_root(model):
    profile = qualified(model)
    assert parse_status_result(POWER, model).parsed.body.is_on == 1
    assert build_segment_query(1, model, profile=profile).hex() == "aaa501000000000000000000000000000000000e"
    panel = build_segment_color([profile.segment_count], 255, 0, 0, model, profile=profile)
    require_profile_packet(panel, profile)
    if model == "H60A6":
        assert panel.hex() == "33051501ff0000000000000000100000000000cd"
    # Identity prefixes are STATIC DERIVED, not reporter captures.
    firmware = frame("aa06" + b"1.00.41\x00".hex())
    hardware = frame("aa0703" + b"1.04.03\x00".hex())
    statuses = {
        ReadDomain.POWER: POWER,
        ReadDomain.FIRMWARE: firmware,
        ReadDomain.HARDWARE: hardware,
        ReadDomain.SEGMENTS: bytes.fromhex(next(iter(CAPTURED_PAGES[model]))),
    }
    assert profile.read_domains == statuses.keys()
    for domain, packet in statuses.items():
        assert decode_status_frame(packet, model, profile=profile).domain is domain
    for builder in (build_power_query, build_firmware_query, build_hardware_query):
        require_profile_packet(builder(model, profile=profile), profile)


@pytest.mark.parametrize("model", ["H60A1", "H60A6"])
def test_unused_slots_opaque_black_records_real_and_bad_frames_rejected(model):
    profile = qualified(model)
    count = profile.segment_count - 12
    packet = frame("aaa504" + "00000000" * count + "deadc0de" * (4 - count))
    body = parse_status_result(packet, model).parsed.body
    assert body.num_segments == count and len(body.segments) == count
    assert body.unused == list(bytes.fromhex("deadc0de" * (4 - count)))
    assert all(record.brightness == 0 for record in body.segments)
    for group in (0, 5):
        assert parse_status_result(frame(f"aaa5{group:02x}"), model).rejection is ProtocolParseRejection.SCHEMA_REJECTED
    assert parse_status_result(POWER[:-1], model).rejection is ProtocolParseRejection.INVALID_LENGTH
    assert parse_status_result(POWER[:-1] + b"\x00", model).rejection is ProtocolParseRejection.INVALID_CHECKSUM


@pytest.mark.parametrize("model", ["H60A1", "H60A6"])
async def test_coordinator_real_pages_panel_brightness_and_no_false_verification(hass, monkeypatch, model):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", model, configuration_url=None)
    c.hw_version, c.fw_version = "1.04.03", "1.02.20" if model == "H60A1" else "1.00.41"
    c._resolve_device_profile()
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    c._client = client
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(c, "_renew_foreground_lease", lambda: None)
    pages = {int(packet[4:6], 16): bytes.fromhex(packet) for packet in CAPTURED_PAGES[model]}
    # Fill only missing pages with synthetic blue records. Page four remains
    # the literal owner reply, including its distinct panel colour.
    pages.update({group: frame(f"aaa5{group:02x}" + "640000ff" * 4) for group in range(1, 4) if group not in pages})
    replies = {build_power_query(model): POWER} | {
        build_segment_query(group, model, profile=c.profile): packet for group, packet in pages.items()
    }

    async def respond(_uuid, packet, **kwargs):
        if packet in replies:
            c._notify_callback(None, bytearray(replies[packet]))

    client.write_gatt_char.side_effect = respond
    c._notify_callback(None, bytearray(pages[4]))
    assert c.segment_state_source == "initial" and c._field_revisions.get("segment_colors", 0) == 0
    assert await c.async_refresh_segments(timeout=0.1)
    assert c.segment_state_source == "observed" and len(c.segment_colors) == c.profile.segment_count
    assert c.segment_colors[-1] == CAPTURED_PAGES[model][next(reversed(CAPTURED_PAGES[model]))][-1][1]
    assert c.color_temp_kelvin is None
    client.write_gatt_char.reset_mock()
    await c._send_state_queries()
    sent = [call.args[1] for call in client.write_gatt_char.await_args_list]
    assert set(sent) == replies.keys()
    assert not any(packet[1] in (4, 5) for packet in sent)
    await c._async_write_packet(
        client, build_brightness(50, model), arm_expected=True, state_values={"brightness_pct": 50}
    )
    assert c.brightness_pct == 50 and "brightness_pct" not in c._field_revisions
    before = c.capture_effect_control_state()
    # Unsolicited brightness/mode and command echoes cannot prove rendered state.
    for packet in (frame("aa0401"), frame("aa051501"), build_brightness(50, model)):
        c._notify_callback(None, bytearray(packet))
    assert c.capture_effect_control_state() == before
    assert not await c.refresh_state(expected_brightness=50, timeout=0.01)
    calls = client.write_gatt_char.await_count
    for packet in (
        build_segment_brightness(c.profile.whole_device_mask, 20, model),
        frame("330504814a"),
        frame("33051305"),
    ):
        with pytest.raises(ValueError):
            await c._async_write_packet(client, packet, arm_expected=True)
    assert client.write_gatt_char.await_count == calls and c.capture_effect_control_state() == before
    with pytest.raises(ValueError, match="colour temperature"):
        build_color_temp(4000, model, profile=c.profile)


@pytest.mark.parametrize("model", ["H60A1", "H60A6"])
async def test_missing_final_page_cannot_promote_partial_segment_state(hass, monkeypatch, model):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", model, configuration_url=None)
    c.hw_version, c.fw_version = "1.04.03", "1.02.20" if model == "H60A1" else "1.00.41"
    c._resolve_device_profile()
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    c._client = client
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(c, "_renew_foreground_lease", lambda: None)
    replies = {
        build_segment_query(group, model, profile=c.profile): frame(f"aaa5{group:02x}" + "64ff0000" * 4)
        for group in range(1, 4)
    }

    async def respond(_uuid, packet, **kwargs):
        if packet in replies:
            c._notify_callback(None, bytearray(replies[packet]))

    client.write_gatt_char.side_effect = respond
    before = list(c.segment_colors)
    assert not await c.async_refresh_segments(timeout=0.01)
    assert c.segment_colors == before and c.segment_state_source == "initial"
    assert c._field_revisions.get("segment_colors", 0) == 0
    assert c._segment_query_incomplete
