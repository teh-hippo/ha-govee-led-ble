from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ha_govee_led_ble.const import device_profile
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_status import decode_status_frame, parse_color_mode
from custom_components.ha_govee_led_ble.effect_compiler import compile_effect, validate_compiled_geometry
from custom_components.ha_govee_led_ble.effect_domain import EffectPair, LibraryItem, MultiEffect, SingleEffect
from custom_components.ha_govee_led_ble.effect_protocol_decoder import decode_effect_frames
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_brightness,
    build_firmware_query,
    build_hardware_query,
    build_power,
    require_profile_packet,
    table_kelvin_rgb,
)
from custom_components.ha_govee_led_ble.light_commands import build_color_rgb, build_color_temp
from custom_components.ha_govee_led_ble.music_commands import resolve_music_profile
from custom_components.ha_govee_led_ble.music_semantics import music_variant
from custom_components.ha_govee_led_ble.native_scenes import build_native_scene_packets
from custom_components.ha_govee_led_ble.protocol_core import H6181DiyBody
from custom_components.ha_govee_led_ble.protocol_music_params import parse_music_parameters
from custom_components.ha_govee_led_ble.scenes import SCENE_ENTRIES, scene_supported
from custom_components.ha_govee_led_ble.transport import fragment_a3, reassemble_a1_02, xor_checksum


def frame(payload: bytes) -> bytes:
    body = payload.ljust(19, b"\0")
    return body + bytes([xor_checksum(body)])


def test_ordinary_colour_and_raw_brightness_match_their_distinct_contracts():
    profile = device_profile("H6181", None, None, firmware="1.03.00", hardware="1.00.03")
    assert build_color_rgb(12, 34, 56, "H6181") == frame(bytes.fromhex("33050d0c2238"))
    assert build_color_temp(2700, "H6181") == frame(bytes.fromhex("33050dffffff0a8c") + bytes(table_kelvin_rgb(2700)))
    assert profile.outbound_transform is not None
    for percent, raw in ((1, 20), (50, 136), (100, 254)):
        assert profile.outbound_transform(build_brightness(percent, "H6181")) == frame(bytes([0x33, 4, raw]))


@pytest.mark.parametrize(
    "pact,firmware,hardware",
    [
        ((None, None), None, None),
        ((None, None), "1.03.00", None),
        ((None, None), None, "1.00.03"),
        ((None, None), "1.03.01", "1.00.03"),
        ((None, None), "1.03.00", "1.00.04"),
        ((10, 1), "1.03.00", "1.00.03"),
        ((10, 2), "1.03.00", "1.00.03"),
        ((10, 3), "1.03.00", "1.00.03"),
    ],
)
def test_colour_probe_does_not_change_other_revision_contexts(pact, firmware, hardware):
    profile = device_profile("H6181", *pact, firmware=firmware, hardware=hardware)
    for packet in (build_color_rgb(255, 0, 0, "H6181"), build_color_temp(4000, "H6181")):
        assert (profile.outbound_transform(packet) if profile.outbound_transform else packet) == packet


@pytest.fixture
async def colour_probe(hass):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6181", configuration_url=None)
    client = MagicMock(is_connected=True, start_notify=AsyncMock(), write_gatt_char=AsyncMock())
    coordinator._client = client
    coordinator._reply_gate.timeout = 0
    coordinator._note_identity(fw_version="1.03.00", hw_version="1.00.03")
    await coordinator._start_notify()
    return coordinator, client


def confirm_probe_identity(client):
    receive = client.start_notify.call_args.args[1]
    receive(None, bytearray(frame(b"\xaa\x06" + b"1.03.00")))
    receive(None, bytearray(frame(b"\xaa\x07\x03" + b"1.00.03")))


@pytest.mark.parametrize(
    "packet,wire,field,value,reply",
    [
        (
            build_color_rgb(255, 0, 0, "H6181"),
            "330502ff000000000000",
            "rgb_color",
            (255, 0, 0),
            "aa0502ff000000000000",
        ),
        (
            build_color_temp(4000, "H6181"),
            "330502ffffff01ffd5a1",
            "color_temp_kelvin",
            4000,
            "aa0502ffffff01ffd1a3",
        ),
    ],
)
async def test_colour_probe_preserves_logical_expectations_and_strict_readback(
    colour_probe, packet, wire, field, value, reply
):
    coordinator, client = colour_probe
    confirm_probe_identity(client)
    await coordinator._async_write_packet(client, packet, arm_expected=True)
    client.write_gatt_char.assert_awaited_once()
    assert client.write_gatt_char.call_args.args[1] == frame(bytes.fromhex(wire))
    assert coordinator._expected_state[field][0] == value
    receive = client.start_notify.call_args.args[1]
    receive(None, bytearray(frame(bytes.fromhex("aa050d000000"))))
    assert field not in coordinator._field_revisions
    receive(None, bytearray(frame(bytes.fromhex(reply))))
    assert getattr(coordinator, field) == value
    assert getattr(coordinator, f"{field}_source") == "observed"


