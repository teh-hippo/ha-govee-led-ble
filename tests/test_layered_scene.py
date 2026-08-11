"""Canonical layered-scene value tests."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

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
        lambda: Movement(True, False, 0, 0, 0, unknown_flags=0x10),
        lambda: Distribution(128),
        lambda: replace(_layer(), priority=256),
        lambda: replace(_layer(), unknown_flags=0x02),
        lambda: replace(_layer(), brightness_patterns=_layer().brightness_patterns * 256),
        lambda: replace(_layer(), palette=((0, 0, 0),) * 256),
        lambda: LayeredEffect((_layer(),) * 256),
    ],
)
def test_wire_model_rejects_unrepresentable_values(factory) -> None:
    with pytest.raises(LayeredSceneValidationError):
        factory()
