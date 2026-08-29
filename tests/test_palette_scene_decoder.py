"""Lossless decoding for committed palette scene templates."""

from __future__ import annotations

import base64
import binascii
from dataclasses import replace
from typing import Any, cast

import pytest
from kaitaistruct import KaitaiStructError

from custom_components.ha_govee_led_ble.effect_compiler import (
    ActivationMode,
    CompatibilityState,
    compatibility,
    compile_effect,
)
from custom_components.ha_govee_led_ble.effect_domain import (
    BuiltinScene,
    CatalogueRef,
    EffectValidationError,
    LibraryItem,
    PaletteScene,
    SceneStep,
    effect_content_from_dict,
    effect_content_to_dict,
)
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    _A3_MAX_CONTENT,
    MAX_SCENE_PARAM_BYTES,
    _check_tree,
    _write,
    build_h617a_scene,
    parse_scene_type1_body_param,
)
from custom_components.ha_govee_led_ble.native_scenes import build_native_scene_packets
from custom_components.ha_govee_led_ble.palette_scene_decoder import (
    decode_catalogue_palette_scene,
    decode_palette_scene,
    encode_palette_scene,
)
from custom_components.ha_govee_led_ble.scenes import SCENE_ENTRIES, SceneEntry
from custom_components.ha_govee_led_ble.transport import fragment_a3

# The parameter drops the marker, line-count and scene-type bytes the A3 header carries.
_A3_STRIPPED_PREFIX = 3


def _reference(entry: SceneEntry) -> CatalogueRef:
    return CatalogueRef("H617A", entry.scene_id, entry.effect_id)


def _colour(colour: Any) -> tuple[int, int, int]:
    return int(colour.r), int(colour.g), int(colour.b)


def test_all_committed_h617a_type_1_scenes_decode_losslessly() -> None:
    entries = [entry for entry in SCENE_ENTRIES["H617A"] if entry.scene_type == 1]

    for entry in entries:
        raw_param = base64.b64decode(entry.param, validate=True)
        parsed = parse_scene_type1_body_param(raw_param)
        envelope = cast(bytes, parsed._io.to_byte_array())
        parameter_start = len(parsed.header.marker) + 2
        decoded = decode_catalogue_palette_scene("H617A", entry)

        assert decoded is not None
        assert decoded.template == _reference(entry)
        assert decoded.layout == int(parsed.layout) == 0
        assert decoded.brightness_flag is bool(parsed.brightness_flag)
        assert decoded.speed_index is None
        assert decoded.steps == tuple(
            SceneStep(
                value=int(step.value),
                colour=_colour(step.colour),
            )
            for step in parsed.steps
        )
        assert decoded.palette == tuple(_colour(colour) for colour in parsed.palette)
        assert envelope[parameter_start : parameter_start + len(raw_param)] == raw_param
        assert not any(envelope[parameter_start + len(raw_param) :])
        _check_tree(parsed)
        assert _write(parsed, len(envelope)) == envelope
        assert encode_palette_scene(decoded) == raw_param
        assert effect_content_from_dict(effect_content_to_dict(decoded)) == decoded

    assert len(entries) == 2


def test_encode_round_trips_every_committed_type_1_scene() -> None:
    fixtures = 0

    assert SCENE_ENTRIES["H617E"] is SCENE_ENTRIES["H617A"]
    for sku in ("H6125", "H617A", "H6199"):
        entries = SCENE_ENTRIES[sku]
        for entry in entries:
            if entry.scene_type != 1:
                continue
            raw_param = base64.b64decode(entry.param, validate=True)
            decoded = decode_catalogue_palette_scene(sku, entry)
            assert decoded is not None
            assert encode_palette_scene(decoded) == raw_param
            fixtures += 1

    assert fixtures == 6


def test_committed_palette_scenes_compile_to_byte_exact_model_frames() -> None:
    for model in ("H617A", "H617E", "H6199"):
        entries = SCENE_ENTRIES[model]
        entry = next(scene for scene in entries if scene.scene_type == 1)
        decoded = decode_catalogue_palette_scene(model, entry)
        assert decoded is not None

        compiled = compile_effect(LibraryItem.new("Palette scene", decoded), model)
        expected = build_native_scene_packets(model, entry)

        assert compiled.activation_mode is ActivationMode.SCENE
        assert compiled.packets == tuple(expected)
        assert compiled.evidence_codes == ("scene_payload_readback_unavailable",)