@pytest.mark.parametrize("confirmed", [(), ("fw_version",), ("hw_version",), ("reconnect",)])
@pytest.mark.parametrize("arm_expected", [False, True])
async def test_colour_probe_cannot_use_cached_or_partially_confirmed_identity(colour_probe, confirmed, arm_expected):
    coordinator, client = colour_probe
    if confirmed == ("reconnect",):
        confirm_probe_identity(client)
        coordinator._clear_client_state(client)
        coordinator._client = client
        await coordinator._start_notify()
    else:
        for field in confirmed:
            coordinator._observe_identity_field(field, getattr(coordinator, field))
    with pytest.raises(ValueError, match="current-subscription device identity"):
        await coordinator._async_write_packet(client, build_color_rgb(255, 0, 0, "H6181"), arm_expected=arm_expected)
    client.write_gatt_char.assert_not_awaited()
    assert coordinator._expected_state == {}
    assert coordinator.control_write_attempts == 0


@pytest.mark.parametrize("change", ["identity", "profile", "subscription", "client"])
async def test_colour_probe_rechecks_authorisation_after_the_write_guard(colour_probe, change):
    coordinator, client = colour_probe
    confirm_probe_identity(client)

    def revoke():
        if change == "identity":
            coordinator._confirmed_identity_fields.discard("hw_version")
        elif change == "profile":
            coordinator._note_identity(fw_version="1.03.01")
        elif change == "subscription":
            coordinator._notification_token = object()
        else:
            coordinator._client = MagicMock(is_connected=True)

    with pytest.raises(ValueError, match="current-subscription device identity"):
        await coordinator._async_write_packet(client, build_color_rgb(255, 0, 0, "H6181"), before_write=revoke)
    client.write_gatt_char.assert_not_awaited()
    assert coordinator._expected_state == {}


async def test_colour_probe_allows_untransformed_identity_queries_and_power(colour_probe):
    coordinator, client = colour_probe
    packets = (
        build_firmware_query("H6181"),
        build_hardware_query("H6181"),
        build_power(True, "H6181"),
    )
    for packet in packets:
        await coordinator._async_write_packet(client, packet)
    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == list(packets)


@pytest.mark.parametrize("selector", [2, 13])
def test_legacy_temperature_flag_is_not_misread_as_a_kelvin_integer(selector):
    packet = frame(bytes([0xAA, 5, selector, 255, 255, 255, 1, *table_kelvin_rgb(2700), 0x7B]))
    profile = device_profile("H6181", None, None)
    decoded = decode_status_frame(packet, "H6181", profile=profile)
    assert decoded is not None
    result = parse_color_mode(decoded.generated, "H6181", profile=profile)
    assert result.color_temp_kelvin == 2700 and result.rgb_color is None
    assert decoded.generated.body.detail.unknown_tail.startswith(b"\x7b")
    bad = decode_status_frame(frame(bytes([0xAA, 5, selector, 1, 2, 3, 2])), "H6181", profile=profile)
    assert bad is not None
    with pytest.raises(ValueError, match="flag"):
        parse_color_mode(bad.generated, "H6181", profile=profile)


@pytest.mark.parametrize("selector", [2, 13])
@pytest.mark.parametrize(
    "companion,kelvin",
    [
        ("ff8912", 2000),
        ("ffd1a3", 4000),
        ("d6e1ff", 9000),
        ("fff9fd", 6600),
        ("f7f5ff", 7000),
        ("eff0ff", 7400),
    ],
)
def test_legacy_temperature_accepts_aliases_without_reassigning_overlapping_colours(selector, companion, kelvin):
    profile = device_profile("H6181", None, None)
    packet = frame(bytes([0xAA, 5, selector, 255, 255, 255, 1]) + bytes.fromhex(companion))
    decoded = decode_status_frame(packet, "H6181", profile=profile)
    assert decoded is not None
    result = parse_color_mode(decoded.generated, "H6181", profile=profile)
    assert result.color_temp_kelvin == kelvin and result.rgb_color is None


