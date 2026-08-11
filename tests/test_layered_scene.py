"""Canonical layered-scene value tests."""

from __future__ import annotations

import base64
import json
from collections import Counter
from dataclasses import replace
from typing import Any, cast

import pytest

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


def _movement_from_parsed(movement: Any) -> Movement:
    return Movement(
        enabled=bool(movement.enabled),
        enter_exit=bool(movement.enter_exit_effect),
        direction=int(movement.direction),
        distance=int(movement.interval),
        speed=int(movement.speed),
        unknown_flags=int(movement.unknown_flags),
    )


def _layer_from_parsed(layer: Any) -> EffectLayer:
    return EffectLayer(
        area=AppliedArea(
            start_tenths=int(layer.applied_area_start_tenths),
            width_tenths=int(layer.applied_area_width_tenths),
        ),
        selection=Selection(
            type=int(layer.select_type),
            param_1=int(layer.select_param_1),
            param_2=int(layer.select_param_2),
        ),
        brightness_gradient=bool(layer.brightness_is_gradient),
        brightness_patterns=tuple(
            BrightnessPattern(
                scope_high=int(block.scope_high),
                scope_low=int(block.scope_low),
                order=int(block.order),
                change_speed=int(block.change_speed),
                brightest_retention=int(block.retention_brightest),
                darkest_retention=int(block.retention_darkest),
            )
            for block in layer.brightness_blocks
        ),
        distribution=Distribution(
            method=int(layer.distribution_method),
            backwards=bool(layer.direction_is_backward),
        ),
        colour_speed=int(layer.colour_speed),
        colour_retention=int(layer.colour_retention),
        palette=tuple((int(colour.r), int(colour.g), int(colour.b)) for colour in layer.palette),
        selected_movement=_movement_from_parsed(layer.selected_area_movement),
        overall_movement=_movement_from_parsed(layer.overall_movement),
        priority=int(layer.priority),
        unknown_flags=int(layer.unknown_flags),
        excess=bytes(layer.excess),
    )


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


def test_generated_unknown_flag_properties_feed_the_canonical_split() -> None:
    entry = next(entry for entry in SCENE_ENTRIES["H617A"] if entry.scene_type == int(SceneBody.SceneType.scene_v2))
    parsed = parse_scene_body_param(base64.b64decode(entry.param, validate=True))
    layer = parsed.records[0].body
    layer.layer_flags |= 0x80
    layer.selected_area_movement.packed |= 0x20

    canonical = _layer_from_parsed(layer)

    assert canonical.unknown_flags == 0x80
    assert canonical.selected_movement.unknown_flags == 0x20


def test_all_committed_layered_scenes_round_trip_canonical_values() -> None:
    scene_counts: Counter[str] = Counter()
    record_count = 0

    for sku, entries in SCENE_ENTRIES.items():
        for entry in entries:
            if entry.scene_type != int(SceneBody.SceneType.scene_v2):
                continue
            raw_param = base64.b64decode(entry.param, validate=True)
            parsed = parse_scene_body_param(raw_param)
            envelope = cast(bytes, parsed._io.to_byte_array())
            canonical = LayeredScene(
                template=CatalogueRef(sku, entry.scene_id, entry.effect_id),
                effect=LayeredEffect(tuple(_layer_from_parsed(record.body) for record in parsed.records)),
                speed_index=entry.speed.default_index if entry.speed is not None else None,
                raw_param=raw_param,
            )
            value = layered_scene_to_value(canonical)
            restored = layered_scene_from_value(json.loads(json.dumps(value)))

            assert restored == canonical
            assert layered_scene_to_value(restored) == value
            assert restored.raw_param == raw_param
            assert len(restored.effect.layers) == int(parsed.num_records)
            _check_tree(parsed)
            assert _write(parsed, len(envelope)) == envelope

            scene_counts[sku] += 1
            record_count += len(restored.effect.layers)

    assert scene_counts == {"H617A": 72, "H6199": 226}
    assert record_count == 863


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
