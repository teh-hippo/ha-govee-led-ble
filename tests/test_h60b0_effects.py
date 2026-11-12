"""Focused combined scenes, native DIY revisions and onboard music contracts."""

import base64
import json
from dataclasses import replace
from unittest.mock import Mock

import pytest

from custom_components.ha_govee_led_ble.const import device_profile
from custom_components.ha_govee_led_ble.h60b0_diy import H60b0DiyV3, encode_h60b0_diy, validate_h60b0_diy
from custom_components.ha_govee_led_ble.h60b0_effects import (
    combined_upload_body,
    decode_combined_scene,
    encode_combined_scene,
    encode_h60b0_music_zones,
    h60b0_music_zones,
    parse_combined_scene,
)
from custom_components.ha_govee_led_ble.layered_scene import (
    CatalogueRef,
    layered_scene_from_value,
    layered_scene_to_value,
)
from custom_components.ha_govee_led_ble.music_commands import music_body_style, prepare_music_body_writes
from custom_components.ha_govee_led_ble.music_semantics import H60B0_MUSIC_VARIANTS, MusicZone
from custom_components.ha_govee_led_ble.native_effect import NativeDiyLayer, NativeEffect, NativeOpaqueLayer
from custom_components.ha_govee_led_ble.native_scenes import apply_scene_speed, build_native_scene_packets
from custom_components.ha_govee_led_ble.protocol_music_params import encode_music_parameters, parse_music_parameters
from custom_components.ha_govee_led_ble.scenes import CATALOGUE_DIR, SCENE_ENTRIES, ScenePage, SceneSpeed
from custom_components.ha_govee_led_ble.transport import reassemble_a3


def _combined_payloads():
    snapshot = json.loads((CATALOGUE_DIR / "H60B0.json").read_text())
    return tuple(
        (effect, base64.b64decode(effect["param"], validate=True))
        for effect in snapshot["effects"]
        if effect["scene_type"] == 6
    )


@pytest.mark.parametrize(
    "effect,payload", _combined_payloads(), ids=lambda value: value.get("name") if isinstance(value, dict) else None
)
def test_combined_catalogue_lossless_semantics(effect, payload):
    template = CatalogueRef("H60B0", effect["scene_id"], effect["effect_id"])
    decoded = decode_combined_scene(template, payload)
    restored = layered_scene_from_value(layered_scene_to_value(decoded))
    assert encode_combined_scene(restored) == payload
    assert restored.ripple_layers


def test_combined_upload_is_pure_and_preserves_nonzero_extensions():
    payload = _combined_payloads()[0][1] + b"\x8a\xfe"
    original = bytearray(payload)
    length = int.from_bytes(payload[1:3], "big")
    expected = (length - 1).to_bytes(2, "big") + payload[4:]
    assert combined_upload_body(original) == expected
    assert combined_upload_body(original) == expected
    assert bytes(original) == payload
    with pytest.raises(ValueError):
        combined_upload_body(expected)


def test_combined_catalogue_upload_preserves_its_actual_selector():
    entry = next(scene for scene in SCENE_ENTRIES["H60B0"] if scene.scene_type == 6 and scene.speed is None)
    packets = build_native_scene_packets("H60B0", entry, profile=device_profile("H60B0", 1, 1))
    body = combined_upload_body(base64.b64decode(entry.param, validate=True))
    envelope = reassemble_a3(packets[:-1])
    assert envelope[2] == 0x5A
    assert envelope[3 : 3 + len(body)] == body
    assert not any(envelope[3 + len(body) :])
    assert packets[-1][:5] == b"\x33\x05\x04" + entry.code.to_bytes(2, "little")


