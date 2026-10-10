"""H601C Android 7.6.01 STATIC DERIVED vectors; none are BLE captures."""

from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.light import ColorMode
from homeassistant.exceptions import HomeAssistantError

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, ModelProfile, ReadDomain
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_expectations import expectations_from_packet
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode, decode_status_frame, parse_color_mode
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    ProtocolParseRejection,
    build_brightness,
    build_brightness_query,
    build_colour_mode_query,
    build_firmware_query,
    build_hardware_query,
    build_power,
    build_power_query,
    build_segment_colour,
    parse_command_result,
    parse_status_result,
    require_profile_packet,
)
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.light_commands import (
    build_color_rgb,
    build_color_temp,
    build_segment_color,
    parse_static_write,
)
from custom_components.ha_govee_led_ble.transport import xor_checksum

PROFILE = ModelProfile(
    "Synthetic H601C basic protocol",
    command_grammar="H601C",
    status_grammar="H601C",
    command_operations=frozenset({"power", "brightness", "static"}),
    read_domains=frozenset(
        {ReadDomain.POWER, ReadDomain.BRIGHTNESS, ReadDomain.COLOUR_MODE, ReadDomain.FIRMWARE, ReadDomain.HARDWARE}
    ),
    supports_rgb=True,
    supports_color_temperature=True,
    min_color_temp_kelvin=2700,
    max_color_temp_kelvin=6500,
    static_readback_echoes_color=True,
    static_readback_kelvin=True,
    static_readback_zero_kelvin_is_rgb=True,
    whole_device_mask=1,
)


def frame(prefix: str) -> bytes:
    body = bytes.fromhex(prefix).ljust(19, b"\x00")
    assert len(body) == 19
    return body + bytes([xor_checksum(body)])


@pytest.mark.parametrize(
    ("kelvin", "hex_packet"),
    [
        (None, "33050dff000000000000000000000000000000c4"),
        (2700, "33050dffffff0a8cffae54000000000000000047"),
        (6500, "33050dffffff1964fff9fb000000000000000044"),
    ],
)
def test_static_derived_vectors_and_expectations(kelvin, hex_packet):
    packet = (
        build_color_rgb(255, 0, 0, profile=PROFILE) if kelvin is None else build_color_temp(kelvin, profile=PROFILE)
    )
    assert packet.hex() == hex_packet
    require_profile_packet(packet, PROFILE)
    parsed = parse_static_write(packet, profile=PROFILE)
    assert parsed is not None and parsed.whole_strip and parsed.kelvin == kelvin
    expected = expectations_from_packet(packet, profile=PROFILE, static_echoes_color=True)
    assert expected["color_mode"] == (ParsedMode.COLOUR, None)
    if kelvin is None:
        assert expected["rgb_color"] == (255, 0, 0) and expected["color_temp_kelvin"] is None
    else:
        assert "rgb_color" not in expected and expected["color_temp_kelvin"] == kelvin


def test_complete_supported_lookup_and_unknown_companion():
    # Independently transcribed first entries of the ordered Constant.java map.
    companions = (
        "ffae54 ffb25b ffb662 ffb969 ffbd6f ffc076 ffc37c ffc682 ffc987 ffcb8d "
        "ffce92 ffd097 ffd39c ffd5a1 ffd7a6 ffd9ab ffdbaf ffddb4 ffdfb8 ffe1bc "
        "ffe2c0 ffe4c4 ffe5c8 ffe7cc ffe8d0 ffead3 ffebd7 ffedda ffeede ffefe1 "
        "fff0e4 fff1e7 fff3ea fff4ed fff5f0 fff6f3 fff7f7 fff8f8 fff9fb"
    ).split()
    assert len(companions) == 39
    for kelvin, companion in zip(range(2700, 6501, 100), companions, strict=True):
        packet = build_color_temp(kelvin, profile=PROFILE)
        assert packet[3:6] == bytes.fromhex("ffffff")
        assert packet[6:8] == kelvin.to_bytes(2, "big")
        assert packet[8:11].hex() == companion
    with pytest.raises(ValueError, match="100 K steps"):
        build_color_temp(2750, profile=PROFILE)
    assert build_color_temp(1000, profile=PROFILE) == build_color_temp(2700, profile=PROFILE)
    assert build_color_temp(9000, profile=PROFILE) == build_color_temp(6500, profile=PROFILE)


