"""Coordinator status parsing tests."""

from dataclasses import replace

import pytest

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES
from custom_components.ha_govee_led_ble.coordinator_status import (
    ParsedColorModeResponse,
    ParsedMode,
    StatusDomain,
    decode_status_frame,
    decode_status_frame_result,
    parse_color_mode,
)
from custom_components.ha_govee_led_ble.generated_protocol_adapter import ProtocolParseRejection
from custom_components.ha_govee_led_ble.scenes import MODEL_SCENES
from custom_components.ha_govee_led_ble.transport import xor_checksum

H = bytes.fromhex


def _parse_colour(frame: str, model: str = "H617A") -> ParsedColorModeResponse:
    decoded = decode_status_frame(H(frame), model)
    assert decoded is not None
    return parse_color_mode(decoded.generated, model)


def _h6179_status(domain: int, body: bytes) -> bytes:
    frame = bytes((0xAA, domain)) + body.ljust(17, b"\0")
    return frame + bytes((xor_checksum(frame),))


def test_h7025_exact_status_root_covers_declared_reads_and_music_numbering():
    frames = (
        _h6179_status(1, b"\x01"),
        _h6179_status(4, b"\x2a"),
        _h6179_status(5, H("13482a")),
        _h6179_status(6, b"1.02.03\0"),
        _h6179_status(7, b"\x033.01.01\0"),
        _h6179_status(0xA5, H("01640102036404050664070809640a0b0c")),
    )
    decoded = [decode_status_frame_result(frame, "H7025") for frame in frames]
    assert all(result.parser == "h7025_status_reply" and result.rejection is None for result in decoded)
    assert {result.parsed.domain for result in decoded} == MODEL_PROFILES["H7025"].read_domains
    music = parse_color_mode(decoded[2].parsed.generated, "H7025")
    assert music.mode is ParsedMode.MUSIC and music.music_mode == "hopping"
    assert music.music_sensitivity == 42 and not music.music_color_present
    rhythm = decode_status_frame(_h6179_status(5, H("13032a0101112233")), "H7025")
    assert rhythm is not None
    settings = parse_color_mode(rhythm.generated, "H7025")
    assert settings.music_mode == "rhythm" and settings.music_calm
    assert settings.music_color == (17, 34, 51)
    static = decode_status_frame(_h6179_status(5, H("15001068")), "H7025")
    assert static is not None
    assert parse_color_mode(static.generated, "H7025").color_temp_kelvin == 4200
    unknown = decode_status_frame(_h6179_status(5, H("00")), "H7025")
    assert unknown is not None
    assert parse_color_mode(unknown.generated, "H7025").mode is ParsedMode.UNKNOWN


def test_status_envelope_rejects_invalid_frames() -> None:
    assert decode_status_frame(b"") is None
    assert decode_status_frame(H("3301010000000000000000000000000000000033")) is None
    bad_checksum = bytearray(H("aa05049d0800000000000000000000000000003e"))
    bad_checksum[-1] ^= 1
    assert decode_status_frame(bytes(bad_checksum)) is None


def test_status_rejections_expose_stable_reasons_and_fail_closed() -> None:
    assert decode_status_frame_result(b"").rejection is ProtocolParseRejection.INVALID_LENGTH

    bad_checksum = bytearray(H("aa05049d0800000000000000000000000000003e"))
    bad_checksum[-1] ^= 1
    assert decode_status_frame_result(bytes(bad_checksum)).rejection is ProtocolParseRejection.INVALID_CHECKSUM

    unsupported = decode_status_frame_result(H("aa05049d0800000000000000000000000000003e"), "H9999")
    assert unsupported.parser is None
    assert unsupported.rejection is ProtocolParseRejection.UNSUPPORTED_MODEL

    h6102 = decode_status_frame_result(H("aa05049d0800000000000000000000000000003e"), "H6102")
    assert h6102.parser == "h6102_status_reply"
    assert h6102.rejection is None

    invalid_shape = decode_status_frame_result(H("aaa506731f646408646464fe6464640000000093"))
    assert invalid_shape.parser == "status_reply"
    assert invalid_shape.rejection is ProtocolParseRejection.SCHEMA_REJECTED


@pytest.mark.parametrize("model", ["H617A", "H617E"])
def test_production_three_record_status_contract(model: str) -> None:
    frame = bytearray(H("aaa50164ff880d64ff880d64ff880d0000000010"))
    for group in (0, 6):
        frame[2] = group
        frame[-1] = xor_checksum(frame[:-1])
        assert decode_status_frame_result(bytes(frame), model).rejection is ProtocolParseRejection.SCHEMA_REJECTED
    issue_frame = H("aaa50164e5444464ffae5464ffae5464cf2e2e24")
    assert decode_status_frame_result(issue_frame, model).rejection is ProtocolParseRejection.SCHEMA_REJECTED
    assert decode_status_frame_result(issue_frame, "H66A0").rejection is ProtocolParseRejection.UNSUPPORTED_MODEL


def test_h617a_colour_modes_preserve_scene_diy_and_music_semantics() -> None:
    scene = _parse_colour("aa05049d0800000000000000000000000000003e")
    assert scene.mode is ParsedMode.SCENE and scene.effect == "candy"
    diy = _parse_colour("aa050a2003000000000000000000000000000086")
    assert diy.mode is ParsedMode.DIY and diy.diy_code == 800
    rhythm = _parse_colour("aa051303580100000000000000000000000000e6")
    assert rhythm.mode is ParsedMode.MUSIC
    assert rhythm.music_mode == "rhythm" and rhythm.music_sensitivity == 88 and rhythm.music_calm is True
    static = _parse_colour("aa051501000000000000000000000000000000bb")
    assert static.mode is ParsedMode.COLOUR and static.multi_effect_flag == 1