def test_authored_combination_roundtrips_and_requires_a_known_pact(monkeypatch):
    from custom_components.ha_govee_led_ble import effect_compiler
    from custom_components.ha_govee_led_ble.effect_domain import (
        LibraryItem,
        effect_content_from_dict,
        effect_content_to_dict,
    )

    combined = decode_combined_scene(CatalogueRef("H60B0", 0, 510), _combined_payloads()[0][1])
    content = NativeEffect(model="H60B0", family=81, layers=(), combined=combined)
    restored = effect_content_from_dict(effect_content_to_dict(content))
    assert restored == content
    assert encode_h60b0_diy(restored) == combined_upload_body(combined.raw_param)
    encode = Mock(wraps=effect_compiler.encode_native_body)
    monkeypatch.setattr(effect_compiler, "encode_native_body", encode)
    compiled = effect_compiler.compile_effect(
        LibraryItem.new("Combined", content), "H60B0", profile=device_profile("H60B0", 1, 1)
    )
    encode.assert_called_once_with(content)
    assert reassemble_a3(compiled.upload_packets)[3:].startswith(combined_upload_body(combined.raw_param))
    for revision in (1, 2, 3):
        validate_h60b0_diy(content, revision)
    with pytest.raises(ValueError, match="Pact"):
        validate_h60b0_diy(content, 0)
    oversized = replace(combined, ripple_layers=(replace(combined.ripple_layers[0], palette=((1, 2, 3),) * 85),))
    with pytest.raises(ValueError, match="length field"):
        encode_combined_scene(oversized)


def test_combined_speed_edits_both_engines_and_retains_extensions():
    payload = _combined_payloads()[0][1] + b"\x80\x91"
    speed = SceneSpeed(
        default_index=0,
        pages=(
            ScenePage(0, move_all=(12, 34), ripple_colour_speed=(10, 70), ripple_movement_speed=(20, 80)),
            ScenePage(1, ripple_colour_speed=(11, 77), ripple_movement_speed=(22, 88)),
        ),
    )
    updated = parse_combined_scene(apply_scene_speed(payload, speed, 1, scene_type=6))
    assert updated.rgbic.records[0].body.overall_movement.speed == 34
    assert [record.body.colour_speed for record in updated.ripple.records] == [70, 77]
    assert [record.body.movement_speed for record in updated.ripple.records] == [80, 88]
    assert updated.unknown_tail == b"\x80\x91"
    with pytest.raises(ValueError):
        apply_scene_speed(payload, speed, 2, scene_type=6)


def test_legacy_native_diy_body_and_revision_rejection():
    content = NativeEffect(
        model="H60B0",
        revision=1,
        family=8,
        layers=(NativeDiyLayer(8, 50, ((255, 0, 0),), secondary_palette=((0, 0, 255),)),),
    )
    assert encode_h60b0_diy(content) == bytes.fromhex("080032010000ff01ff0000")
    validate_h60b0_diy(content, 2)
    with pytest.raises(ValueError, match="revision"):
        validate_h60b0_diy(content, 3)
    with pytest.raises(ValueError, match="revision"):
        validate_h60b0_diy(content, 0)


def test_legacy_advanced_disabled_side_and_ripple_parameters():
    content = NativeEffect(
        model="H60B0",
        revision=1,
        family=13,
        layers=(NativeDiyLayer(2, 50, ((1, 2, 3),), direction=1, flag=25), NativeDiyLayer(0, 0, (), enabled=False)),
    )
    assert encode_h60b0_diy(content) == bytes.fromhex("0d020800320101020301190000")


@pytest.mark.parametrize("placeholder_palette", [False, True])
def test_three_source_diy_lengths_temperature_and_safety(placeholder_palette):
    off = NativeDiyLayer(1, 0, ())
    content = NativeEffect(
        model="H60B0",
        revision=3,
        family=922,
        layers=(
            NativeDiyLayer(1, 50, (), enabled=False, parameter=50, direction=1),
            off,
            NativeDiyLayer(2, 50, ((255, 249, 251),) if placeholder_palette else (), points=(1,), temperatures=(6500,)),
        ),
    )
    payload = encode_h60b0_diy(content)
    assert payload == bytes.fromhex("100003320100010109023201016419fff9fb")
    parsed = H60b0DiyV3.from_bytes(payload)
    parsed._read()
    assert parsed.body.bottom.body.colours[0].kelvin == 6500
    with pytest.raises(ValueError, match="temperature records"):
        validate_h60b0_diy(
            replace(content, layers=(*content.layers[:2], replace(content.layers[2], kind=3, points=(50,)))), 3
        )
    with pytest.raises(ValueError):
        encode_h60b0_diy(
            replace(
                content,
                layers=(
                    *content.layers[:2],
                    replace(content.layers[2], kind=3, points=(101, 100)),
                ),
            )
        )
    with pytest.raises(ValueError, match="Unqualified"):
        validate_h60b0_diy(replace(content, layers=(NativeOpaqueLayer(1, b"\x01"), *content.layers[1:])), 3)
    with pytest.raises(ValueError, match="all three"):
        encode_h60b0_diy(
            replace(content, layers=(content.layers[0], NativeDiyLayer(2, 50, ((1, 2, 3),)), content.layers[2]))
        )