@pytest.mark.parametrize("companion", ["ff8912", "d6e1ff", "fff9fd", "010203", "000000"])
def test_legacy_temperature_rejects_unknown_or_out_of_range_companions(companion):
    profile = replace(device_profile("H6181", None, None), color_temp_range=(2700, 6500))
    packet = frame(bytes.fromhex("aa050dffffff01") + bytes.fromhex(companion))
    decoded = decode_status_frame(packet, "H6181", profile=profile)
    assert decoded is not None
    with pytest.raises(ValueError, match="Unrecognised legacy colour-temperature companion"):
        parse_color_mode(decoded.generated, "H6181", profile=profile)


@pytest.mark.parametrize(
    "content",
    [
        SingleEffect(0, 0, 50, ((255, 0, 0),)),
        MultiEffect((EffectPair(0, 0), EffectPair(2, 0)), 75, ((255, 0, 0), (0, 0, 255))),
    ],
)
def test_legacy_diy_upload_uses_the_approved_selector_and_round_trips(content):
    profile = device_profile("H6181", None, None)
    compiled = compile_effect(LibraryItem.new("Palette", content), "H6181", diy_code=42, profile=profile)
    assert compiled.upload_transport == "a1_02"
    body = reassemble_a1_02(compiled.upload_packets)
    parsed = H6181DiyBody.from_bytes(body)
    parsed._read()
    assert parsed.selector == 42 and parsed.speed == content.speed
    assert compiled.activation_packet == frame(bytes.fromhex("33050a2a00"))
    assert decode_effect_frames(compiled.upload_packets, "H6181", compiled.upload_transport) == content
    with pytest.raises(ValueError, match="transport"):
        validate_compiled_geometry(compiled, replace(profile, diy_upload_transport="a3"))
    with pytest.raises(ValueError, match="one-byte"):
        compile_effect(LibraryItem.new("Palette", content), "H6181", diy_code=256, profile=profile)


def test_diy_application_requires_owner_approval_of_a_disposable_slot():
    item = LibraryItem.new("Palette", SingleEffect(0, 0, 50, ((255, 0, 0),)))
    with pytest.raises(ValueError, match="requires a DIY code"):
        compile_effect(item, "H6181")


@pytest.mark.parametrize(
    "pact,firmware,hardware,brightness,modes,uploads",
    [
        ((None, None), "1.00.99", "1.00.03", (20, 254), (), False),
        ((10, 1), "1.02.99", "1.00.03", None, ("dynamic", "soft"), False),
        ((10, 1), "1.03.00", "1.00.03", None, ("dynamic", "soft"), True),
        ((10, 2), None, None, None, ("dynamic", "soft"), True),
        ((10, 3), "1.03.00", "1.00.03", (20, 254), (), True),
        ((10, 2), "2.03.99", "2.01.01", None, ("dynamic", "soft"), True),
        ((10, 2), "2.04.00", "2.01.01", None, ("dynamic", "soft", "bloom", "radiant"), True),
        ((10, 2), "2.04.00", "2.00.05", None, ("dynamic", "soft"), True),
        ((10, 2), "2.04.00", "2.02.01", None, ("dynamic", "soft"), True),
        ((10, 2), "2.04.00", "3.04.01", None, ("dynamic", "soft"), True),
        ((10, 2), "2.04.00", "3.05.01", None, ("dynamic", "soft", "bloom", "radiant"), True),
    ],
)
def test_revision_boundaries_resolve_independently(pact, firmware, hardware, brightness, modes, uploads):
    profile = device_profile("H6181", *pact, firmware=firmware, hardware=hardware)
    assert profile.brightness_wire_range == brightness
    assert profile.music_modes == modes
    assert (profile.selector_only_scene_bits is None) is uploads
    assert profile.supports_custom_effects
    assert profile.diy_upload_transport == ("a1_02" if pact[0] is None else "a3")
    for scene in SCENE_ENTRIES["H6181"]:
        if not scene_supported(scene, profile):
            continue
        packets = build_native_scene_packets("H6181", scene, profile=profile)
        assert packets[-1] == frame(bytes([0x33, 5, 4, scene.code & 255, scene.code >> 8]))
        assert bool(len(packets) > 1) is bool(uploads and scene.param)


