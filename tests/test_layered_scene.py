"""Canonical layered-scene value tests."""

from __future__ import annotations

import base64
import binascii
import json
from collections import Counter
from dataclasses import replace
from typing import Any, cast

import pytest
from kaitaistruct import KaitaiStructError

from custom_components.ha_govee_led_ble.generated_protocol.scene_body import SceneBody
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    _check_tree,
    _write,
    parse_scene_body_param,
)
from custom_components.ha_govee_led_ble.layered_scene import (
    AppliedArea,
    BrightnessOrder,
    BrightnessPattern,
    CatalogueRef,
    Distribution,
    EffectLayer,
    LayeredEffect,
    LayeredScene,
    LayeredSceneValidationError,
    Movement,
    Selection,
    SelectionType,
    layered_effect_from_value,
    layered_effect_to_value,
    layered_scene_from_value,
    layered_scene_to_value,
)
from custom_components.ha_govee_led_ble.layered_scene_decoder import (
    decode_catalogue_layered_scene,
    decode_layered_scene,
)
from custom_components.ha_govee_led_ble.scenes import SCENE_ENTRIES


def _layer() -> EffectLayer:
    return EffectLayer(
        area=AppliedArea(0, 0),
        selection=Selection(SelectionType.CUSTOM, 0, 255),
        brightness_gradient=True,
        brightness_patterns=(
            BrightnessPattern(
                scope_high=0,
                scope_low=255,
                order=BrightnessOrder.BRIGHTEST_DARKEST,
                change_speed=255,
                brightest_retention=0,
                darkest_retention=255,
            ),
        ),
        distribution=Distribution(127, backwards=True),
        colour_speed=255,
        colour_retention=0,
        palette=tuple((value, value + 1, value + 2) for value in range(11)),
        selected_movement=Movement(True, False, 3, 0, 255, unknown_flags=0xA8),
        overall_movement=Movement(False, True, 0, 255, 0),
        priority=255,
        unknown_flags=0xFD,
        excess=b"\xaa\xbb",
    )


def _assert_movement_matches(decoded: Movement, parsed: Any) -> None:
    assert decoded.enabled is bool(parsed.enabled)
    assert decoded.enter_exit is bool(parsed.enter_exit_effect)
    assert decoded.direction == int(parsed.direction)
    assert decoded.distance == int(parsed.interval)
    assert decoded.speed == int(parsed.speed)
    assert decoded.unknown_flags == int(parsed.unknown_flags)


