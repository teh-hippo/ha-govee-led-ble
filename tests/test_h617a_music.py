"""Local APK/contract regressions; synthetic uploads do not qualify device playback."""

from dataclasses import replace

import pytest

from custom_components.ha_govee_led_ble.const import MUSIC_MODE_SLUGS, get_profile
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_expectations import expectations_from_packet
from custom_components.ha_govee_led_ble.coordinator_status import decode_status_frame, parse_color_mode
from custom_components.ha_govee_led_ble.effect_catalogue import MODEL_EFFECT_CATALOGUES
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    MusicBody,
    build_music_mode,
    encode_music_parameters,
    music_default_palette,
)
from custom_components.ha_govee_led_ble.music_commands import (
    build_music_params,
    prepare_music_profile_writes,
    resolve_music_profile,
)
from custom_components.ha_govee_led_ble.music_semantics import music_params_for_mode, music_variant
from custom_components.ha_govee_led_ble.transport import reassemble_a3, xor_checksum

NEW_MODES = (0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x37)
PROFILE = get_profile("H617A")


def frame(prefix):
    body = bytes.fromhex(prefix).ljust(19, b"\0")
    return body + bytes([xor_checksum(body)])


def parse_body(body):
    parsed = MusicBody.from_bytes(body)
    parsed._read()
    return parsed


@pytest.mark.parametrize("model", ("H617A", "H617E", "H6099"))
@pytest.mark.parametrize("mode", NEW_MODES)
def test_tail_schema_ownership_is_independent_of_product_permissions(model, mode):
    from custom_components.ha_govee_led_ble.generated_protocol_adapter import parse_music_parameters

    profile = get_profile(model)
    variant = music_variant(profile, mode)
    parsed = parse_music_parameters(variant, variant.template)
    module = "h6099_music_parameters" if model == "H6099" else "h617a_control_payload"
    assert type(parsed.tail).__module__.endswith("." + module)
    if model == "H617E":
        assert variant.palette_bounds is None
        assert not profile.music_requires_upload_ack


@pytest.mark.parametrize("mode", NEW_MODES)
@pytest.mark.parametrize("size", range(1, 9))
def test_variable_palette_preserves_complete_preset_tail(mode, size):
    variant = music_variant(PROFILE, mode)
    original = parse_body(b"\x01\x02\x41" + variant.template)
    palette = [(index, 32, 160) for index in range(size)]
    body = encode_music_parameters(variant, {}, palette=palette, calm=False)
    parsed = parse_body(b"\x01\x02\x41" + body)
    assert parsed.num_palette == size
    assert [(rgb.red, rgb.green, rgb.blue) for rgb in parsed.palette] == palette
    assert parsed._raw_tail == original._raw_tail
    assert parsed.padding == original.padding
    assert len(body) == len(variant.template) + 3 * (size - original.num_palette)
    upload = parse_body(reassemble_a3(build_music_params(mode, {}, palette=palette, profile=PROFILE)))
    assert upload._raw_tail == original._raw_tail


@pytest.mark.parametrize("mode", NEW_MODES)
@pytest.mark.parametrize("palette", [[], [(0, 0, 0)] * 9, [(True, 0, 0)], [(256, 0, 0)], [(1, 2)]])
def test_invalid_palettes_fail_before_writes(mode, palette):
    with pytest.raises(ValueError):
        build_music_params(mode, {}, palette=palette, profile=PROFILE)


@pytest.mark.parametrize("mode", NEW_MODES)
@pytest.mark.parametrize("suffix", ["0000000000", "01ff2060a0"])
def test_new_selector_has_no_style_or_colour_authority(mode, suffix):
    response = decode_status_frame(frame(f"aa0513{mode:02x}32{suffix}"))
    parsed = parse_color_mode(response.generated, "H617A")
    assert parsed.music_sensitivity == 50
    assert parsed.music_calm is None and parsed.music_color is None and not parsed.music_color_present
    slug = next(slug for slug, code in MUSIC_MODE_SLUGS.items() if code == mode)
    packet = build_music_mode(mode, 50, None, mode in (0x30, 0x31))
    assert packet == frame(f"330513{mode:02x}32")
    expected = expectations_from_packet(packet)
    assert expected["music_mode"] == slug and expected["music_sensitivity"] == 50
    assert "music_color" not in expected and "music_calm" not in expected
    writes = prepare_music_profile_writes("H617A", slug, 50, None, False, {}, include_parameters=False)
    assert "music_color" not in writes[1][1] and "music_calm" not in writes[1][1]


@pytest.mark.parametrize("mode", (3, 4, 5, 6))
@pytest.mark.parametrize("flag", (0, 1, 2, 255))
def test_legacy_colour_is_nonzero_flag_not_count(mode, flag):
    response = decode_status_frame(frame(f"aa0513{mode:02x}3201{flag:02x}2060a0"))
    parsed = parse_color_mode(response.generated, "H617A")
    assert parsed.music_color_present
    assert parsed.music_color == ((32, 96, 160) if flag else None)
    assert parsed.music_calm == (True if mode == 3 else None)
    expected = expectations_from_packet(frame(f"330513{mode:02x}3201{flag:02x}2060a0"))
    assert expected["music_color"] == parsed.music_color


