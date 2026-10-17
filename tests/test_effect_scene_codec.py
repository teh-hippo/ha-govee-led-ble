"""Lossless decoding for committed layered scene templates."""

from __future__ import annotations

import base64
from collections import Counter
from dataclasses import replace
from typing import cast

import pytest

from custom_components.ha_govee_led_ble import effect_contracts
from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, ModelProfile
from custom_components.ha_govee_led_ble.effect_compiler import (
    ActivationMode,
    CompatibilityState,
    compatibility,
    compile_effect,
)
from custom_components.ha_govee_led_ble.effect_contracts import ApplicationRoute, CapabilityWorkflow, release_capability
from custom_components.ha_govee_led_ble.effect_domain import (
    BuiltinScene,
    CatalogueRef,
    LayeredScene,
    LibraryItem,
    effect_content_from_dict,
    effect_content_to_dict,
)
from custom_components.ha_govee_led_ble.generated_protocol.scene_body import SceneBody
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    _check_tree,
    _write,
    build_scene_activation,
    parse_scene_body_param,
)
from custom_components.ha_govee_led_ble.layered_scene_decoder import decode_layered_scene, encode_layered_scene
from custom_components.ha_govee_led_ble.native_scenes import apply_scene_speed, build_native_scene_packets
from custom_components.ha_govee_led_ble.palette_scene_decoder import decode_catalogue_palette_scene
from custom_components.ha_govee_led_ble.scenes import MODEL_SCENES, SCENE_ENTRIES, SceneEntry
from custom_components.ha_govee_led_ble.transport import fragment_a3, xor_checksum
from tests.test_layered_scene import _assert_layer_matches

_LAYERED_SCENE_TYPE = int(SceneBody.SceneType.scene_v2)


def _reference(sku: str, entry: SceneEntry) -> CatalogueRef:
    return CatalogueRef(sku, entry.scene_id, entry.effect_id)


def _raw_param(entry: SceneEntry) -> bytes:
    return base64.b64decode(entry.param, validate=True)


def test_inert_catalogue_metadata_does_not_enable_scene_compilation() -> None:
    entry = SCENE_ENTRIES["H6076"][0]
    item = LibraryItem.new("Unsupported scene", BuiltinScene(_reference("H6076", entry)))

    result = compatibility(item, "H6076")

    assert result.state is CompatibilityState.INCOMPATIBLE
    assert result.reasons == ("H6076 native scenes are not supported",)
    with pytest.raises(ValueError, match="native scenes are not supported"):
        compile_effect(item, "H6076")


def test_all_legacy_h617e_saved_scenes_remain_compilable() -> None:
    for legacy in SCENE_ENTRIES["H617A"]:
        item = LibraryItem.new(
            "Legacy H617E scene",
            BuiltinScene(
                _reference("H617E", legacy),
                speed_index=legacy.speed.default_index if legacy.speed is not None else None,
            ),
        )

        compiled = compile_effect(item, "H617E")

        assert compiled.packets == tuple(
            build_native_scene_packets(
                "H617E",
                legacy,
                speed_index=legacy.speed.default_index if legacy.speed is not None else None,
            )
        )


