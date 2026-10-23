"""Reporter fork f8d4267 literals plus explicitly synthetic H60A protocol audits."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError
from homeassistant.exceptions import ServiceValidationError

from custom_components.ha_govee_led_ble.const import ReadDomain, device_profile
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode
from custom_components.ha_govee_led_ble.effect_deployments import PriorControlState
from custom_components.ha_govee_led_ble.effect_runtime import async_prepare_effect_control_state
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    BulkStatusCollector,
    ProtocolParseRejection,
    build_boolean_control,
    build_brightness,
    build_bulk_status_query,
    build_colour_mode_query,
    build_power,
    build_power_on_behaviour,
    build_power_query,
    build_segment_brightness,
    build_segment_query,
    parse_status_result,
    require_profile_packet,
)
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.light_commands import (
    build_color_temp,
    build_segment_color,
    build_segment_color_temp,
    kelvin_to_rgb,
)
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


def bulk_frames(payload: bytes) -> list[bytes]:
    if len(payload) <= 12:
        return [frame(f"ac000100{len(payload):02x}0300" + payload.hex())]
    chunks = [payload[index : index + 17] for index in range(12, len(payload), 17)]
    first = frame(f"ac00{len(chunks) + 1:02x}00{len(chunks[-1]):02x}0300" + payload[:12].hex())
    return [
        first,
        *(
            frame(f"ac{255 if index == len(chunks) else index:02x}" + chunk.hex())
            for index, chunk in enumerate(chunks, 1)
        ),
    ]


def test_bulk_direct_selector_and_atomic_reassembly():
    single = frame("ac0001000503000503046300")
    result = BulkStatusCollector().feed(single)
    assert result.parsed.records[0].body.detail.scene_id == 99
    payload = bytes.fromhex("fe14000102030405060708090a0b0c0d0e0f1011121305030afe00")
    packets = bulk_frames(payload)
    collector = BulkStatusCollector()
    assert collector.feed(packets[0]).parsed is None
    result = collector.feed(packets[1])
    assert result.parsed.records[0].body == bytes(range(20))
    assert result.parsed.records[1].body.detail.code == 254
    for malformed in (
        [packets[1], *packets],
        [packets[0], packets[0], packets[1]],
        bulk_frames(bytes.fromhex("05030463000503046300")),
        bulk_frames(bytes.fromhex("0505046300")),
    ):
        collector = BulkStatusCollector()
        for packet in malformed:
            result = collector.feed(packet)
        assert result.parsed is None and collector.failed


@pytest.mark.parametrize("model", ["H60A1", "H60A6"])
def test_bulk_and_native_setting_admission_are_independent_of_geometry(model):
    profile = qualified(model)
    query = build_colour_mode_query(model, profile=profile)
    require_profile_packet(query, profile)
    assert query[:2] == b"\xac\x03"
    assert model != "H60A1" or query == frame("ac0300")
    if model == "H60A6":
        legacy = device_profile(model, 1, 1)
        assert legacy.segment_count == 1
        for setting in ("panel_enabled", "ring_enabled"):
            packet = build_boolean_control(setting, False, model, profile=legacy)
            require_profile_packet(packet, legacy)
            with pytest.raises(ValueError):
                require_profile_packet(packet, device_profile(model, 1, 4))
        assert build_power_on_behaviour("off", legacy) == frame("33410202")
        require_profile_packet(build_bulk_status_query(legacy, domains=("zone_enable",)), legacy)
    else:
        with pytest.raises(ValueError):
            build_boolean_control("ring_enabled", False, model, profile=profile)


@pytest.mark.parametrize("model", ["H60A1", "H60A6"])
async def test_bulk_updates_only_complete_state_and_zone_flags_are_independent(hass, model):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", model, configuration_url=None)
    c.hw_version, c.fw_version = "1.04.03", "1.02.20" if model == "H60A1" else "1.00.41"
    c._resolve_device_profile()
    c._bulk_collector = BulkStatusCollector()
    c._bulk_query_incomplete = True
    payload = bytes.fromhex("fe0c000102030405060708090a0b0503046300300200814102aa02")
    packets = bulk_frames(payload)
    c._notify_callback(None, bytearray(packets[0]))
    assert c.color_mode is None and not c.boolean_control_state
    c._notify_callback(None, bytearray(packets[1]))
    assert c.color_mode is ParsedMode.SCENE and c.scene_code == 99
    assert not c._bulk_query_incomplete
    assert c.boolean_control_state == ({"panel_enabled": False, "ring_enabled": True} if model == "H60A6" else {})
    assert c.power_on_behaviour == ("off" if model == "H60A6" else None)
    if model == "H60A6":
        c._notify_callback(None, bytearray(frame("ee3001018001")))
        assert c.is_on and c.boolean_control_state == {"panel_enabled": False, "ring_enabled": True}
        c._notify_callback(None, bytearray(frame("aa0100")))
        assert not c.is_on and c.boolean_control_state["ring_enabled"]


async def test_invalid_complete_bulk_does_not_publish_earlier_valid_records(hass):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H60A6", configuration_url=None)
    c._bulk_collector = BulkStatusCollector()
    c._bulk_query_incomplete = True
    before = c.capture_effect_control_state()
    for packet in bulk_frames(bytes.fromhex("010101300200014102aa03")):
        c._notify_callback(None, bytearray(packet))
    assert c.capture_effect_control_state() == before
    assert not c._field_revisions and c._bulk_query_incomplete
    assert c.packet_log[-1]["reason"] == "semantic_rejected"


@pytest.mark.parametrize("outcome", ["timeout", "expired", "cancelled", "write_error"])
async def test_abandoned_bulk_query_rejects_late_status_until_reconnect(hass, monkeypatch, outcome):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H60A6", configuration_url=None)
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    c._client = client
    prior = c.capture_effect_control_state()
    packets = bulk_frames(bytes.fromhex("010101050304630030020001"))

    async def wait(*_args):
        if outcome == "cancelled":
            raise asyncio.CancelledError
        if outcome == "expired":
            c._bulk_query_deadline = time.monotonic() - 1
            for packet in packets:
                c._notify_callback(None, bytearray(packet))
        return False

    monkeypatch.setattr(c, "_wait_for_revisions", wait)
    if outcome == "write_error":
        client.write_gatt_char.side_effect = BleakError("write failed")
    if outcome in {"cancelled", "write_error"}:
        with pytest.raises(asyncio.CancelledError if outcome == "cancelled" else BleakError):
            await c._async_read_bulk_status(client, domains=(), deadline=time.monotonic() + 10)
    else:
        assert not await c._async_read_bulk_status(client, domains=(), deadline=time.monotonic() + 10)
    assert c._bulk_collector is None
    for packet in packets:
        c._notify_callback(None, bytearray(packet))
    assert c._bulk_query_incomplete and not c._field_revisions
    assert c.capture_effect_control_state() == prior
    with pytest.raises(BleakError, match="Incomplete bulk query"):
        await c._async_write_packet(client, build_power(False, c.model), arm_expected=True)


@pytest.mark.parametrize("model", ["H60A1", "H60A6"])
@pytest.mark.parametrize("previous", ["diy", "scene"])
async def test_generic_music_observation_replaces_previous_effect_without_inventing_submode(hass, model, previous):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", model, configuration_url=None)
    for payload in (
        bytes.fromhex("0101010503" + ("0afe00" if previous == "diy" else "046300")),
        bytes.fromhex("050113"),
    ):
        c._bulk_collector = BulkStatusCollector()
        for packet in bulk_frames(payload):
            c._notify_callback(None, bytearray(packet))
    assert c.color_mode is ParsedMode.MUSIC
    assert c.active_mode == c.capture_effect_control_state().mode == "music"
    assert c.diy_code is c.scene_code is c.effect is c.unknown_scene_code is None
    assert c.music_mode == "off" and "music_mode" not in c._field_revisions


@pytest.mark.parametrize("flags", [None, "fresh", "retained"])
async def test_native_preview_requires_fresh_zone_flags_even_for_scene_mode(hass, flags):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H60A6", configuration_url=None)
    c.hw_version, c.fw_version = "1.04.03", "1.00.41"
    c._resolve_device_profile()
    c.color_mode, c._scene_code = ParsedMode.SCENE, 99
    c._notify_started_monotonic = time.monotonic()
    if flags is not None:
        c._notify_callback(None, bytearray(frame("ee3001010001")))
        if flags == "retained":
            c._notify_started_monotonic = time.monotonic() + 1
    if flags == "fresh":
        assert await async_prepare_effect_control_state(c, require_restorable_static=True)
        c.color_mode, c._scene_code = ParsedMode.MUSIC, None
        with pytest.raises(RuntimeError, match="music mode"):
            await async_prepare_effect_control_state(c, require_restorable_static=True)
    else:
        with pytest.raises(RuntimeError, match="panel and ring"):
            await async_prepare_effect_control_state(c, require_restorable_static=True)


@pytest.mark.parametrize("required_segments", [False, True])
async def test_optional_bulk_timeout_preserves_power_but_blocks_abandoned_subscription(
    hass, monkeypatch, required_segments
):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H60A6", configuration_url=None)
    c.hw_version, c.fw_version = "1.04.03", "1.00.41"
    c._resolve_device_profile()
    c._confirmed_identity_fields.update(c.profile.profile_identity_fields)
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    c._client = client

    async def respond(_uuid, packet, **kwargs):
        if packet == build_power_query(c.model, profile=c.profile):
            c._notify_callback(None, bytearray(POWER))

    client.write_gatt_char.side_effect = respond
    monkeypatch.setattr(c, "_wait_for_revisions", AsyncMock(return_value=False))
    required = frozenset({ReadDomain.POWER} | ({ReadDomain.SEGMENTS} if required_segments else set()))
    assert await c._send_state_queries(required_domains=required) is not required_segments
    assert c.is_on and c._field_revisions["is_on"] > 0
    assert c._bulk_query_incomplete
    with pytest.raises(BleakError, match="Incomplete bulk query"):
        await c._async_write_packet(client, build_power(False, c.model), arm_expected=True)
    calls = client.write_gatt_char.await_count
    assert not await c._send_state_queries(required_domains=required)
    assert client.write_gatt_char.await_count == calls


@pytest.mark.parametrize("source", ["synchronous", "bulk", "mismatch"])
async def test_native_zone_write_requires_its_fresh_independent_flag(hass, monkeypatch, source):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H60A6", configuration_url=None)
    c.hw_version, c.fw_version = "1.04.03", "1.00.41"
    c._resolve_device_profile()
    c._confirmed_identity_fields.update(c.profile.profile_identity_fields)
    c._notify_started_monotonic = time.monotonic()
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    c._client = client
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(c, "_renew_foreground_lease", lambda: None)
    panel_flag = "01" if source == "mismatch" else "00"

    async def respond(_uuid, packet, **kwargs):
        if packet == build_boolean_control("panel_enabled", False, c.model, profile=c.profile):
            if source != "bulk":
                c._notify_callback(None, bytearray(frame(f"ee300100{panel_flag}01")))
        elif packet == build_bulk_status_query(c.profile, domains=("zone_enable",)):
            c._notify_callback(None, bytearray(bulk_frames(bytes.fromhex("30020001"))[0]))

    client.write_gatt_char.side_effect = respond
    if source == "mismatch":
        with pytest.raises(ValueError, match="did not confirm"):
            await c.async_set_boolean_control("panel_enabled", False)
    else:
        await c.async_set_boolean_control("panel_enabled", False)
    sent = [call.args[1] for call in client.write_gatt_char.await_args_list]
    assert len(sent) == (2 if source == "bulk" else 1)
    assert not c.is_on and c.boolean_control_state["ring_enabled"]
    prior = c.capture_effect_control_state()
    assert prior.panel_enabled is (source == "mismatch") and prior.ring_enabled is True
    c._clear_client_state(client)
    assert c.capture_effect_control_state().panel_enabled is None


@pytest.mark.parametrize("known", [False, True])
async def test_recovery_restores_only_known_native_flags_without_changing_master_power(hass, monkeypatch, known):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H60A6", configuration_url=None)
    c.hw_version, c.fw_version = "1.04.03", "1.00.41"
    c._resolve_device_profile()
    c._confirmed_identity_fields.update(c.profile.profile_identity_fields)
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    c._client = client
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(c, "_renew_foreground_lease", lambda: None)
    monkeypatch.setattr(c, "_async_restore_effect_appearance", AsyncMock(return_value=True))
    flags = {"panel_enabled": True, "ring_enabled": False}

    async def respond(_uuid, packet, **kwargs):
        if packet == build_bulk_status_query(c.profile, domains=("zone_enable",)):
            c._notify_callback(None, bytearray(bulk_frames(bytes.fromhex("30020100"))[0]))
        else:
            for name in flags:
                if packet == build_boolean_control(name, not flags[name], c.model, profile=c.profile):
                    flags[name] = not flags[name]
                    c._notify_callback(
                        None,
                        bytearray(frame(f"ee300100{int(flags['panel_enabled']):02x}{int(flags['ring_enabled']):02x}")),
                    )
                    break

    client.write_gatt_char.side_effect = respond
    state = PriorControlState(
        "scene", False, 50, (1, 2, 3), panel_enabled=False if known else None, ring_enabled=True if known else None
    )
    assert await c.async_restore_effect_control_state(state, overwritten_diy_code=None) is known
    assert not c.is_on
    if known:
        assert c.boolean_control_state == {"panel_enabled": False, "ring_enabled": True}
        assert client.write_gatt_char.await_count == 3
    else:
        client.write_gatt_char.assert_not_awaited()


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
    c._confirmed_identity_fields.update(c.profile.profile_identity_fields)
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
    replies[build_colour_mode_query(model, profile=c.profile)] = bulk_frames(bytes.fromhex("050415000000"))[0]

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
        frame("33051305"),
    ):
        with pytest.raises(ValueError):
            await c._async_write_packet(client, packet, arm_expected=True)
    assert client.write_gatt_char.await_count == calls and c.capture_effect_control_state() == before
    kelvin_packet = build_color_temp(4000, model, profile=c.profile)
    require_profile_packet(kelvin_packet, c.profile)
    light = GoveeBLELight(c)
    light.async_write_ha_state = MagicMock()
    c.is_on = True
    await light.async_turn_on(color_temp_kelvin=4000)
    assert client.write_gatt_char.await_args.args[1] == kelvin_packet
    assert light.color_temp_kelvin == 4000
    assert c.segment_colors == [kelvin_to_rgb(4000)] * c.profile.segment_count
    companion_hex = bytes((100, *kelvin_to_rgb(4000))).hex()
    replies.update(
        {
            build_segment_query(group, model, profile=c.profile): frame(f"aaa5{group:02x}" + companion_hex * 4)
            for group in range(1, 5)
        }
    )
    assert await c.async_refresh_segments(timeout=0.1)
    assert light.color_temp_kelvin == 4000
    if model == "H60A6":
        seg_packet = build_segment_color_temp([13], 6500, model, profile=c.profile)
        require_profile_packet(seg_packet, c.profile)
        panel_hex = bytes((100, *kelvin_to_rgb(6500))).hex()
        replies[build_segment_query(4, model, profile=c.profile)] = frame("aaa504" + panel_hex)
        await light.async_set_segment_color_temp([13], 6500)
        assert c.segment_colors[12] == kelvin_to_rgb(6500)
        assert c.segment_colors[:12] == [kelvin_to_rgb(4000)] * 12
    else:
        with pytest.raises(ValueError, match="segment colour temperature"):
            build_segment_color_temp([14], 6500, model, profile=c.profile)
        with pytest.raises(ServiceValidationError):
            await light.async_set_segment_color_temp([14], 6500)


@pytest.mark.parametrize("model", ["H60A1", "H60A6"])
async def test_missing_final_page_cannot_promote_partial_segment_state(hass, monkeypatch, model):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", model, configuration_url=None)
    c.hw_version, c.fw_version = "1.04.03", "1.02.20" if model == "H60A1" else "1.00.41"
    c._resolve_device_profile()
    c._confirmed_identity_fields.update(c.profile.profile_identity_fields)
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
