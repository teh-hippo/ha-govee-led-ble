"""Exact-model controls and revision contracts, without claiming hardware qualification."""

import base64
from dataclasses import replace
from importlib import import_module

import pytest

from custom_components.ha_govee_led_ble.const import device_profile, get_profile
from custom_components.ha_govee_led_ble.dreamview import (
    build_dreamview_command,
    build_dreamview_query,
)
from custom_components.ha_govee_led_ble.effect_compiler import compile_effect
from custom_components.ha_govee_led_ble.effect_domain import (
    EffectPair,
    LibraryItem,
    MultiEffect,
    PaintedEffect,
    SingleEffect,
    WorkshopEffect,
)
from custom_components.ha_govee_led_ble.effect_protocol_decoder import decode_effect_frames
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_boolean_control,
    build_boolean_control_query,
    require_profile_packet,
)
from custom_components.ha_govee_led_ble.layered_scene_decoder import decode_workshop_effect
from custom_components.ha_govee_led_ble.light_commands import (
    build_color_rgb,
    build_color_temp,
    build_segment_brightness,
    build_segment_color,
    build_segment_color_temp,
)
from custom_components.ha_govee_led_ble.music_commands import prepare_music_request
from custom_components.ha_govee_led_ble.native_scenes import build_native_scene_packets
from custom_components.ha_govee_led_ble.scenes import SCENE_ENTRIES
from custom_components.ha_govee_led_ble.transport import reassemble_a3, xor_checksum


def frame(prefix: str) -> bytes:
    body = bytes.fromhex(prefix).ljust(19, b"\0")
    return body + bytes((xor_checksum(body),))


def test_static_writes_select_native_geometry_and_keep_kelvin_separate():
    assert build_color_rgb(255, 128, 0, "H605C") == frame("33051501ff80000000000000ff3f")
    assert build_color_temp(3000, "H605C") == frame("33051501ffffff0bb8ffb969ff3f")
    assert build_color_temp(6500, "H605C") == frame("33051501ffffff1964fff9fbff3f")
    assert build_segment_color((14,), 1, 2, 3, "H605C") == frame("3305150101020300000000000020")
    assert build_segment_color_temp((1, 14), 3000, "H605C") == frame("33051501ffffff0bb8ffb9690120")
    assert build_segment_brightness((1, 14), 42, "H605C") == frame("330515022a0120")
    with pytest.raises(ValueError, match="out of range"):
        build_segment_color((15,), 1, 2, 3, "H605C")


@pytest.mark.parametrize("enabled", [False, True])
def test_gradual_uses_shared_register_without_granting_native_zones(enabled):
    profile = get_profile("H605C")
    packet = build_boolean_control("gradual", enabled, "H605C")
    assert packet == frame(f"33a3{int(enabled):02x}")
    assert build_boolean_control_query("gradual", "H605C") == frame("aaa3")
    require_profile_packet(packet, profile)
    with pytest.raises(ValueError):
        require_profile_packet(packet, replace(profile, boolean_controls=frozenset()))
    with pytest.raises(ValueError):
        build_boolean_control("pole_enabled", enabled, "H605C")


@pytest.mark.parametrize(
    "pact,expected_write,expected_query,capacity",
    [
        ((1, 1), "335401", "aa54", 5),
        ((1, 2), "3360010101", "aa600101", 7),
    ],
)
def test_dreamview_generation_is_independent_of_standalone_video(pact, expected_write, expected_query, capacity):
    profile = device_profile("H605C", *pact)
    assert build_dreamview_command("switch_group", {"enabled": True}, profile) == frame(expected_write)
    assert build_dreamview_query("switch_group", profile) == frame(expected_query)
    assert build_dreamview_command("same_brightness", {"enabled": True}, profile) == frame("33600401")
    assert profile.dreamview_max_sub_devices == capacity
    assert profile.video_grammar == "H605C-video"
    with pytest.raises(ValueError, match="not supported"):
        build_dreamview_command("switch_group", {"enabled": True}, device_profile("H605C", None, None))