def test_all_committed_type_2_scenes_decode_losslessly() -> None:
    scene_counts: Counter[str] = Counter()
    layer_count = 0
    catalogue_unknown_flags = 0
    catalogue_excess = 0
    multi_line_bodies = 0

    for sku in ("H6125", "H617A", "H617C", "H617F", "H6199"):
        entries = SCENE_ENTRIES[sku]
        for entry in entries:
            if entry.scene_type != _LAYERED_SCENE_TYPE:
                continue
            raw_param = _raw_param(entry)
            parsed = parse_scene_body_param(raw_param)
            synthetic_envelope = cast(bytes, parsed._io.to_byte_array())
            assert len(synthetic_envelope) == int(parsed.header.linecount) * 17
            _check_tree(parsed)
            assert _write(parsed, len(synthetic_envelope)) == synthetic_envelope

            decoded = decode_layered_scene(
                _reference(sku, entry),
                raw_param,
                speed_index=entry.speed.default_index if entry.speed is not None else None,
            )
            document = effect_content_to_dict(decoded)
            restored = effect_content_from_dict(document)

            assert document["raw_param"] == raw_param.hex()
            assert isinstance(restored, LayeredScene)
            assert restored == decoded
            assert restored.raw_param == raw_param
            assert encode_layered_scene(decoded) == raw_param
            assert len(decoded.effect.layers) == len(parsed.records)
            for layer, record in zip(decoded.effect.layers, parsed.records, strict=True):
                _assert_layer_matches(layer, record.body)
                catalogue_unknown_flags += layer.unknown_flags
                catalogue_unknown_flags += layer.selected_movement.unknown_flags
                catalogue_unknown_flags += layer.overall_movement.unknown_flags
                catalogue_excess += len(layer.excess)

            scene_counts[sku] += 1
            layer_count += len(decoded.effect.layers)
            multi_line_bodies += parsed.header.linecount > 2

    assert scene_counts == {"H6125": 226, "H617A": 72, "H617C": 226, "H617F": 226, "H6199": 226}
    assert layer_count == 2879
    assert catalogue_unknown_flags == 0
    assert catalogue_excess == 0
    assert multi_line_bodies > 0


def test_unknown_flags_and_excess_survive_decode_and_json() -> None:
    entry = next(scene for scene in SCENE_ENTRIES["H617A"] if scene.scene_type == _LAYERED_SCENE_TYPE)
    raw_param = _raw_param(entry)
    parsed = parse_scene_body_param(raw_param)
    original_envelope = cast(bytes, parsed._io.to_byte_array())
    prefix_length = len(original_envelope) - len(raw_param) - len(parsed.padding)
    record = parsed.records[0]
    record.body.layer_flags |= 0x80
    record.body.selected_area_movement.packed |= 0x20
    record.body.select_type = 0xFE
    record.body.brightness_blocks[0].brightness_order = 0xFD
    record.body.excess = b"\xaa\xbb"
    record.len_body += len(record.body.excess)
    parsed.padding = []
    _check_tree(parsed)
    synthetic_envelope = _write(parsed, prefix_length + len(raw_param) + len(record.body.excess))
    synthetic_param = synthetic_envelope[prefix_length:]

    decoded = decode_layered_scene(_reference("H617A", entry), synthetic_param)
    restored = effect_content_from_dict(effect_content_to_dict(decoded))

    assert isinstance(restored, LayeredScene)
    assert restored == decoded
    assert restored.raw_param == synthetic_param
    assert restored.effect.layers[0].unknown_flags == 0x80
    assert restored.effect.layers[0].selected_movement.unknown_flags == 0x20
    assert restored.effect.layers[0].selection.type == 0xFE
    assert restored.effect.layers[0].brightness_patterns[0].order == 0xFD
    assert restored.effect.layers[0].excess == b"\xaa\xbb"
    assert encode_layered_scene(decoded) == synthetic_param
    assert decode_layered_scene(_reference("H617A", entry), encode_layered_scene(decoded)) == decoded


def test_decoded_layered_scenes_compile_to_byte_exact_model_frames() -> None:
    for model in ("H617A", "H6199"):
        entry = next(scene for scene in SCENE_ENTRIES[model] if scene.scene_type == _LAYERED_SCENE_TYPE)
        content = decode_layered_scene(
            _reference(model, entry),
            _raw_param(entry),
            speed_index=entry.speed.default_index if entry.speed is not None else None,
        )
        item = LibraryItem.new("Layered template", content)

        assert compatibility(item, model).state is CompatibilityState.COMPATIBLE
        compiled = compile_effect(item, model)
        expected = build_native_scene_packets(model, entry, speed_index=content.speed_index)

        assert compiled.activation_mode is ActivationMode.SCENE
        assert compiled.selector_kind == "scene"
        assert compiled.packets == tuple(expected)
        assert compiled.evidence_codes == (
            "scene_payload_readback_unavailable",
            "layered_field_semantics_uncalibrated",
        )


