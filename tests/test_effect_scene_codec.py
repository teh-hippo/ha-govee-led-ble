"""Lossless decoding for committed layered scene templates."""

from __future__ import annotations

import base64
import io
from collections import Counter
from dataclasses import replace
from typing import Any, cast

import pytest
from kaitaistruct import KaitaiStream

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
    NativeEffect,
    effect_content_from_dict,
    effect_content_to_dict,
)
from custom_components.ha_govee_led_ble.effect_protocol_decoder import decode_a3_effect, decode_effect_frames
from custom_components.ha_govee_led_ble.generated_protocol.scene_body import SceneBody
from custom_components.ha_govee_led_ble.generated_protocol_adapter import build_scene_activation, parse_scene_body_param
from custom_components.ha_govee_led_ble.h60a6_effects import decode_native_scene, encode_native_body, native_diy_preset
from custom_components.ha_govee_led_ble.layered_scene_decoder import decode_layered_scene, encode_layered_scene
from custom_components.ha_govee_led_ble.native_effect import NativeDiyLayer, NativePaintLayer
from custom_components.ha_govee_led_ble.native_scenes import apply_scene_speed, build_native_scene_packets
from custom_components.ha_govee_led_ble.palette_scene_decoder import decode_catalogue_palette_scene
from custom_components.ha_govee_led_ble.protocol_core import H60a6DiyBody, _check_tree, _write
from custom_components.ha_govee_led_ble.scenes import MODEL_SCENES, SCENE_ENTRIES, SceneEntry
from custom_components.ha_govee_led_ble.transport import fragment_a3, xor_checksum

_LAYERED_SCENE_TYPE = int(SceneBody.SceneType.scene_v2)


def test_all_h60a6_native_catalogue_bodies_round_trip_through_saved_semantics() -> None:
    counts: Counter[int] = Counter()
    for entry in SCENE_ENTRIES["H60A6"]:
        if entry.diy_effect_codes not in ((797,), (798,)):
            continue
        raw = _raw_param(entry)
        content = decode_native_scene(_reference("H60A6", entry), raw, family=entry.diy_effect_codes[0])
        restored = effect_content_from_dict(effect_content_to_dict(content))
        assert restored == content
        item = LibraryItem.new("Native saved scene", content)
        assert LibraryItem.from_dict(item.to_dict()).content == content
        assert encode_native_body(restored) == raw
        counts[content.family] += 1
        for index, layer in enumerate(content.layers):
            if isinstance(layer, NativeDiyLayer | NativePaintLayer):
                layers = list(content.layers)
                layers[index] = replace(layer, speed=(layer.speed + 1) % 101)
                edited = replace(content, layers=tuple(layers))
                reparsed = decode_native_scene(content.template, encode_native_body(edited), family=content.family)
                assert reparsed == edited
    assert counts == {797: 15, 798: 60}


@pytest.mark.parametrize("preset", range(1, 16))
def test_native_presets_are_structured_and_round_trip(preset: int) -> None:
    content = native_diy_preset(preset, ((255, 0, 0), (0, 0, 255)))
    raw = encode_native_body(content)
    decoded = decode_native_scene(CatalogueRef("H60A6", 1, 1), raw, family=content.family)
    assert decoded.layers == content.layers
    assert decoded.backgrounds == content.backgrounds
    if content.family == 797:
        root = H60a6DiyBody(KaitaiStream(io.BytesIO(raw + bytes(16))))
        root._read()
        direct = decode_a3_effect(root, "H60A6")
        assert isinstance(direct, NativeEffect)
        assert direct.layers == content.layers
    compiled = compile_effect(LibraryItem.new("Native preset", content), "H60A6")
    assert compiled.diy_code == 254
    assert compiled.upload_transport == ("a4" if preset == 15 else "a3")
    assert compiled.upload_subtype == 0x58
    assert "native_diy_positive_ack_required" in compiled.evidence_codes
    uploaded = decode_effect_frames(compiled.upload_packets, "H60A6", compiled.upload_transport)
    assert isinstance(uploaded, NativeEffect)
    assert uploaded.layers == content.layers
    assert uploaded.backgrounds == content.backgrounds


@pytest.mark.parametrize("family", [797, 798])
def test_native_scene_compilation_preserves_its_catalogue_selector_and_route(family: int) -> None:
    entry = next(scene for scene in SCENE_ENTRIES["H60A6"] if scene.diy_effect_codes == (family,))
    raw = _raw_param(entry)
    if entry.speed is not None:
        raw = apply_scene_speed(raw, entry.speed, entry.speed.default_index)
    content = decode_native_scene(_reference("H60A6", entry), raw, family=family)
    compiled = compile_effect(LibraryItem.new("Edited native scene", content), "H60A6")
    builtin = compile_effect(LibraryItem.new("Native scene", BuiltinScene(content.template)), "H60A6")
    assert compiled.upload_packets == builtin.upload_packets
    assert compiled.activation_packet == builtin.activation_packet
    assert compiled.upload_transport == builtin.upload_transport == ("a3" if family == 797 else "a4")
    assert compiled.upload_subtype == builtin.upload_subtype == 0x58