def test_exact_h617a_contract_and_dependent_controls():
    settings = MODEL_EFFECT_CATALOGUES["H617A"].to_dict()["music_settings"]
    for slug in ("spectrum", "rolling"):
        assert settings[slug]["colour"]
        resolve_music_profile("H617A", slug, 50, (32, 96, 160), None, {})
    assert not settings["energetic"]["colour"]
    with pytest.raises(ValueError, match="fixed music colour"):
        resolve_music_profile("H617A", "energetic", 50, (32, 96, 160), None, {})
    assert PROFILE.physical_ic_count is None
    for mode in NEW_MODES:
        slug = next(slug for slug, code in MUSIC_MODE_SLUGS.items() if code == mode)
        assert settings[slug]["palette"]["min"] == 1 and settings[slug]["palette"]["max"] == 8
        assert not settings[slug]["colour"]
    assert set(settings["piano_keys"]["parameters"]) == {"gradient"}
    assert set(settings["hopping"]["parameters"]) == {"background", "relative_brightness"}
    for mode, parameter in ((0x32, "gradient"), (0x34, "key_count"), (0x35, "direction"), (0x37, "segment_count")):
        assert parameter not in {spec.profile_key for spec in music_params_for_mode(mode, PROFILE)}
        assert parameter in {
            spec.profile_key for spec in music_params_for_mode(mode, replace(PROFILE, physical_ic_count=60))
        }


def test_background_gradient_and_unexposed_companions_survive_palette_resize():
    # Synthetic alternate tail values must parse and survive, not become literal reset defaults.
    hopping = music_variant(PROFILE, 0x33)
    original = parse_body(b"\x01\x02\x41" + hopping.template)
    template = bytes.fromhex("3301010203aabbcc196104050708")
    variant = replace(hopping, template=template)
    encoded = encode_music_parameters(variant, {"background": 0x010101}, palette=[(9, 8, 7)] * 8, calm=False)
    parsed = parse_body(b"\x01\x02\x41" + encoded)
    assert parsed._raw_tail == bytes.fromhex("010101196104050708")
    assert original._raw_tail == bytes.fromhex("ff0000326201030206")
    piano = replace(music_variant(PROFILE, 0x34), template=bytes.fromhex("3401010203000f0b090a"))
    encoded = encode_music_parameters(piano, {"gradient": True}, palette=[(9, 8, 7)] * 8, calm=False)
    assert parse_body(b"\x01\x02\x41" + encoded)._raw_tail == bytes.fromhex("010f0b090a")
    # Re-encoding a known complete preset is distinct from recovering unknown resident settings.
    writes = prepare_music_profile_writes("H617A", "hopping", 50, None, False, {"background": 0x010101})
    assert writes[1][1]["_music_palette"] is None
    assert writes[-2][1]["music_hopping_background"] == 0x010101
    assert writes[-2][1]["_music_palette"] == ("hopping", music_default_palette(hopping))


def test_explicit_physical_ic_metadata_qualifies_only_dependent_transforms():
    profile = replace(PROFILE, physical_ic_count=60)
    piano = parse_body(reassemble_a3(build_music_params(0x34, {"key_count": 18, "gradient": True}, profile=profile)))
    assert piano._raw_tail == bytes.fromhex("0112230109")
    separation = parse_body(reassemble_a3(build_music_params(0x32, {"gradient": False}, profile=profile)))
    assert separation.tail.speed == 99
    fountain = parse_body(reassemble_a3(build_music_params(0x35, {"direction": "two_way"}, profile=profile)))
    assert (fountain.tail.start_point, fountain.tail.piece_len, fountain.tail.piece_num) == (1, 2, 6)
    daynight = music_params_for_mode(0x37, profile)
    assert daynight[0].max_value == 12


def test_new_notification_preserves_siblings_without_fabricating_observations(hass):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A", configuration_url=None)
    coordinator.music_mode = "bloom"
    coordinator.music_calm = True
    coordinator.music_color = (32, 96, 160)
    coordinator._music_palette = ("bloom", ((12, 34, 56),))
    coordinator._notify_callback(None, bytearray(frame("aa05133032")))
    assert coordinator.music_calm and coordinator.music_color == (32, 96, 160)
    assert coordinator.music_palette == ((12, 34, 56),)
    assert coordinator.music_sensitivity == 50
    assert "music_calm" not in coordinator._field_revisions and "music_color" not in coordinator._field_revisions
    coordinator._notify_callback(None, bytearray(frame("aa051303320100")))
    assert coordinator.music_color is None and coordinator._field_revisions["music_color"] == 1