@pytest.mark.parametrize("grammar", ["H617A", "H6199"])
@pytest.mark.parametrize("scene_type", [0, 1, 2])
@pytest.mark.parametrize("disabled_route", [ApplicationRoute.NONE, ApplicationRoute.STUDIO_SCENE_APPLY])
def test_exact_qualified_scene_routes_share_native_and_authored_activation(
    monkeypatch, grammar, scene_type, disabled_route
):
    model = "H9999"
    entry = next(scene for scene in SCENE_ENTRIES[grammar] if scene.scene_type == scene_type)
    # Independent nonzero selectors distinguish music bytes from H617A's scene type.
    entry = replace(entry, code=0x1234, music_code=0x5678)
    monkeypatch.setitem(
        MODEL_PROFILES,
        model,
        ModelProfile(
            "Synthetic",
            command_grammar=grammar,
            effect_grammar=grammar,
            supports_scenes=True,
            advanced_scene_carrier=(entry.scene_id, entry.effect_id),
        ),
    )
    monkeypatch.setitem(MODEL_SCENES, model, {"synthetic": entry})
    content = BuiltinScene(_reference(model, entry))
    items = [(LibraryItem.new("Native", content), CapabilityWorkflow.NATIVE_SCENES)]
    if scene_type == 1:
        authored = decode_catalogue_palette_scene(model, entry)
        assert authored is not None
        items.append((LibraryItem.new("Palette", authored), CapabilityWorkflow.EDITED_PALETTE_SCENES))
    elif scene_type == 2:
        authored = decode_layered_scene(_reference(model, entry), _raw_param(entry))
        items.extend(
            [
                (LibraryItem.new("Layered", authored), CapabilityWorkflow.LAYERED_SCENES),
                (LibraryItem.new("Advanced", authored.effect), CapabilityWorkflow.ADVANCED),
            ]
        )
    prefix = bytes.fromhex("3305043412") + (bytes.fromhex("7856") if grammar == "H6199" else b"\x00\x00")
    frame = prefix.ljust(19, b"\x00")
    expected_activation = frame + bytes([xor_checksum(frame)])
    native_packets = tuple(build_native_scene_packets(model, entry))
    assert native_packets[-1] == expected_activation

    for item, workflow in items:
        assert compatibility(item, model).state is CompatibilityState.INCOMPATIBLE
        with pytest.raises(ValueError, match="application is not supported"):
            compile_effect(item, model)
        capability = release_capability(grammar, workflow)
        assert capability is not None
        monkeypatch.setattr(
            effect_contracts,
            "RELEASE_CAPABILITY_CONTRACT",
            (*effect_contracts.RELEASE_CAPABILITY_CONTRACT, replace(capability, model=model)),
        )
        compiled = compile_effect(item, model)
        assert compiled.model == model
        assert compiled.selector_kind == "scene"
        assert compiled.activation_mode is ActivationMode.SCENE
        assert compiled.diy_code == entry.code
        assert compiled.activation_packet == expected_activation
        if workflow is not CapabilityWorkflow.ADVANCED:
            assert compiled.packets == native_packets
            with pytest.raises(ValueError, match=f"targets {model}"):
                compile_effect(item, grammar)
        profile = MODEL_PROFILES[model]
        for field in ("effect_grammar", "command_grammar"):
            for missing in (None, "unknown", "H6199" if grammar == "H617A" else "H617A"):
                monkeypatch.setitem(MODEL_PROFILES, model, replace(profile, **{field: missing}))
                assert compatibility(item, model).state is CompatibilityState.INCOMPATIBLE
                with pytest.raises(ValueError, match="activation route"):
                    compile_effect(item, model)
        monkeypatch.setitem(MODEL_PROFILES, model, profile)
        monkeypatch.setattr(
            effect_contracts,
            "RELEASE_CAPABILITY_CONTRACT",
            tuple(
                replace(
                    capability,
                    application_route=ApplicationRoute.NONE
                    if workflow is CapabilityWorkflow.NATIVE_SCENES
                    else disabled_route,
                )
                if capability.model == model and capability.workflow is workflow
                else capability
                for capability in effect_contracts.RELEASE_CAPABILITY_CONTRACT
            ),
        )
        with pytest.raises(ValueError, match="application is not supported"):
            compile_effect(item, model)