def test_queries_identity_and_complete_status_root():
    queries = (
        (build_power_query, "aa01"),
        (build_brightness_query, "aa04"),
        (build_colour_mode_query, "aa0501"),
        (build_firmware_query, "aa06"),
        (build_hardware_query, "aa0703"),
    )
    for builder, prefix in queries:
        packet = builder("H9901", profile=PROFILE)
        assert packet == frame(prefix)
        require_profile_packet(packet, PROFILE)
        assert expectations_from_packet(packet, profile=PROFILE) == {}
    assert build_colour_mode_query(profile=PROFILE).hex() == "aa050100000000000000000000000000000000ae"
    for builder, prefix in ((build_power, "330101"), (build_brightness, "330432")):
        packet = builder(True if builder is build_power else 50, profile=PROFILE)
        assert packet == frame(prefix)
        require_profile_packet(packet, PROFILE)
    statuses = {
        ReadDomain.POWER: "aa0101",
        ReadDomain.BRIGHTNESS: "aa0432",
        ReadDomain.COLOUR_MODE: "aa050dff00000000000000",
        ReadDomain.FIRMWARE: "aa06312e30302e303000",
        ReadDomain.HARDWARE: "aa0703312e30302e303100",
    }
    assert PROFILE.read_domains == statuses.keys()
    for domain, prefix in statuses.items():
        decoded = decode_status_frame(frame(prefix), profile=PROFILE)
        assert decoded is not None and decoded.domain == domain
    assert parse_status_result(frame(statuses[ReadDomain.HARDWARE]), profile=PROFILE).parsed.body.text == "1.00.01"


def test_opaque_modes_tails_and_malformed_envelopes():
    generated = parse_status_result(frame("aa050dffffff0fa0ffd5a10102030405060708"), profile=PROFILE).parsed
    assert generated.body.detail.unknown_tail == bytes(range(1, 9))
    assert generated.body.detail.companion_rgb.green == 213
    semantic = parse_color_mode(generated, "H9901", profile=PROFILE)
    assert semantic.color_temp_kelvin == 4000 and semantic.rgb_color is None
    unknown = parse_status_result(frame("aa05ee1234"), profile=PROFILE).parsed
    assert unknown.body.detail.startswith(bytes.fromhex("1234"))
    assert parse_color_mode(unknown, "H9901", profile=PROFILE).mode is ParsedMode.UNKNOWN
    assert parse_status_result(frame("aa0102"), profile=PROFILE).parsed.body.is_on == 2
    assert parse_status_result(frame("aa0465"), profile=PROFILE).parsed.body.brightness_pct == 101
    for prefix in ("ab0101", "aa07023100"):
        assert parse_status_result(frame(prefix), profile=PROFILE).rejection is ProtocolParseRejection.SCHEMA_REJECTED
    valid = frame("aa0101")
    assert parse_status_result(valid[:-1], profile=PROFILE).rejection is ProtocolParseRejection.INVALID_LENGTH
    assert parse_status_result(valid + b"\x00", profile=PROFILE).rejection is ProtocolParseRejection.INVALID_LENGTH
    assert (
        parse_status_result(valid[:-1] + bytes([valid[-1] ^ 1]), profile=PROFILE).rejection
        is ProtocolParseRejection.INVALID_CHECKSUM
    )
    for prefix in ("33010101", "33050dff0000000000000001", "330102", "330465"):
        assert parse_command_result(frame(prefix), profile=PROFILE).rejection is ProtocolParseRejection.SCHEMA_REJECTED
    for prefix in ("330504", "330513", "3305ee", "a30200", "aaa501", "33a301", "33050dffffff1965"):
        with pytest.raises(ValueError):
            require_profile_packet(frame(prefix), PROFILE)
    with pytest.raises(ValueError, match="per-segment"):
        build_segment_color([1], 1, 2, 3, profile=PROFILE)
    with pytest.raises(ValueError, match="whole-device"):
        build_segment_colour(2, 1, 2, 3, profile=PROFILE)
    with pytest.raises(ValueError):
        require_profile_packet(
            build_color_rgb(1, 2, 3, profile=PROFILE), replace(PROFILE, command_operations=frozenset({"power"}))
        )