def test_h617e_scene_readback_uses_its_exact_catalogue() -> None:
    h617a_codes = {scene.code for scene in MODEL_SCENES["H617A"].values()}
    name, scene = next((name, scene) for name, scene in MODEL_SCENES["H617E"].items() if scene.code not in h617a_codes)
    frame = bytearray(20)
    frame[:3] = bytes((0xAA, 0x05, 0x04))
    frame[3:5] = scene.code.to_bytes(2, "little")
    frame[-1] = xor_checksum(frame[:-1])
    decoded = decode_status_frame(bytes(frame), "H617E")

    assert decoded is not None
    parsed = parse_color_mode(decoded.generated, "H617E")
    assert parsed.effect == name


def test_h6179_status_uses_typed_domains_and_model_music_codes() -> None:
    static = decode_status_frame(_h6179_status(0x05, bytes.fromhex("0d1234560000000000")), "H6179")
    music = decode_status_frame(_h6179_status(0x05, bytes.fromhex("0e013201123456")), "H6179")
    diy = decode_status_frame(_h6179_status(0x05, bytes.fromhex("0a3412")), "H6179")

    assert static is not None and static.domain is StatusDomain.MODE
    assert parse_color_mode(static.generated, "H6179").rgb_color == (0x12, 0x34, 0x56)
    assert music is not None
    parsed_music = parse_color_mode(music.generated, "H6179")
    assert (parsed_music.mode, parsed_music.music_mode, parsed_music.music_sensitivity) == (
        ParsedMode.MUSIC,
        "mode_1",
        50,
    )
    assert parsed_music.music_color == (0x12, 0x34, 0x56)
    assert diy is not None and parse_color_mode(diy.generated, "H6179").diy_code == 0x1234


def test_h6199_video_and_music_fields_decode() -> None:
    video = _parse_colour("aa050000012a01370000000000000000000000b2", "H6199")
    assert video.mode is ParsedMode.VIDEO and video.video_mode == "game"
    assert (video.video_full_screen, video.video_saturation) == (False, 42)
    assert (video.video_sound_effects, video.video_sound_effects_softness) == (True, 55)
    music = _parse_colour("aa0513044d0001010203000000000000000000f4", "H6199")
    assert music.mode is ParsedMode.MUSIC and music.music_mode == "spectrum"
    assert music.music_sensitivity == 77 and music.music_color == (1, 2, 3)


def test_compatible_video_grammar_reuses_readback_without_exact_model_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = "H7000"
    monkeypatch.setitem(
        MODEL_PROFILES,
        model,
        replace(
            MODEL_PROFILES["H6199"],
            name="Synthetic video device",
            supports_video_capture_region=False,
            supports_video_saturation=False,
            supports_video_sound_effects=False,
            supports_white_balance=False,
            supports_relative_brightness=False,
            supports_blank_screen=False,
        ),
    )

    video = _parse_colour("aa050000012a01370000000000000000000000b2", model)

    assert video.mode is ParsedMode.VIDEO
    assert video.video_mode == "game"
    assert video.video_full_screen is None
    assert video.video_saturation is None
    assert video.video_sound_effects is None


@pytest.mark.parametrize("offset", [3, 4])
def test_h6199_unknown_video_selectors_are_ignored(offset: int) -> None:
    frame = bytearray(H("aa050000012a01370000000000000000000000b2"))
    frame[offset] = 0x7F
    frame[-1] = xor_checksum(frame[:-1])
    decoded = decode_status_frame(bytes(frame), "H6199")

    assert decoded is not None
    assert parse_color_mode(decoded.generated, "H6199") == ParsedColorModeResponse()


def test_h6199_native_control_readbacks_remain_generated_fields() -> None:
    white = decode_status_frame(H("aaa9000601100301150500000000000000000006"), "H6199")
    edges = decode_status_frame(H("aaae010433141f29000000000000000000000010"), "H6199")
    assert white is not None
    assert (white.generated.body.payload.current_red, white.generated.body.payload.current_blue) == (21, 5)
    assert edges is not None
    body = edges.generated.body
    assert (body.left_percent, body.top_percent, body.right_percent, body.bottom_percent) == (51, 20, 31, 41)


def test_invalid_static_gradual_flag_rejects_atomically_without_clearing_active_mode(hass) -> None:
    from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator

    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617C", configuration_url=None)
    coordinator.color_mode = ParsedMode.MUSIC
    coordinator.music_mode = "bloom"
    coordinator._music_body = ("bloom", b"3007ff0000")
    coordinator.effect = "dracarys"
    coordinator.diy_code = 402
    coordinator.rgb_color_source = "observed"
    frame = bytearray.fromhex("aa0515020fa0" + "00" * 13)
    frame.append(xor_checksum(frame))

    coordinator._notify_callback(None, frame)

    assert coordinator.packet_log[-1]["outcome"] == "rejected"
    assert coordinator.packet_log[-1]["reason"] == "semantic_rejected"
    assert coordinator.color_mode is ParsedMode.MUSIC
    assert coordinator.music_mode == "bloom"
    assert coordinator._music_body == ("bloom", b"3007ff0000")
    assert coordinator.effect == "dracarys"
    assert coordinator.diy_code == 402
    assert coordinator.rgb_color_source == "observed"
    assert StatusDomain.COLOUR_MODE not in coordinator._domain_revisions
    assert not coordinator._field_revisions