@pytest.mark.parametrize(
    "content",
    [
        SingleEffect(3, 5, 50, ((1, 2, 3), (4, 5, 6))),
        MultiEffect((EffectPair(0, 2), EffectPair(9, 10)), 50, ((1, 2, 3),)),
    ],
)
def test_palette_diy_upload_and_selector_round_trip_through_shared_runtime(content):
    compiled = compile_effect(LibraryItem.new("Candidate", content), "H605C", diy_code=4096)
    assert compiled.activation_packet == frame("33050a0010")
    assert compiled.upload_subtype == 4
    assert decode_effect_frames(compiled.upload_packets, "H605C", compiled.upload_transport) == content
    root = import_module("custom_components.ha_govee_led_ble.generated_protocol.h605c_effect_upload").H605cEffectUpload
    parsed = root.from_bytes(reassemble_a3(compiled.upload_packets))
    parsed._read()
    assert int(parsed.kind) == 4
    for packet in (*compiled.upload_packets, compiled.activation_packet):
        require_profile_packet(packet, get_profile("H605C"))


def test_painted_effect_uses_observed_physical_geometry_not_static_segments():
    profile = replace(get_profile("H605C"), physical_ic_count=72)
    content = PaintedEffect(
        "clockwise", 50, 100, ((255, 0, 0),) * 72, background=(255, 255, 255), addressing="physical_ic"
    )
    compiled = compile_effect(LibraryItem.new("Paint", content), "H605C", diy_code=4096, profile=profile)
    assert compiled.physical_ic_count == 72
    root = import_module("custom_components.ha_govee_led_ble.generated_protocol.h605c_effect_upload").H605cEffectUpload
    parsed = root.from_bytes(reassemble_a3(compiled.upload_packets))
    parsed._read()
    assert int(parsed.kind) == 3
    assert parsed.body.groups[0].indices == list(range(72))


@pytest.mark.parametrize(
    "mode,prefix,colour",
    [
        ("energetic", "330513052a", None),
        ("rhythm", "330513032a0001010203", (1, 2, 3)),
        ("spectrum", "330513042a0001010203", (1, 2, 3)),
        ("rolling", "330513062a0001010203", (1, 2, 3)),
    ],
)
def test_onboard_music_uses_exact_selectors_without_parameter_upload(mode, prefix, colour):
    packets = prepare_music_request("H605C", mode, 42, colour, False, {})
    assert packets == (frame("330101"), frame(prefix))
    root = import_module("custom_components.ha_govee_led_ble.generated_protocol.h605c_music_write").H605cMusicWrite
    parsed = root.from_bytes(packets[-1])
    parsed._read()
    assert parsed.body.mode.name == mode


@pytest.mark.parametrize("pact_code", [1, 2])
def test_workshop_uses_the_command_selector_contract_independently_of_upload(pact_code):
    profile = device_profile("H605C", 1, pact_code)
    scene = next(entry for entry in SCENE_ENTRIES["H605C"] if entry.scene_id == 29884)
    raw = base64.b64decode(scene.param)
    effect, padding = decode_workshop_effect("H605C", raw)
    content = WorkshopEffect("H605C", "candidate", effect, raw_param=raw, trailing_padding=padding)
    compiled = compile_effect(LibraryItem.new("Workshop", content), "H605C", profile=profile)
    assert compiled.activation_packet == frame("3305049201")
    assert reassemble_a3(compiled.upload_packets)[2] == 2
    root = import_module("custom_components.ha_govee_led_ble.generated_protocol.h605c_effect_upload").H605cEffectUpload
    encoded = root.from_bytes(reassemble_a3(compiled.upload_packets))
    encoded._read()
    assert [layer.body.layer_flags for layer in encoded.body.layers] == [0x12] * 4
    native = build_native_scene_packets("H605C", scene, profile=profile)
    assert reassemble_a3(native[:-1])[3:].startswith(raw)
    for packet in compiled.packets:
        require_profile_packet(packet, profile)


def test_energetic_readback_does_not_interpret_opaque_colour_or_style_bytes():
    from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode, decode_status_frame, parse_color_mode

    decoded = decode_status_frame(frame("aa051305637e8011223344"), "H605C")
    assert decoded is not None
    assert decoded.generated.body.detail.unknown_tail.startswith(bytes.fromhex("7e8011223344"))
    state = parse_color_mode(decoded.generated, "H605C")
    assert state.mode is ParsedMode.MUSIC and state.music_mode == "energetic"
    assert state.music_sensitivity == 99 and not state.music_color_present
    assert state.music_calm is None and state.music_color is None