def _assert_layer_matches(decoded: EffectLayer, parsed: Any) -> None:
    assert (decoded.area.start_tenths, decoded.area.width_tenths) == (
        int(parsed.applied_area_start_tenths),
        int(parsed.applied_area_width_tenths),
    )
    assert (decoded.selection.type, decoded.selection.param_1, decoded.selection.param_2) == (
        int(parsed.select_type),
        int(parsed.select_param_1),
        int(parsed.select_param_2),
    )
    assert decoded.brightness_gradient is bool(parsed.brightness_is_gradient)
    assert [
        (
            block.scope_high,
            block.scope_low,
            block.order,
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
    _assert_movement_matches(decoded.selected_movement, parsed.selected_area_movement)
    _assert_movement_matches(decoded.overall_movement, parsed.overall_movement)
    assert decoded.priority == int(parsed.priority)
    assert decoded.unknown_flags == int(parsed.unknown_flags)
    assert decoded.excess == bytes(parsed.excess)


def test_effect_domain_compatibility_shape_uses_raw_integer_values() -> None:
    pattern = replace(_layer().brightness_patterns[0], order=0xFD)
    layer = replace(
        _layer(),
        selection=Selection(0xFE, 1, 2),
        brightness_patterns=(pattern,),
        palette=((1, 2, 3),),
    )
    effect = LayeredEffect((layer,))
    expected_effect = {
        "layers": [
            {
                "area": {"start_tenths": 0, "width_tenths": 0},
                "selection": {"type": 0xFE, "param_1": 1, "param_2": 2},
                "brightness_gradient": True,
                "brightness_patterns": [
                    {
                        "scope_high": 0,
                        "scope_low": 255,
                        "order": 0xFD,
                        "change_speed": 255,
                        "brightest_retention": 0,
                        "darkest_retention": 255,
                    }
                ],
                "distribution": {"method": 127, "backwards": True},
                "colour_speed": 255,
                "colour_retention": 0,
                "palette": [[1, 2, 3]],
                "selected_movement": {
                    "enabled": True,
                    "enter_exit": False,
                    "direction": 3,
                    "distance": 0,
                    "speed": 255,
                    "unknown_flags": 0xA8,
                },
                "overall_movement": {
                    "enabled": False,
                    "enter_exit": True,
                    "direction": 0,
                    "distance": 255,
                    "speed": 0,
                    "unknown_flags": 0,
                },
                "priority": 255,
                "unknown_flags": 0xFD,
                "excess": "aabb",
            }
        ]
    }
    effect_value = layered_effect_to_value(effect)
    scene_value = layered_scene_to_value(
        LayeredScene(
            template=CatalogueRef("H617A", 1033, 1095),
            effect=effect,
            speed_index=2,
            raw_param=b"\x00\xff",
        )
    )

    assert effect_value == expected_effect
    layer_value = cast(dict[str, Any], cast(list[Any], effect_value["layers"])[0])
    selection_value = cast(dict[str, Any], layer_value["selection"])
    pattern_value = cast(dict[str, Any], cast(list[Any], layer_value["brightness_patterns"])[0])
    assert type(selection_value["type"]) is int
    assert type(pattern_value["order"]) is int
    assert scene_value == {
        "template": {
            "sku": "H617A",
            "scene_id": 1033,
            "effect_id": 1095,
            "catalogue_schema_version": 1,
        },
        "effect": expected_effect,
        "speed_index": 2,
        "raw_param": "00ff",
    }


def test_committed_catalogue_extremes_round_trip_through_json() -> None:
    layer = _layer()
    effect = LayeredEffect(
        tuple(
            replace(
                layer,
                area=AppliedArea(9, 10) if index == 1 else layer.area,
                priority=priority,
            )
            for index, priority in enumerate((255, 5, 4, 3, 2, 0))
        )
    )

    document = json.loads(json.dumps(layered_effect_to_value(effect)))
    restored = layered_effect_from_value(document)

    assert restored == effect
    assert restored.layers[0].area == AppliedArea(0, 0)
    assert restored.layers[1].area == AppliedArea(9, 10)
    assert len(restored.layers[0].palette) == 11
    assert tuple(layer.priority for layer in restored.layers) == (255, 5, 4, 3, 2, 0)
    assert restored.layers[0].brightness_patterns[0].scope_low == 255


def test_applied_area_preserves_the_full_raw_nibble_range() -> None:
    effect = LayeredEffect((replace(_layer(), area=AppliedArea(15, 15)),))

    assert layered_effect_from_value(layered_effect_to_value(effect)) == effect


def test_scene_round_trip_preserves_raw_parameter_provenance() -> None:
    scene = LayeredScene(
        template=CatalogueRef("H617A", scene_id=1033, effect_id=1095),
        effect=LayeredEffect((_layer(),)),
        speed_index=2,
        raw_param=b"\x00\xff\x10\x80",
    )

    document = json.loads(json.dumps(layered_scene_to_value(scene)))

    assert document["raw_param"] == "00ff1080"
    assert layered_scene_from_value(document) == scene


def test_unknown_enums_flags_and_excess_round_trip_without_normalisation() -> None:
    layer = replace(
        _layer(),
        selection=Selection(0xFE, 1, 2),
        brightness_patterns=(
            replace(
                _layer().brightness_patterns[0],
                order=0xFD,
            ),
        ),
    )
    restored = layered_effect_from_value(layered_effect_to_value(LayeredEffect((layer,))))
    restored_layer = restored.layers[0]

    assert restored_layer.selection.type == 0xFE
    assert restored_layer.brightness_patterns[0].order == 0xFD
    assert restored_layer.unknown_flags == 0xFD
    assert restored_layer.selected_movement.unknown_flags == 0xA8
    assert restored_layer.excess == b"\xaa\xbb"


def test_decoder_preserves_unknown_generated_values_and_record_excess() -> None:
    entry = next(entry for entry in SCENE_ENTRIES["H617A"] if entry.scene_type == int(SceneBody.SceneType.scene_v2))
    raw_param = base64.b64decode(entry.param, validate=True)
    parsed = parse_scene_body_param(raw_param)
    original_envelope = cast(bytes, parsed._io.to_byte_array())
    prefix_length = len(original_envelope) - len(raw_param) - len(parsed.padding)
    record = parsed.records[0]
    layer = record.body
    layer.applied_area = 0
    layer.select_type = 0xFE
    layer.brightness_blocks[0].brightness_order = 0xFD
    layer.layer_flags |= 0x80
    layer.selected_area_movement.packed |= 0x20
    layer.overall_movement.packed |= 0x40
    layer.priority = 0xFF
    layer.excess = b"\xaa\xbb"
    record.len_body += len(layer.excess)
    parsed.padding = []
    _check_tree(parsed)
    synthetic_envelope = _write(parsed, prefix_length + len(raw_param) + len(layer.excess))
    synthetic_param = synthetic_envelope[prefix_length:]

    decoded = decode_layered_scene(
        CatalogueRef("H617A", entry.scene_id, entry.effect_id),
        synthetic_param,
    )
    canonical = decoded.effect.layers[0]

    assert decoded.raw_param == synthetic_param
    assert canonical.area == AppliedArea(0, 0)
    assert canonical.selection.type == 0xFE
    assert canonical.brightness_patterns[0].order == 0xFD
    assert canonical.unknown_flags & 0x80
    assert canonical.selected_movement.unknown_flags & 0x20
    assert canonical.overall_movement.unknown_flags & 0x40
    assert canonical.priority == 0xFF
    assert canonical.excess == b"\xaa\xbb"


def test_all_committed_layered_scenes_round_trip_canonical_values() -> None:
    scene_counts: Counter[str] = Counter()
    record_count = 0

    for sku, entries in SCENE_ENTRIES.items():
        for entry in entries:
            if entry.scene_type != int(SceneBody.SceneType.scene_v2):
                continue
            raw_param = base64.b64decode(entry.param, validate=True)
            parsed = parse_scene_body_param(raw_param)
            canonical = decode_catalogue_layered_scene(sku, entry)
            assert canonical is not None
            value = layered_scene_to_value(canonical)
            restored = layered_scene_from_value(json.loads(json.dumps(value)))

            assert restored == canonical
            assert layered_scene_to_value(restored) == value
            assert restored.raw_param == raw_param
            assert restored.template == CatalogueRef(sku, entry.scene_id, entry.effect_id)
            assert restored.speed_index == (entry.speed.default_index if entry.speed is not None else None)
            assert len(restored.effect.layers) == int(parsed.num_records)
            for decoded_layer, record in zip(restored.effect.layers, parsed.records, strict=True):
                _assert_layer_matches(decoded_layer, record.body)

            scene_counts[sku] += 1
            record_count += len(restored.effect.layers)

    assert scene_counts == {"H617A": 72, "H6199": 226}
    assert record_count == 863


def test_catalogue_decoder_rejects_malformed_type_2_input() -> None:
    entry = next(entry for entry in SCENE_ENTRIES["H617A"] if entry.scene_type == int(SceneBody.SceneType.scene_v2))

    with pytest.raises(binascii.Error):
        decode_catalogue_layered_scene("H617A", replace(entry, param="not base64!"))
    with pytest.raises(ValueError, match="has no parameter"):
        decode_catalogue_layered_scene("H617A", replace(entry, param=""))
    decoded = decode_catalogue_layered_scene("H617A", entry)
    assert decoded is not None
    with pytest.raises(TypeError, match="must be bytes"):
        decode_layered_scene(decoded.template, bytearray(base64.b64decode(entry.param, validate=True)))
    with pytest.raises(KaitaiStructError):
        decode_layered_scene(decoded.template, b"\x01")


def test_catalogue_decoder_leaves_non_type_2_entries_opaque() -> None:
    entry = next(entry for entry in SCENE_ENTRIES["H617A"] if entry.scene_type != int(SceneBody.SceneType.scene_v2))

    assert decode_catalogue_layered_scene("H617A", replace(entry, param="not base64!")) is None


def test_wire_sized_collections_do_not_apply_authoring_minimums() -> None:
    empty_layer = replace(_layer(), brightness_patterns=(), palette=())

    assert LayeredEffect(()) == layered_effect_from_value({"layers": []})
    assert layered_effect_from_value(layered_effect_to_value(LayeredEffect((empty_layer,)))) == LayeredEffect(
        (empty_layer,)
    )


def test_wire_sized_collections_accept_byte_count_maximums() -> None:
    layer = _layer()
    maximal_layer = replace(
        layer,
        brightness_patterns=(layer.brightness_patterns[0],) * 255,
        palette=((0, 0, 0),) * 255,
    )
    effect = LayeredEffect((maximal_layer,) * 255)

    assert len(effect.layers) == 255
    assert len(effect.layers[0].brightness_patterns) == 255
    assert len(effect.layers[0].palette) == 255


@pytest.mark.parametrize(
    "factory",
    [
        lambda: AppliedArea(16, 0),
        lambda: AppliedArea(0, -1),
        lambda: Selection(True, 0, 0),
        lambda: BrightnessPattern(0, 0, 256, 0, 0, 0),
        lambda: Distribution(128),
        lambda: replace(_layer(), priority=256),
        lambda: replace(_layer(), brightness_patterns=_layer().brightness_patterns * 256),
        lambda: replace(_layer(), palette=((0, 0, 0),) * 256),
        lambda: LayeredEffect((_layer(),) * 256),
    ],
)
def test_wire_model_rejects_unrepresentable_values(factory) -> None:
    with pytest.raises(LayeredSceneValidationError):
        factory()