def test_h6125_palette_scene_editing_stays_disabled_until_hardware_validation() -> None:
    entry = next(scene for scene in SCENE_ENTRIES["H6125"] if scene.scene_type == 1)
    decoded = decode_catalogue_palette_scene("H6125", entry)

    assert decoded is not None
    with pytest.raises(ValueError, match="edited native scenes are not supported"):
        compile_effect(LibraryItem.new("Palette scene", decoded), "H6125")


def test_edited_palette_scene_compiles_authored_definition_not_catalogue_bytes() -> None:
    entry = next(scene for scene in SCENE_ENTRIES["H617A"] if scene.scene_type == 1)
    decoded = decode_catalogue_palette_scene("H617A", entry)
    assert decoded is not None
    edited = replace(
        decoded,
        steps=(
            replace(decoded.steps[0], colour=(1, 2, 3)),
            *decoded.steps[1:],
        ),
    )
    encoded = encode_palette_scene(edited)

    compiled = compile_effect(LibraryItem.new("Edited palette scene", edited), "H617A")

    assert encoded != base64.b64decode(entry.param, validate=True)
    assert compiled.upload_packets == tuple(fragment_a3(1, encoded))
    assert compiled.activation_packet == build_h617a_scene(entry.code)


def test_saved_native_scene_uses_the_catalogue_application_path() -> None:
    entry = next(scene for scene in SCENE_ENTRIES["H617A"] if scene.scene_type == 1)
    item = LibraryItem.new("Native scene", BuiltinScene(CatalogueRef("H617A", entry.scene_id, entry.effect_id)))

    assert compatibility(item, "H617A").state is CompatibilityState.COMPATIBLE
    assert compile_effect(item, "H617A").packets == tuple(build_native_scene_packets("H617A", entry))


def test_palette_scene_rejects_a_layered_scene_identity_and_speed() -> None:
    palette_entry = next(scene for scene in SCENE_ENTRIES["H617A"] if scene.scene_type == 1)
    layered_entry = next(scene for scene in SCENE_ENTRIES["H617A"] if scene.scene_type == 2)
    decoded = decode_catalogue_palette_scene("H617A", palette_entry)
    assert decoded is not None

    mismatched = replace(
        decoded,
        template=CatalogueRef("H617A", layered_entry.scene_id, layered_entry.effect_id),
    )
    assert (
        compatibility(LibraryItem.new("Mismatched palette scene", mismatched), "H617A").state
        is CompatibilityState.INCOMPATIBLE
    )

    with pytest.raises(ValueError, match="do not expose a documented Speed control"):
        compile_effect(
            LibraryItem.new("Palette scene with speed", replace(decoded, speed_index=1)),
            "H617A",
        )


def test_layout_1_decoding_is_synthetic_schema_support_without_hardware_evidence() -> None:
    raw_param = bytes.fromhex("93010102033412040506")

    decoded = decode_palette_scene(
        CatalogueRef("SYNTHETIC", 1, 1),
        raw_param,
        speed_index=7,
    )

    assert decoded == PaletteScene(
        template=CatalogueRef("SYNTHETIC", 1, 1),
        layout=1,
        brightness_flag=True,
        steps=(
            SceneStep(
                value=0x1234,
                colour=(1, 2, 3),
                inline_colour=(4, 5, 6),
            ),
        ),
        speed_index=7,
    )
    assert encode_palette_scene(decoded) == raw_param
    assert effect_content_from_dict(effect_content_to_dict(decoded)) == decoded


@pytest.mark.parametrize(
    ("raw_param", "expected_steps", "expected_palette"),
    [
        (bytes.fromhex("830000"), 0, 0),
        (
            b"\x83\xff" + bytes.fromhex("0102033412") * 255 + b"\xff" + bytes.fromhex("040506") * 255,
            255,
            255,
        ),
    ],
)
def test_layout_0_preserves_full_u1_count_boundaries(
    raw_param: bytes,
    expected_steps: int,
    expected_palette: int,
) -> None:
    decoded = decode_palette_scene(CatalogueRef("SYNTHETIC", 1, 1), raw_param)

    assert len(decoded.steps) == expected_steps
    assert len(decoded.palette) == expected_palette
    assert encode_palette_scene(decoded) == raw_param
    assert effect_content_from_dict(effect_content_to_dict(decoded)) == decoded