@pytest.mark.parametrize("grammar", [None, "unknown"])
def test_scene_activation_builder_has_no_fallback_grammar(monkeypatch, grammar):
    monkeypatch.setitem(MODEL_PROFILES, "H9999", ModelProfile("Synthetic", command_grammar=grammar))
    with pytest.raises(ValueError, match="scene activation grammar"):
        build_scene_activation("H9999", 401)
    with pytest.raises(ValueError, match="scene activation grammar"):
        build_native_scene_packets("H9999", SceneEntry(code=401, scene_type=0))


def test_saved_builtin_scenes_compile_to_native_scene_packets() -> None:
    for model in ("H617A", "H6199"):
        entry = next(scene for scene in SCENE_ENTRIES[model] if scene.scene_type == 0)
        item = LibraryItem.new(
            "Scene copy",
            BuiltinScene(_reference(model, entry)),
        )

        assert compatibility(item, model).state is CompatibilityState.COMPATIBLE
        compiled = compile_effect(item, model)

        assert compiled.activation_mode is ActivationMode.SCENE
        assert compiled.packets == tuple(build_native_scene_packets(model, entry))
        assert compiled.content_kind == "scene_builtin"
        assert compiled.upload_packets == ()


def test_empty_imported_layers_compile_without_reusing_source_only_bytes() -> None:
    entry = next(scene for scene in SCENE_ENTRIES["H617A"] if scene.scene_type == _LAYERED_SCENE_TYPE)
    decoded = decode_layered_scene(_reference("H617A", entry), _raw_param(entry))
    empty = replace(
        decoded,
        effect=replace(decoded.effect, layers=()),
        raw_param=b"\xaa\xbb\xcc",
        trailing_padding=0,
    )

    compiled = compile_effect(LibraryItem.new("Empty imported scene", empty), "H617A")
    encoded = encode_layered_scene(empty)

    assert encoded == b"\x00"
    assert compiled.upload_packets == tuple(fragment_a3(_LAYERED_SCENE_TYPE, encoded))


def test_edited_layered_scene_compiles_authored_layers_not_source_bytes() -> None:
    entry = next(scene for scene in SCENE_ENTRIES["H617A"] if scene.scene_type == _LAYERED_SCENE_TYPE)
    decoded = decode_layered_scene(_reference("H617A", entry), _raw_param(entry))
    first = decoded.effect.layers[0]
    edited = replace(
        decoded,
        effect=replace(
            decoded.effect,
            layers=(
                replace(first, palette=((1, 2, 3), *first.palette[1:])),
                *decoded.effect.layers[1:],
            ),
        ),
    )
    encoded = encode_layered_scene(edited)

    compiled = compile_effect(LibraryItem.new("Edited layered scene", edited), "H617A")

    assert encoded != decoded.raw_param
    assert compiled.upload_packets == tuple(
        fragment_a3(
            _LAYERED_SCENE_TYPE,
            apply_scene_speed(encoded, entry.speed, entry.speed.default_index) if entry.speed is not None else encoded,
        )
    )


def test_layered_scene_rejects_a_palette_scene_identity() -> None:
    layered_entry = next(scene for scene in SCENE_ENTRIES["H617A"] if scene.scene_type == _LAYERED_SCENE_TYPE)
    palette_entry = next(scene for scene in SCENE_ENTRIES["H617A"] if scene.scene_type == 1)
    decoded = decode_layered_scene(_reference("H617A", layered_entry), _raw_param(layered_entry))
    mismatched = replace(
        decoded,
        template=_reference("H617A", palette_entry),
        speed_index=None,
    )
    item = LibraryItem.new("Mismatched layered scene", mismatched)

    assert compatibility(item, "H617A").state is CompatibilityState.INCOMPATIBLE
    with pytest.raises(ValueError, match="uses type 1, not type 2"):
        compile_effect(item, "H617A")