@pytest.fixture
def device(hass, monkeypatch):
    monkeypatch.setitem(MODEL_PROFILES, "H9901", PROFILE)
    device = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H9901", configuration_url="test")
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    device._client = client
    monkeypatch.setattr(device, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(device, "_renew_foreground_lease", lambda: None)
    return device


async def test_real_coordinator_queries_static_state_and_fresh_verification(device):
    replies = {
        build_power_query(profile=PROFILE): "aa0101",
        build_brightness_query(profile=PROFILE): "aa0432",
        build_colour_mode_query(profile=PROFILE): "aa050dffffff0fa0ffd5a1",
    }

    async def respond(_uuid, packet, **kwargs):
        if packet in replies:
            device._notify_callback(None, bytearray(frame(replies[packet])))

    device._client.write_gatt_char.side_effect = respond
    await device._send_state_queries(query_segments=False)
    assert [call.args[1] for call in device._client.write_gatt_char.await_args_list] == list(replies)
    assert device.is_on and device.brightness_pct == 50 and device.color_temp_kelvin == 4000
    assert device.color_temp_kelvin_source == "observed"
    assert await device.refresh_state(expected_color_temp_kelvin=4000, timeout=0.01)
    # Complete but mismatched readback is not successful verification.
    assert not await device.refresh_state(expected_color_temp_kelvin=5000, timeout=0.01)


async def test_real_writer_expectations_rgb_kelvin_transition_and_rejections(device):
    packet = build_color_temp(4000, profile=PROFILE)
    await device._async_write_packet(device._client, packet, arm_expected=True)
    assert device.color_temp_kelvin == 4000 and device.color_temp_kelvin_source == "optimistic"
    assert device._field_revisions == {}
    device._notify_callback(None, bytearray(frame("aa050dffffff0fa0ffd5a1")))
    assert device.color_temp_kelvin_source == "observed"
    rgb = build_color_rgb(255, 0, 0, profile=PROFILE)
    await device._async_write_packet(device._client, rgb, arm_expected=True)
    device._notify_callback(None, bytearray(frame("aa050dff00000000000000")))
    assert device.rgb_color == (255, 0, 0) and device.rgb_color_source == "observed"
    assert device.color_temp_kelvin is None and device.color_temp_kelvin_source == "observed"
    before = device.capture_effect_control_state()
    revisions = dict(device._field_revisions)
    device._notify_callback(None, bytearray(frame("aa050dffffff1965")))
    assert device.capture_effect_control_state() == before and device._field_revisions == revisions
    calls = device._client.write_gatt_char.await_count
    with pytest.raises(ValueError):
        await device._async_write_packet(device._client, frame("330504"), arm_expected=True)
    assert device._client.write_gatt_char.await_count == calls
    assert device.capture_effect_control_state() == before


async def test_unsolicited_kelvin_demotes_old_rgb_and_preserves_companion_decode_only(device):
    device._notify_callback(None, bytearray(frame("aa050dff00000000000000")))
    assert device.rgb_color_source == "observed"
    packets = [frame("aa050dffffff0fa0" + companion) for companion in ("ffd5a1", "123456")]
    for packet in packets:
        device._notify_callback(None, bytearray(packet))
        assert device.color_temp_kelvin == 4000 and device.color_temp_kelvin_source == "observed"
        assert device.rgb_color_source == "retained"
    assert parse_status_result(packets[1], profile=PROFILE).parsed.body.detail.companion_rgb.red == 18
    with pytest.raises(ValueError, match="companion"):
        require_profile_packet(frame("33050dffffff0fa0000000"), PROFILE)
    with pytest.raises(ValueError, match="100 K steps"):
        require_profile_packet(frame("33050dffffff0abe000000"), PROFILE)


async def test_entity_static_controls_require_fresh_reply_and_preserve_received_state(device, monkeypatch):
    light = GoveeBLELight(device)
    light.async_write_ha_state = MagicMock()
    device.is_on = True

    async def respond(_uuid, packet, **kwargs):
        if packet == build_colour_mode_query(profile=PROFILE):
            device._notify_callback(None, bytearray(frame("aa050dffffff0fa0ffd5a1")))

    device._client.write_gatt_char.side_effect = respond
    await light.async_turn_on(color_temp_kelvin=4000)
    assert light.color_mode is ColorMode.COLOR_TEMP and light.color_temp_kelvin == 4000
    assert device.color_temp_kelvin_source == "observed"
    monkeypatch.setattr(device, "refresh_state", AsyncMock(return_value=False))
    with pytest.raises(HomeAssistantError):
        await light.async_turn_on(rgb_color=(255, 0, 0))
    assert device.refresh_state.await_count == 2
    assert device.rgb_color_source != "observed"
    # Unknown modes retain opaque data and revoke direct static observation authority.
    device._expected_state.clear()
    device._notify_callback(None, bytearray(frame("aa05ee1234")))
    assert device.color_mode is ParsedMode.UNKNOWN
    assert device.color_temp_kelvin_source != "observed"


@pytest.mark.parametrize("operation", ["brightness", "power_on", "power_off"])
async def test_fresh_observation_during_write_survives_entity_rollback(device, monkeypatch, operation):
    light = GoveeBLELight(device)
    light.async_write_ha_state = MagicMock()
    device.is_on = operation != "power_on"
    field = "brightness_pct" if operation == "brightness" else "is_on"
    value = 25 if operation == "brightness" else operation == "power_off"

    async def respond(_uuid, packet, **kwargs):
        device._expected_state.clear()
        packet = frame("aa0419" if operation == "brightness" else f"aa01{int(value):02x}")
        device._notify_callback(None, bytearray(packet))

    device._client.write_gatt_char.side_effect = respond
    monkeypatch.setattr(device, "refresh_state", AsyncMock(return_value=False))
    with pytest.raises(HomeAssistantError):
        if operation == "brightness":
            await light.async_turn_on(brightness=128)
        elif operation == "power_on":
            await light.async_turn_on()
        else:
            await light.async_turn_off()
    assert getattr(device, field) == value and device._field_revisions[field] > 0


@pytest.mark.parametrize("builder,value", [(build_power, False), (build_brightness, 25)])
@pytest.mark.parametrize("stage", ["transform", "guard"])
async def test_basic_optimism_waits_for_transform_and_authorization(device, builder, value, stage):
    def reject(*args):
        raise ValueError("rejected")

    if stage == "transform":
        device.profile = replace(device.profile, outbound_transform=reject)
    before = device.capture_effect_control_state()
    with pytest.raises(ValueError, match="rejected"):
        await device._async_write_packet(
            device._client,
            builder(value, profile=PROFILE),
            arm_expected=True,
            before_write=reject if stage == "guard" else None,
        )
    assert device.capture_effect_control_state() == before and device.control_write_attempts == 0
    device._client.write_gatt_char.assert_not_awaited()
