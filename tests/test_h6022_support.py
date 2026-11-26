import base64

import pytest

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode, parse_color_mode
from custom_components.ha_govee_led_ble.effect_catalogue import MODEL_EFFECT_CATALOGUES
from custom_components.ha_govee_led_ble.effect_commands import build_h617a_diy_single
from custom_components.ha_govee_led_ble.effect_compiler import compile_effect
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem
from custom_components.ha_govee_led_ble.effect_scenes import scene_detail_payload
from custom_components.ha_govee_led_ble.generated_protocol_adapter import parse_status_result
from custom_components.ha_govee_led_ble.music_commands import (
    edit_music_body,
    music_body_parameters,
    music_body_style,
    prepare_music_body_writes,
    prepare_music_profile_writes,
)
from custom_components.ha_govee_led_ble.music_protocol import music_codebook
from custom_components.ha_govee_led_ble.native_scenes import build_native_scene_packets, native_scene_body_is_opaque
from custom_components.ha_govee_led_ble.protocol_admission import require_profile_packet
from custom_components.ha_govee_led_ble.protocol_core import H6022EffectUpload
from custom_components.ha_govee_led_ble.protocol_effect_bodies import (
    parse_a3_effect_envelope,
    upload_ack_mode,
    upload_ack_subtype,
    upload_ack_success,
)
from custom_components.ha_govee_led_ble.protocol_parsing import parse_command_ack_result
from custom_components.ha_govee_led_ble.scenes import SCENE_ENTRIES
from custom_components.ha_govee_led_ble.transport import fragment_a3, reassemble_a3, xor_checksum

H6022_PALETTE = "07ff0000ff7f00ffff0000ff000000ff00ffff8b00ff"
H6022_MUSIC_BODIES = {
    "energetic": bytes.fromhex("39" + H6022_PALETTE + "0100"),
    "rhythm": bytes.fromhex("38" + H6022_PALETTE + "0100"),
    "spectrum": bytes.fromhex("54" + H6022_PALETTE + "0100"),
    "rolling": bytes.fromhex("63" + H6022_PALETTE + "010000"),
    "separation": bytes.fromhex("55" + H6022_PALETTE + "0100"),
    "hopping": bytes.fromhex("33" + H6022_PALETTE + "0019"),
    "fountain": bytes.fromhex("64" + H6022_PALETTE + "010000"),
    "meteor": bytes.fromhex("65" + H6022_PALETTE + "00"),
}


def _scene(family: int):
    return next(entry for entry in SCENE_ENTRIES["H6022"] if entry.diy_effect_codes == (family,))


def test_h6022_declares_exact_scene_and_diy_catalogues():
    catalogue = MODEL_EFFECT_CATALOGUES["H6022"]

    assert {family.family for family in catalogue.effects} == {0, 5, 9, 14, 15, 82, 83}
    assert {mode.id for mode in catalogue.music_modes} == {
        "energetic",
        "rhythm",
        "spectrum",
        "rolling",
        "separation",
        "hopping",
        "fountain",
        "meteor",
    }
    assert len(SCENE_ENTRIES["H6022"]) == 96


def test_h6022_opaque_family_classification_is_exact_model_scoped():
    scene = _scene(1)

    assert native_scene_body_is_opaque(scene, "H6022")
    assert not native_scene_body_is_opaque(scene, "H617A")


def test_h6022_opaque_scenes_round_trip_through_exact_upload_routes():
    professional = _scene(693)
    legacy = _scene(1)

    for scene, expected_subtype, expected_marker in ((professional, 0x58, 0x41), (legacy, 0x04, 0x00)):
        packets = build_native_scene_packets("H6022", scene)
        payload = base64.b64decode(scene.param, validate=True)
        envelope = reassemble_a3(packets[:-1])
        assert envelope[2] == expected_subtype
        assert envelope[3 : 3 + len(payload)] == payload
        assert envelope[3] == expected_marker
        detail = scene_detail_payload("H6022", scene.scene_id, scene.effect_id)
        assert detail["scene"]["parameter_kind"] == "opaque"
        assert detail["content"]["kind"] == "scene_builtin"


def test_h6022_family_zero_diy_is_not_inferred_from_legacy_scene_marker():
    custom = build_h617a_diy_single(0, 0, 50, ((255, 0, 0), (0, 255, 0)))
    legacy_scene = _scene(1)
    scene = build_native_scene_packets("H6022", legacy_scene)

    for packets, subtype in ((custom, 0x04), (scene[:-1], 0x04)):
        envelope = reassemble_a3(packets)
        parsed = parse_a3_effect_envelope(envelope, "H6022")
        assert isinstance(parsed, H6022EffectUpload)
        assert parsed.upload_type == subtype
        assert parsed.data == envelope[3:]
        for packet in packets:
            require_profile_packet(packet, MODEL_PROFILES["H6022"])

    template = next(item for item in MODEL_EFFECT_CATALOGUES["H6022"].templates if item.id == "template:single:0:0")
    compiled = compile_effect(LibraryItem.new("H6022 gradual", template.content), "H6022", diy_code=24)
    assert isinstance(parse_a3_effect_envelope(reassemble_a3(compiled.upload_packets), "H6022"), H6022EffectUpload)