@pytest.mark.parametrize(
    "code,mode,calm,tail",
    [
        (48, "bloom", False, b"\x0a\x50"),
        (48, "bloom", True, b"\x0a\x14"),
        (49, "radiant", False, b"\x05\x64\x0a"),
        (49, "radiant", True, b"\x14\x46\x0a"),
    ],
)
def test_palette_music_preserves_the_evidenced_style_and_palette(code, mode, calm, tail):
    from custom_components.ha_govee_led_ble.transport import reassemble_a3

    profile = device_profile("H6181", 10, 2, firmware="2.04.00", hardware="2.01.01")
    _, _, packets = resolve_music_profile(
        "H6181", mode, 73, None, calm, {}, profile=profile, palette=((12, 34, 56), (78, 90, 12))
    )
    envelope = reassemble_a3(tuple(packet for packet in packets if packet[0] == 0xA3))
    assert envelope[2 : 2 + 3 + 6 + len(tail)] == bytes([0x41, code, 2, 12, 34, 56, 78, 90, 12]) + tail
    assert packets[-1] == frame(bytes([0x33, 5, 0x13, code, 73]))
    variant = music_variant(profile, code)
    assert variant is not None
    parsed = parse_music_parameters(variant, envelope[3:])
    assert [(rgb.red, rgb.green, rgb.blue) for rgb in parsed.palette] == [(12, 34, 56), (78, 90, 12)]


def test_music_status_does_not_invent_a_selector_from_conflicting_readback_fields():
    profile = device_profile("H6181", 10, 1, firmware="1.03.00", hardware="1.00.03")
    decoded = decode_status_frame(frame(bytes.fromhex("aa051300320101ff0000")), "H6181", profile=profile)
    assert decoded is not None
    parsed = parse_color_mode(decoded.generated, "H6181", profile=profile)
    assert parsed.music_mode is None and parsed.music_sensitivity == 50
    assert parsed.music_color is None and parsed.music_calm is None and not parsed.music_color_present


@pytest.mark.parametrize(
    "firmware,hardware,selector,sensitivity,mode,observed",
    [
        ("2.04.00", "2.01.01", 48, 0, "bloom", 0),
        ("2.04.00", "3.05.01", 49, 99, "radiant", 99),
        ("2.03.99", "2.01.01", 48, 73, None, 73),
        ("2.04.00", "3.04.01", 49, 73, None, 73),
        ("2.04.00", "2.01.01", 255, 73, None, 73),
        ("2.04.00", "2.01.01", 48, 100, "bloom", None),
    ],
)
def test_music_readback_qualifies_selector_and_sensitivity_independently(
    firmware, hardware, selector, sensitivity, mode, observed
):
    profile = device_profile("H6181", 10, 2, firmware=firmware, hardware=hardware)
    packet = frame(bytes([0xAA, 5, 0x13, selector, sensitivity, 0x7B, 1, 255, 0, 0]))
    decoded = decode_status_frame(packet, "H6181", profile=profile)
    assert decoded is not None
    result = parse_color_mode(decoded.generated, "H6181", profile=profile)
    assert result.music_mode == mode and result.music_sensitivity == observed
    assert result.music_calm is None and result.music_color is None and not result.music_color_present


@pytest.mark.parametrize("selector,mode", [(0, None), (48, "bloom")])
async def test_music_observes_qualified_fields_without_confirming_ambiguous_settings(hass, selector, mode):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6181", configuration_url=None)
    client = MagicMock(is_connected=True, start_notify=AsyncMock())
    coordinator._client = client
    coordinator.pact_type, coordinator.pact_code = 10, 2
    coordinator._note_identity(fw_version="2.04.00", hw_version="2.01.01")
    await coordinator._start_notify()
    receive = client.start_notify.call_args.args[1]
    coordinator.music_mode, coordinator.music_sensitivity = "dynamic", 73
    coordinator.music_color, coordinator.music_calm = (12, 34, 56), True
    coordinator._arm_expected_values({"music_sensitivity": 73})
    for sensitivity in (42, 73):
        receive(None, bytearray(frame(bytes([0xAA, 5, 0x13, selector, sensitivity, 1, 1, 255, 0, 0]))))
        assert coordinator.music_sensitivity == 73
        assert ("music_sensitivity" in coordinator._field_revisions) is (sensitivity == 73)
    assert coordinator.music_mode == (mode or "dynamic")
    assert ("music_mode" in coordinator._field_revisions) is (mode is not None)
    assert coordinator.music_color == (12, 34, 56) and coordinator.music_calm
    assert not {"music_color", "music_calm"} & coordinator._field_revisions.keys()
    assert coordinator.profile.music_readback_ambiguous


@pytest.mark.parametrize("payload", ["3305047b", "3399", "334101"])
def test_legacy_packet_authorisation_rejects_unqualified_operations(payload):
    with pytest.raises(ValueError):
        require_profile_packet(frame(bytes.fromhex(payload)), device_profile("H6181", None, None))


@pytest.mark.parametrize("subtype", [1, 3, 4])
def test_legacy_profile_does_not_admit_later_or_painted_uploads(subtype):
    profile = device_profile("H6181", None, None)
    with pytest.raises(ValueError):
        require_profile_packet(fragment_a3(subtype, b"\0")[0], profile)