def test_native_scene_metadata_speed_applies_only_when_explicitly_selected() -> None:
    entry = next(scene for scene in SCENE_ENTRIES["H60A6"] if scene.speed is not None and scene.speed.layer_speeds)
    assert entry.speed is not None
    raw = _raw_param(entry)
    content = decode_native_scene(_reference("H60A6", entry), raw, family=797)
    selected = replace(content, speed_index=0)
    compiled = compile_effect(LibraryItem.new("Native speed choice", selected), "H60A6")
    assert compiled.upload_packets == tuple(fragment_a3(0x58, apply_scene_speed(raw, entry.speed, 0)))
    manual = compile_effect(LibraryItem.new("Preserved native layer speeds", content), "H60A6")
    assert manual.upload_packets == tuple(fragment_a3(0x58, raw))


def test_native_paint_edit_preserves_groups_order_and_unknown_fields() -> None:
    raw = bytes.fromhex("50201020304002011700030a0001000300aabbcc000c84013264013412deadbeef")
    content = decode_native_scene(CatalogueRef("H60A6", 1, 1), raw, family=798)
    layer = content.layers[0]
    assert isinstance(layer, NativePaintLayer)
    assert layer.groups[0].indices == (0, 12, 132)
    for action in range(1, 8):
        edited = replace(content, layers=(replace(layer, action=action, priority=9),))
        decoded = decode_native_scene(content.template, encode_native_body(edited), family=798)
        assert decoded == edited
        decoded_layer = decoded.layers[0]
        assert isinstance(decoded_layer, NativePaintLayer)
        assert decoded_layer.opaque == bytes.fromhex("deadbeef")


def _reference(sku: str, entry: SceneEntry) -> CatalogueRef:
    return CatalogueRef(sku, entry.scene_id, entry.effect_id)


def _raw_param(entry: SceneEntry) -> bytes:
    return base64.b64decode(entry.param, validate=True)


def test_inert_catalogue_metadata_does_not_enable_scene_compilation(monkeypatch) -> None:
    monkeypatch.setitem(
        MODEL_PROFILES,
        "H6076",
        replace(MODEL_PROFILES["H6076"], supports_scenes=False),
    )
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


def _assert_movement(decoded: Any, parsed: Any) -> None:
    assert decoded.enabled is bool(parsed.enabled)
    assert decoded.enter_exit is bool(parsed.enter_exit_effect)
    assert decoded.direction == int(parsed.direction)
    assert decoded.distance == int(parsed.interval)
    assert decoded.speed == int(parsed.speed)
    assert decoded.unknown_flags == int(parsed.unknown_flags)


def _assert_layer(decoded: Any, parsed: Any) -> None:
    assert (decoded.area.start_tenths, decoded.area.width_tenths) == (
        int(parsed.applied_area_start_tenths),
        int(parsed.applied_area_width_tenths),
    )
    assert (int(decoded.selection.type), decoded.selection.param_1, decoded.selection.param_2) == (
        int(parsed.select_type),
        int(parsed.select_param_1),
        int(parsed.select_param_2),
    )
    assert decoded.brightness_gradient is bool(parsed.brightness_is_gradient)
    assert [
        (
            block.scope_high,
            block.scope_low,
            int(block.order),
            block.change_speed,
            block.brightest_retention,
            block.darkest_retention,
        )
        for block in decoded.brightness_patterns
    ] == [
        (
            int(block.scope_high),
            int(block.scope_low),
            int(block.order),
            int(block.change_speed),
            int(block.retention_brightest),
            int(block.retention_darkest),
        )
        for block in parsed.brightness_blocks
    ]
    assert (decoded.distribution.method, decoded.distribution.backwards) == (
        int(parsed.distribution_method),
        bool(parsed.direction_is_backward),
    )
    assert (decoded.colour_speed, decoded.colour_retention) == (
        int(parsed.colour_speed),
        int(parsed.colour_retention),
    )
    assert decoded.palette == tuple((int(colour.r), int(colour.g), int(colour.b)) for colour in parsed.palette)
    _assert_movement(decoded.selected_movement, parsed.selected_area_movement)
    _assert_movement(decoded.overall_movement, parsed.overall_movement)
    assert decoded.priority == int(parsed.priority)
    assert decoded.unknown_flags == int(parsed.unknown_flags)
    assert decoded.excess == bytes(parsed.excess)


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
                _assert_layer(layer, record.body)
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
            supports_advanced_effects=True,
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
            for missing in (None, "unknown"):
                monkeypatch.setitem(MODEL_PROFILES, model, replace(profile, **{field: missing}))
                assert compatibility(item, model).state is CompatibilityState.INCOMPATIBLE
                with pytest.raises(ValueError, match="activation"):
                    compile_effect(item, model)
            alternate = "H6199" if grammar == "H617A" else "H617A"
            monkeypatch.setitem(MODEL_PROFILES, model, replace(profile, **{field: alternate}))
            assert compatibility(item, model).state is CompatibilityState.COMPATIBLE
            assert compile_effect(item, model).activation_packet == build_scene_activation(
                model, entry.code, entry.music_code
            )
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