def test_encode_preserves_reserved_config_bit_without_hardware_evidence() -> None:
    raw_param = bytes.fromhex("8b0000")

    decoded = decode_palette_scene(CatalogueRef("SYNTHETIC", 1, 1), raw_param)

    assert decoded.config_flags == 0x08
    assert encode_palette_scene(decoded) == raw_param
    assert effect_content_from_dict(effect_content_to_dict(decoded)) == decoded


@pytest.mark.parametrize("padding", [1, 2, 5, 17, 34])
def test_decode_preserves_real_trailing_zero_padding(padding: int) -> None:
    raw_param = bytes.fromhex("830000") + b"\x00" * padding

    decoded = decode_palette_scene(CatalogueRef("SYNTHETIC", 1, 1), raw_param)

    assert decoded.trailing_padding == padding
    assert encode_palette_scene(decoded) == raw_param
    assert effect_content_from_dict(effect_content_to_dict(decoded)) == decoded


def test_construction_rejects_trailing_padding_beyond_the_framing_limit() -> None:
    base = PaletteScene(
        template=CatalogueRef("SYNTHETIC", 1, 1),
        layout=0,
        brightness_flag=False,
        steps=(),
        palette=(),
    )

    replace(base, trailing_padding=MAX_SCENE_PARAM_BYTES)

    with pytest.raises(EffectValidationError, match="trailing padding"):
        replace(base, trailing_padding=MAX_SCENE_PARAM_BYTES + 1)


def test_encode_rejects_type_1_content_beyond_the_line_count() -> None:
    base = PaletteScene(
        template=CatalogueRef("SYNTHETIC", 1, 1),
        layout=0,
        brightness_flag=False,
        steps=(),
        palette=(),
    )
    largest = _A3_MAX_CONTENT - _A3_STRIPPED_PREFIX - len(encode_palette_scene(base))

    encoded = encode_palette_scene(replace(base, trailing_padding=largest))
    assert len(encoded) + _A3_STRIPPED_PREFIX == _A3_MAX_CONTENT

    with pytest.raises(EffectValidationError, match="A3 line count"):
        encode_palette_scene(replace(base, trailing_padding=largest + 1))


@pytest.mark.parametrize(
    "scene",
    [
        PaletteScene(
            template=CatalogueRef("SYNTHETIC", 1, 1),
            layout=0,
            brightness_flag=False,
            steps=(SceneStep(value=0x0102, colour=(9, 8, 7)),),
            palette=((1, 2, 3),),
            config_flags=0x08,
        ),
        PaletteScene(
            template=CatalogueRef("SYNTHETIC", 1, 1),
            layout=1,
            brightness_flag=True,
            steps=(SceneStep(value=0x1234, colour=(1, 2, 3), inline_colour=(4, 5, 6)),),
            speed_index=7,
        ),
    ],
)
def test_encode_then_decode_round_trips_canonical_palette_values(scene: PaletteScene) -> None:
    decoded = decode_palette_scene(scene.template, encode_palette_scene(scene), speed_index=scene.speed_index)

    assert decoded == scene


@pytest.mark.parametrize("raw_param", [bytearray(b"\x83"), memoryview(b"\x83"), "\x83"])
def test_generated_type_1_parser_requires_bytes(raw_param) -> None:
    with pytest.raises(TypeError, match="must be bytes"):
        parse_scene_type1_body_param(raw_param)


@pytest.mark.parametrize(
    "raw_param",
    [
        b"",
        b"\x83",
        b"\x83\x01\x01",
        b"\x83\x00",
        b"\x82\x00\x00",
        b"\x83\x00\x00\x01",
    ],
)
def test_generated_type_1_parser_rejects_invalid_parameters(raw_param: bytes) -> None:
    with pytest.raises(KaitaiStructError):
        parse_scene_type1_body_param(raw_param)


def test_catalogue_decoder_rejects_invalid_base64_and_missing_parameters() -> None:
    entry = next(entry for entry in SCENE_ENTRIES["H617A"] if entry.scene_type == 1)

    with pytest.raises(binascii.Error):
        decode_catalogue_palette_scene("H617A", replace(entry, param=f"{entry.param}\n"))
    with pytest.raises(ValueError, match="has no parameter"):
        decode_catalogue_palette_scene("H617A", replace(entry, param=""))
    assert decode_catalogue_palette_scene("H617A", replace(entry, scene_type=0)) is None
