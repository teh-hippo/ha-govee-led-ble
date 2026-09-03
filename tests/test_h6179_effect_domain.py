"""H6179 persistent custom-effect content."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from custom_components.ha_govee_led_ble.effect_compiler import CompatibilityState, compatibility, compile_effect
from custom_components.ha_govee_led_ble.effect_domain import (
    EFFECT_SCHEMA_VERSION,
    EffectPair,
    EffectValidationError,
    H6179MixedDiyEffect,
    H6179SingleDiyEffect,
    LibraryItem,
    MultiEffect,
    OpaqueContent,
    PaletteDiyEffect,
    SingleEffect,
    effect_content_from_dict,
    effect_content_to_dict,
)

RED = (255, 0, 0)
BLUE = (0, 0, 255)
type RGB = tuple[int, int, int]
type DiyFactory = Callable[[int, tuple[RGB, ...]], object]


def _single_diy(speed: int, palette: tuple[RGB, ...]) -> H6179SingleDiyEffect:
    return H6179SingleDiyEffect("H6179", 0, 0, speed, palette)


def _mixed_diy(speed: int, palette: tuple[RGB, ...]) -> H6179MixedDiyEffect:
    return H6179MixedDiyEffect("H6179", (EffectPair(0, 0),), speed, palette)


def test_h6179_single_diy_round_trips_with_model_identity() -> None:
    content = H6179SingleDiyEffect("H6179", 1, 0, 0, (RED,))
    document = {
        "kind": "h6179_single_diy",
        "model": "H6179",
        "family": 1,
        "variant": 0,
        "speed": 0,
        "palette": [[255, 0, 0]],
    }

    assert effect_content_to_dict(content) == document
    assert effect_content_from_dict(document) == content
    item = LibraryItem.new("Single", content)
    assert LibraryItem.from_dict(item.to_dict()).content == content


def test_h6179_mixed_diy_round_trips_with_component_pairs() -> None:
    content = H6179MixedDiyEffect(
        "H6179",
        (EffectPair(0, 0), EffectPair(1, 0), EffectPair(2, 0), EffectPair(0, 0)),
        100,
        (RED, BLUE),
    )
    document = {
        "kind": "h6179_mixed_diy",
        "model": "H6179",
        "components": [
            {"family": 0, "variant": 0},
            {"family": 1, "variant": 0},
            {"family": 2, "variant": 0},
            {"family": 0, "variant": 0},
        ],
        "speed": 100,
        "palette": [[255, 0, 0], [0, 0, 255]],
    }

    assert effect_content_to_dict(content) == document
    assert effect_content_from_dict(document) == content
    item = LibraryItem.new("Mixed", content)
    assert LibraryItem.from_dict(item.to_dict()).content == content


@pytest.mark.parametrize("content", [_single_diy(50, (RED,)), _mixed_diy(50, (RED,))])
def test_h6179_diy_compiles_only_for_exact_model_and_with_approved_code(
    content: H6179SingleDiyEffect | H6179MixedDiyEffect,
) -> None:
    item = LibraryItem.new("DIY", content)

    wrong_model = compatibility(item, "H617A")
    h6179 = compatibility(item, "H6179")

    assert wrong_model.state is CompatibilityState.INCOMPATIBLE
    assert wrong_model.reasons == ("H6179 DIY content targets H6179, not H617A",)
    assert h6179.state is CompatibilityState.COMPATIBLE
    assert h6179.reasons == ()
    with pytest.raises(ValueError, match="observed and explicitly approved disposable DIY code"):
        compile_effect(item, "H6179")
    assert compile_effect(item, "H6179", diy_code=0x1234).model == "H6179"


@pytest.mark.parametrize("factory", [_single_diy, _mixed_diy])
def test_h6179_diy_accepts_eight_palette_colours(factory: DiyFactory) -> None:
    assert len(factory(50, (RED,) * 8).palette) == 8


@pytest.mark.parametrize(
    "factory",
    [
        lambda: H6179SingleDiyEffect("H617A", 0, 0, 50, (RED,)),
        lambda: H6179SingleDiyEffect("H6199", 0, 0, 50, (RED,)),
        lambda: H6179MixedDiyEffect("H617A", (EffectPair(0, 0),), 50, (RED,)),
        lambda: H6179MixedDiyEffect("H6199", (EffectPair(0, 0),), 50, (RED,)),
    ],
)
def test_h6179_diy_rejects_cross_sku_content(factory: Callable[[], object]) -> None:
    with pytest.raises(EffectValidationError, match="must target model 'H6179'"):
        factory()


@pytest.mark.parametrize("speed", [-1, 101])
@pytest.mark.parametrize("factory", [_single_diy, _mixed_diy])
def test_h6179_diy_rejects_speed_outside_zero_to_one_hundred(factory: DiyFactory, speed: int) -> None:
    with pytest.raises(EffectValidationError, match="speed must be an integer from 0 to 100"):
        factory(speed, (RED,))


@pytest.mark.parametrize("palette", [(), (RED,) * 9])
@pytest.mark.parametrize("factory", [_single_diy, _mixed_diy])
def test_h6179_diy_requires_one_to_eight_palette_colours(
    factory: DiyFactory,
    palette: tuple[RGB, ...],
) -> None:
    with pytest.raises(EffectValidationError, match="palette must contain 1 to 8 colours"):
        factory(50, palette)


@pytest.mark.parametrize("components", [(), (EffectPair(0, 0),) * 5])
def test_h6179_mixed_diy_requires_one_to_four_components(components: tuple[EffectPair, ...]) -> None:
    with pytest.raises(EffectValidationError, match="mixed DIY must contain 1 to 4 components"):
        H6179MixedDiyEffect("H6179", components, 50, (RED,))


@pytest.mark.parametrize(
    "factory",
    [
        lambda: H6179SingleDiyEffect("H6179", 3, 0, 50, (RED,)),
        lambda: H6179SingleDiyEffect("H6179", 0, 1, 50, (RED,)),
        lambda: H6179SingleDiyEffect("H6179", 254, 255, 50, (RED,)),
        lambda: H6179SingleDiyEffect("H6179", 255, 0, 50, (RED,)),
        lambda: H6179MixedDiyEffect("H6179", (EffectPair(3, 0),), 50, (RED,)),
        lambda: H6179MixedDiyEffect("H6179", (EffectPair(0, 1),), 50, (RED,)),
        lambda: H6179MixedDiyEffect("H6179", (EffectPair(254, 255),), 50, (RED,)),
    ],
)
def test_h6179_diy_rejects_unsupported_family_variant_pairs(factory: Callable[[], object]) -> None:
    with pytest.raises(EffectValidationError, match="unsupported H6179 DIY family/variant pair"):
        factory()


def test_h6179_kinds_are_additive_without_reshaping_existing_content() -> None:
    assert EFFECT_SCHEMA_VERSION == 2
    assert effect_content_to_dict(SingleEffect(1, 2, 3, (RED,)))["kind"] == "h617a_single"
    assert effect_content_to_dict(MultiEffect((EffectPair(1, 2),), 3, (RED,)))["kind"] == "h617a_multi"
    assert effect_content_to_dict(PaletteDiyEffect("H6199", 1, 2, 3, (RED,)))["kind"] == "palette_diy"

    future = {"kind": "h6179_future_diy", "model": "H6179", "payload": {"value": 1}}
    assert effect_content_from_dict(future) == OpaqueContent(
        "h6179_future_diy",
        {"model": "H6179", "payload": {"value": 1}},
    )


@pytest.mark.parametrize(
    "document",
    [
        {
            "kind": "h6179_single_diy",
            "model": "H6199",
            "family": 1,
            "variant": 2,
            "speed": 50,
            "palette": [[255, 0, 0]],
        },
        {
            "kind": "h6179_mixed_diy",
            "model": "H617A",
            "components": [{"family": 1, "variant": 2}],
            "speed": 50,
            "palette": [[255, 0, 0]],
        },
    ],
)
def test_h6179_deserialization_rejects_cross_sku_documents(document: dict[str, Any]) -> None:
    with pytest.raises(EffectValidationError, match="must target model 'H6179'"):
        effect_content_from_dict(document)
