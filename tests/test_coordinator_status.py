"""Coordinator status parsing tests."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock

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
from custom_components.ha_govee_led_ble.protocol_core import ProtocolParseRejection
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


_H66A0_SEGMENT_PAGES = (
    "aaa50164e5444464ffae5464ffae5464cf2e2e24",
    "aaa50264c7262664c01f1f64b9181864b2111101",
    "aaa50364ba191964c3222264cb2a2a64d433336a",
    "aaa50464dc3b3b64e54444000000000000000032",
)


def test_h66a0_exact_status_root_covers_declared_reads_with_evidence_pages():
    frames = (
        _h6179_status(1, b"\x01"),
        _h6179_status(4, b"\x64"),
        _h6179_status(5, H("1305")),
        _h6179_status(6, b"1.00.24\0"),
        _h6179_status(7, b"\x033.07.01\0"),
        _h6179_status(0x20, b"6.01.00\0"),
        _h6179_status(0x21, b"1.01.18\0"),
        _h6179_status(0x30, b"\x02"),
        _h6179_status(0x32, b"\x01"),
        _h6179_status(0x40, b"\x00\x5a"),
        _h6179_status(0xA9, b"\x06\x01\x32"),
        _h6179_status(0xAE, b"\x01\x04\x64\x64\x64\x64"),
        *(H(page) for page in _H66A0_SEGMENT_PAGES),
    )
    decoded = [decode_status_frame_result(frame, "H66A0") for frame in frames]
    assert all(result.parser == "h66a0_status_reply" and result.rejection is None for result in decoded)
    assert {result.parsed.domain for result in decoded} == MODEL_PROFILES["H66A0"].read_domains
    assert decoded[3].parsed.generated.body.text == "1.00.24"
    music = parse_color_mode(decoded[2].parsed.generated, "H66A0")
    assert music.mode is ParsedMode.MUSIC and music.music_mode == "energetic"
    pages = [result.parsed.generated.body for result in decoded[12:]]
    assert [len(page.segments) for page in pages] == [4, 4, 4, 2]
    assert sum(len(page.segments) for page in pages) == MODEL_PROFILES["H66A0"].segment_count


def test_h1a42_exact_status_root_covers_declared_reads_and_wide_kelvin():
    from custom_components.ha_govee_led_ble.light_commands import build_color_temp

    frames = (
        _h6179_status(1, b"\x01"),
        _h6179_status(4, b"\x64"),
        _h6179_status(5, H("1392")),
        _h6179_status(6, b"1.01.07\0"),
        _h6179_status(7, b"\x033.08.01\0"),
        _h6179_status(0x20, b"1.07.00\0"),
        _h6179_status(0x21, b"1.02.04\0"),
        _h6179_status(0x40, b"\x00\x0b"),
        _h6179_status(0xA5, H("0164ff00006400ff00640000ff64ffffff")),
        _h6179_status(0xA5, H("0264808080000000000000000000000000")),
    )
    decoded = [decode_status_frame_result(frame, "H1A42") for frame in frames]
    assert all(result.parser == "h1a42_status_reply" and result.rejection is None for result in decoded)
    assert {result.parsed.domain for result in decoded} == MODEL_PROFILES["H1A42"].read_domains
    assert decoded[3].parsed.generated.body.text == "1.01.07"
    assert decoded[4].parsed.generated.body.text == "3.08.01"
    assert decoded[5].parsed.generated.body.text == "1.07.00"
    assert decoded[6].parsed.generated.body.text == "1.02.04"
    assert decoded[7].parsed.generated.body.count == 11
    music = parse_color_mode(decoded[2].parsed.generated, "H1A42")
    assert music.mode is ParsedMode.MUSIC and music.music_mode == "ripple"
    pages = [result.parsed.generated.body for result in decoded[8:]]
    assert [len(page.segments) for page in pages] == [4, 1]
    assert build_color_temp(1000, "H1A42")[7:9] == (1000).to_bytes(2, "big")
    assert build_color_temp(10000, "H1A42")[7:9] == (10000).to_bytes(2, "big")


@pytest.mark.parametrize("update", ["advertisement", "resolution", "same-cohort-count", "disconnect-advertisement"])
async def test_h61f5_cut_strip_narrows_segments_from_aa40(hass, update):
    from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator

    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H61F5", configuration_url=None)
    advertisement = SimpleNamespace(name="Govee_H61F5_ABCD", manufacturer_data={0x8801: H("ec00030101")})
    coordinator._note_advertisement(advertisement)
    coordinator._client = MagicMock(is_connected=True)
    assert coordinator.profile.physical_ic_count == 50
    assert coordinator.profile.segment_count == 10
    assert coordinator.profile.whole_device_mask == 0x03FF
    coordinator.segment_state_source = "observed"
    coordinator.segment_state_observed_at = "2026-10-21T00:00:00+00:00"
    coordinator.segment_brightness_readable = True
    initial_gen = coordinator._profile_generation
    coordinator._notify_callback(None, bytearray(_h6179_status(0x40, b"\x00\x15")))
    assert coordinator.profile.physical_ic_count == 21
    assert coordinator.profile.segment_count == 5
    assert coordinator.profile.whole_device_mask == 0x001F
    assert coordinator._profile_generation == initial_gen + 1
    assert coordinator.segment_state_source == "initial"
    assert coordinator.segment_state_observed_at is None
    assert not coordinator.segment_brightness_readable
    assert len(coordinator.segment_colors) == 5
    coordinator._notify_callback(None, bytearray(_h6179_status(0xA5, H("0164ff00006400ff00640000ff64ffffff"))))
    coordinator._notify_callback(None, bytearray(_h6179_status(0xA5, H("0264808080000000000000000000000000"))))
    assert coordinator.segment_state_source == "observed"
    assert len(coordinator.segment_colors) == 5
    assert coordinator.segment_colors[-1] == (0x80, 0x80, 0x80)
    # Repeated AA 40 with the same 5-segment geometry preserves observed segment colours.
    coordinator._notify_callback(None, bytearray(_h6179_status(0x40, b"\x00\x15")))
    assert coordinator.segment_state_source == "observed"
    assert coordinator.segment_colors[-1] == (0x80, 0x80, 0x80)
    coordinator._arm_expected_values({"brightness_pct": 45})
    coordinator._segment_query_generation = coordinator._profile_generation
    coordinator._notify_callback(None, bytearray(_h6179_status(0xA5, H("01640102036404050664070809640a0b0c"))))
    if update == "disconnect-advertisement":
        assert coordinator._physical_ic_count_confirmed
        coordinator._clear_client_state(coordinator._client)
        assert not coordinator._physical_ic_count_confirmed
    before = (
        coordinator._profile_generation,
        dict(coordinator._expected_state),
        coordinator.segment_colors,
        coordinator.segment_brightness,
        coordinator.segment_state_observed_at,
        coordinator._segment_query_generation,
        coordinator._segment_query_colors,
        coordinator._segment_query_brightness,
        set(coordinator._segment_groups_observed),
    )
    if update in {"advertisement", "disconnect-advertisement"}:
        advertisement.manufacturer_data[0x8801] = H("ec00030100")
        coordinator._note_advertisement(advertisement)
    elif update == "resolution":
        coordinator._resolve_device_profile()
    else:
        coordinator._notify_callback(None, bytearray(_h6179_status(0x40, b"\x00\x16")))
    assert coordinator.profile.physical_ic_count == (22 if update == "same-cohort-count" else 21)
    assert coordinator.profile.segment_count == 5
    assert coordinator.profile.whole_device_mask == 0x1F
    assert coordinator.segment_state_source == "observed"
    assert (
        coordinator._profile_generation,
        coordinator._expected_state,
        coordinator.segment_colors,
        coordinator.segment_brightness,
        coordinator.segment_state_observed_at,
        coordinator._segment_query_generation,
        coordinator._segment_query_colors,
        coordinator._segment_query_brightness,
        coordinator._segment_groups_observed,
    ) == before
    if update == "disconnect-advertisement":
        assert not coordinator._physical_ic_count_confirmed
        coordinator._client = MagicMock(is_connected=True)
        coordinator._notify_callback(None, bytearray(_h6179_status(0x40, b"\x00\x15")))
        assert coordinator._physical_ic_count_confirmed
        assert coordinator._profile_generation == before[0]


@pytest.mark.parametrize("array_count", [5, 10])
async def test_h61f5_repeated_ic_count_repairs_topology_before_expanding(hass, array_count):
    from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator

    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H61F5", configuration_url=None)
    coordinator.profile = replace(coordinator.profile, physical_ic_count=21)
    coordinator.segment_colors = [(1, 2, 3)] * array_count
    coordinator.segment_brightness = [40] * array_count
    coordinator.segment_state_source = "observed"
    coordinator._arm_expected_values({"brightness_pct": 45})
    generation = coordinator._profile_generation
    for step, (count, segments) in enumerate(((21, 5), (26, 6), (50, 10)), 1):
        coordinator._notify_callback(None, bytearray(_h6179_status(0x40, count.to_bytes(2, "big"))))
        assert coordinator.profile.physical_ic_count == count
        assert coordinator.profile.segment_count == segments
        assert len(coordinator.segment_colors) == len(coordinator.segment_brightness) == segments
        assert coordinator._profile_generation == generation + step
        assert coordinator._expected_state == {}
        assert coordinator.segment_state_source == "initial"
        coordinator._resolve_device_profile()
        assert coordinator.profile.segment_count == segments
        assert coordinator._profile_generation == generation + step


async def test_h61f5_pact_changes_retain_cut_geometry_and_update_kelvin_bounds(hass):
    from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator

    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H61F5", configuration_url=None)
    coordinator._notify_callback(None, bytearray(_h6179_status(0x40, b"\x00\x15")))
    generation = coordinator._profile_generation
    for step, (pact, kelvin_range) in enumerate(((4, (1000, 10000)), (3, (2700, 6500))), 1):
        coordinator._note_advertisement(
            SimpleNamespace(name="Govee_H61F5_ABCD", manufacturer_data={0x8801: bytes((0xEC, 0, pact, 1, 0))})
        )
        assert coordinator.profile.physical_ic_count == 21
        assert coordinator.profile.segment_count == 5
        assert coordinator.profile.color_temp_range == kelvin_range
        assert coordinator._profile_generation == generation + step


@pytest.mark.parametrize(
    "model,layouts",
    [
        ("H1A42", [(3, 3), (4, 4), (5, 5), (12, 5), (1, 1)]),
        ("H61F5", [(21, 5), (50, 10), (80, 16), (81, 17), (100, 20), (101, 20), (21, 5)]),
        ("H705A", [(36, 9), (72, 18), (108, 27), (35, 8), (12, 3)]),
    ],
)
async def test_reported_strip_layouts_grow_shrink_and_collect_only_installed_records(hass, model, layouts):
    from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator

    c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", model, configuration_url=None)
    for physical, sections in layouts:
        generation, previous = c._profile_generation, c.profile.segment_count
        c._notify_callback(None, bytearray(_h6179_status(0x40, physical.to_bytes(2, "big"))))
        assert c.profile.segment_count == sections
        assert c.profile.physical_ic_count == physical
        assert c._profile_generation == generation + (previous != sections)
        c._resolve_device_profile()
        assert c.profile.segment_count == sections
        assert c.profile.whole_device_mask == (1 << sections) - 1
        c._segment_query_generation = c._profile_generation
        for page in range(1, c.profile.segment_group_count + 1):
            installed = min(4, sections - (page - 1) * 4)
            records = bytes((37, 1, 2, 3)) * installed + bytes((251, 9, 8, 7)) * (4 - installed)
            c._notify_callback(None, bytearray(_h6179_status(0xA5, bytes((page,)) + records)))
        assert c.segment_state_source == "observed"
        assert c.segment_colors == [(1, 2, 3)] * sections
        assert c.segment_brightness == [37] * sections
        revision = c._field_revisions["segment_colors"]
        extra = bytes((c.profile.segment_group_count + 1,)) + bytes((37, 1, 2, 3)) * 4
        c._notify_callback(None, bytearray(_h6179_status(0xA5, extra)))
        assert c._field_revisions["segment_colors"] == revision


@pytest.mark.parametrize("invalid_count", [0, 112])
async def test_impossible_installed_geometry_is_rejected_before_updating_either_count(hass, invalid_count):
    from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator

    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H705A", configuration_url=None)
    coordinator._notify_callback(None, bytearray(_h6179_status(0x40, (72).to_bytes(2, "big"))))
    before = (
        coordinator.profile,
        coordinator._observed_physical_ic_count,
        coordinator._profile_generation,
        dict(coordinator._field_revisions),
    )
    coordinator._notify_callback(None, bytearray(_h6179_status(0x40, invalid_count.to_bytes(2, "big"))))
    assert (
        coordinator.profile,
        coordinator._observed_physical_ic_count,
        coordinator._profile_generation,
        dict(coordinator._field_revisions),
    ) == before
    assert coordinator.packet_log[-1]["reason"] == "semantic_rejected"


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
    assert decode_status_frame_result(issue_frame, "H66A0").parsed is not None


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