def test_three_source_top_kelvin_derives_the_qualified_companion():
    off = NativeDiyLayer(1, 0, ())
    content = NativeEffect(
        model="H60B0",
        revision=3,
        family=923,
        layers=(NativeDiyLayer(7, 0, (), parameter=50, direction=1, flag=100, angle=4000), off, off),
    )
    payload = encode_h60b0_diy(content)
    assert payload == bytes.fromhex("0f000a3201010764a00fffd5a101010101")
    root = H60b0DiyV3.from_bytes(payload)
    root._read()
    assert root.body.top.body.kelvin == 4000
    assert root.body.top.body.brightness == 100
    colour = root.body.top.body.companion
    assert (colour.red, colour.green, colour.blue) == (255, 213, 161)


def test_music_style_palette_and_hopping_budget():
    style = next(variant for variant in H60B0_MUSIC_VARIANTS if variant.mode_code == 48)
    encoded = encode_music_parameters(style, {}, palette=[(1, 2, 3), (4, 5, 6)], calm=True)
    assert encoded == bytes.fromhex("300201020304050601")
    assert encode_music_parameters(style, {}, palette=[(1, 2, 3), (4, 5, 6)], calm=False) == bytes.fromhex(
        "300201020304050600"
    )
    hopping = next(variant for variant in H60B0_MUSIC_VARIANTS if variant.mode_code == 51)
    with pytest.raises(ValueError, match="physical"):
        encode_music_parameters(hopping, {}, palette=None, calm=None)
    encoded = encode_music_parameters(
        hopping,
        {"background": 0x010203, "relative_brightness": 15},
        palette=[(4, 5, 6)],
        calm=None,
        physical_ic_count=9,
    )
    assert encoded == bytes.fromhex("33010405060102030f6201030204")


@pytest.mark.parametrize("mode,code", [("bloom", 48), ("shiny", 49)])
@pytest.mark.parametrize("calm", [False, True])
def test_retained_music_style_matches_the_encoded_enum(mode, code, calm):
    profile = device_profile("H60B0", 1, 2)
    variant = next(variant for variant in profile.music_variants if variant.mode_code == code)
    body = encode_music_parameters(variant, {}, palette=None, calm=calm)
    assert music_body_style(body, mode, profile=profile) is calm
    states = [state for _, state in prepare_music_body_writes("H60B0", mode, 50, body, profile=profile)]
    retained = next(state for state in states if isinstance(state.get("_music_body"), tuple))
    assert retained["music_calm"] is calm


def test_combined_music_has_independently_bounded_source_parameters(monkeypatch):
    from custom_components.ha_govee_led_ble import h60b0_effects

    profile = replace(
        device_profile("H60B0", 1, 1),
        music_modes=("spectrum", "hopping", "flow", "firefly", "bloom", "rhythm", "shiny", "combined"),
        music_variants=H60B0_MUSIC_VARIANTS,
    )
    zones = (
        MusicZone("side", "bloom", palette=((1, 2, 3), (4, 5, 6)), calm=True),
        MusicZone("ripple", "spectrum", palette=((7, 8, 9),)),
    )
    serialise = Mock(wraps=h60b0_effects.serialize_native_body)
    monkeypatch.setattr(h60b0_effects, "serialize_native_body", serialise)
    encoded = encode_h60b0_music_zones(profile, zones)
    assert serialise.call_count == 3
    assert encoded == bytes.fromhex("8230080201020304050601830401070809")
    restored = h60b0_music_zones(encoded)
    assert restored[0].calm is True
    assert encode_h60b0_music_zones(profile, restored) == encoded
    with pytest.raises(ValueError, match="eligible"):
        encode_h60b0_music_zones(profile, (zones[0], replace(zones[1], mode="flow")))
    variant = next(variant for variant in H60B0_MUSIC_VARIANTS if variant.mode_code == 130)
    parsed = parse_music_parameters(variant, variant.template)
    assert int(parsed.body.side.mode) == 48
    assert int(parsed.body.ripple.mode) == 131