@pytest.mark.parametrize("mode", tuple(H6022_MUSIC_BODIES))
def test_h6022_music_modes_match_exact_selector_and_body_bytes(mode):
    profile = MODEL_PROFILES["H6022"]
    code = music_codebook(profile)[mode]
    expected_body = H6022_MUSIC_BODIES[mode]
    writes = prepare_music_profile_writes("H6022", mode, 42, None, mode in {"energetic", "rhythm"}, {}, profile=profile)

    assert writes.body == (mode, expected_body)
    assert tuple(packet for packet, _state in writes.writes[1:-1]) == tuple(fragment_a3(0x41, expected_body))
    selector_prefix = bytes((0x33, 0x05, 0x13, code, 42)) + bytes(14)
    assert writes.writes[-1][0] == selector_prefix + bytes((xor_checksum(selector_prefix),))
    assert writes.first_upload == 1 and writes.last_upload == 2
    assert writes.writes[-1][1]["music_mode"] == mode


def test_h6022_music_style_is_encoded_and_read_from_its_exact_body():
    profile = MODEL_PROFILES["H6022"]
    dynamic = prepare_music_profile_writes("H6022", "energetic", 42, None, False, {}, profile=profile)

    assert dynamic.body is not None
    assert dynamic.body[1] == H6022_MUSIC_BODIES["energetic"][:-2] + b"\x00\x00"
    assert music_body_style(dynamic.body[1], "energetic", profile=profile) is False
    assert music_body_style(H6022_MUSIC_BODIES["energetic"], "energetic", profile=profile) is True


@pytest.mark.parametrize(
    ("mode", "parameters", "tail"),
    [
        ("spectrum", {"gradient": False}, b"\x00\x00"),
        ("rolling", {"gradient": False, "direction": "down"}, b"\x00\x01\x00"),
        ("separation", {"gradient": False}, b"\x00\x00"),
        ("hopping", {"gradient": True}, b"\x01\x19"),
        ("fountain", {"gradient": False, "direction": "down"}, b"\x00\x01\x00"),
        ("meteor", {"direction": "right"}, b"\x01"),
    ],
)
def test_h6022_nondefault_parameters_encode_and_edit_exact_tails(mode, parameters, tail):
    profile = MODEL_PROFILES["H6022"]
    default = H6022_MUSIC_BODIES[mode]
    authored = prepare_music_profile_writes("H6022", mode, 42, None, False, parameters, profile=profile)
    expected = default[: -len(tail)] + tail

    assert authored.body == (mode, expected)
    assert music_body_parameters(expected, mode, profile=profile) == parameters
    assert edit_music_body(default, mode, parameters, profile=profile) == expected


@pytest.mark.parametrize(
    "mode,expected_code",
    [(mode, bytes((code,))) for mode, code in zip(H6022_MUSIC_BODIES, (57, 56, 84, 99, 85, 51, 100, 101), strict=True)],
)
def test_h6022_exact_music_readback_selects_mode_and_sensitivity(mode, expected_code):
    profile = MODEL_PROFILES["H6022"]
    prefix = bytes.fromhex("aa0513") + expected_code + b"\x2a"
    frame = prefix.ljust(19, b"\x00") + bytes((xor_checksum(prefix.ljust(19, b"\x00")),))
    result = parse_status_result(frame, "H6022", profile=profile)

    assert result.rejection is None and result.parser == "h6022_status_reply"
    parsed = parse_color_mode(result.parsed, "H6022", profile=profile)
    assert parsed.mode is ParsedMode.MUSIC
    assert parsed.music_mode == mode
    assert parsed.music_sensitivity == 42
    assert parsed.music_color_present is False


@pytest.mark.parametrize(
    ("mode", "parameters"),
    [
        ("spectrum", {"gradient": False}),
        ("rolling", {"gradient": False, "direction": "down"}),
        ("separation", {"gradient": False}),
        ("hopping", {"gradient": True}),
        ("fountain", {"gradient": False, "direction": "down"}),
        ("meteor", {"direction": "right"}),
    ],
)
def test_h6022_recovery_replays_retained_parameter_body_before_selector(mode, parameters):
    profile = MODEL_PROFILES["H6022"]
    body = edit_music_body(H6022_MUSIC_BODIES[mode], mode, parameters, profile=profile)
    writes = prepare_music_body_writes("H6022", mode, 37, body, profile=profile)

    assert writes.body == (mode, body)
    assert tuple(packet for packet, _state in writes.writes[1:-1]) == tuple(fragment_a3(0x41, body))
    if "gradient" in parameters:
        assert writes.writes[-2][1]["music_gradient"] is parameters["gradient"]
    else:
        assert "music_gradient" not in writes.writes[-2][1]
    if "direction" in parameters:
        assert writes.writes[-2][1]["music_direction"] == parameters["direction"]
    assert writes.writes[-1][1]["music_mode"] == mode


@pytest.mark.parametrize("success", [False, True])
def test_h6022_music_upload_ack_is_required_before_activation(success):
    profile = MODEL_PROFILES["H6022"]
    writes = prepare_music_profile_writes(
        "H6022",
        "rolling",
        42,
        None,
        False,
        {"gradient": False, "direction": "down"},
        profile=profile,
    )
    packets = tuple(packet for packet, _state in writes.writes)
    index = writes.last_upload
    assert index is not None
    assert upload_ack_subtype(packets, index, "H6022", profile=profile) == 0x41
    assert upload_ack_mode(packets, index, "H6022", profile=profile) is None

    prefix = bytes.fromhex("a3410000" if success else "a3410001").ljust(19, b"\x00")
    ack = parse_command_ack_result(prefix + bytes((xor_checksum(prefix),)), "H6022", profile=profile)
    assert ack.rejection is None and ack.parser == "h617a_command_ack"
    assert upload_ack_success(ack.parsed, 0x41) is success
