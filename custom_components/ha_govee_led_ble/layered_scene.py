"""Canonical, editor-neutral layered scene values."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import IntEnum
from importlib import import_module
from typing import Any, cast

type RGB = tuple[int, int, int]
type JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]

GoveeShared = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.govee_shared").GoveeShared,
)

__all__ = [
    "AppliedArea",
    "BrightnessOrder",
    "BrightnessPattern",
    "CatalogueRef",
    "Distribution",
    "EffectLayer",
    "LayeredEffect",
    "LayeredScene",
    "LayeredSceneValidationError",
    "Movement",
    "RGB",
    "Selection",
    "SelectionType",
    "layered_effect_from_value",
    "layered_effect_to_value",
    "layered_scene_from_value",
    "layered_scene_to_value",
]

_BYTE_COUNT = 0xFF
_LAYER_GRADIENT_FLAG = 0x02
_MOVEMENT_KNOWN_FLAGS = 0x17


class LayeredSceneValidationError(ValueError):
    """A layered scene value does not satisfy the canonical contract."""


class BrightnessOrder(IntEnum):
    """Known brightness-order values from the shared Kaitai schema."""

    BRIGHTEST_DARKEST = int(GoveeShared.BrightnessOrder.brightest_darkest)
    BRIGHTEST_DARKEST_BRIGHTEST = int(GoveeShared.BrightnessOrder.brightest_darkest_brightest)
    DARKEST_BRIGHTEST = int(GoveeShared.BrightnessOrder.darkest_brightest)
    DARKEST_BRIGHTEST_DARKEST = int(GoveeShared.BrightnessOrder.darkest_brightest_darkest)


class SelectionType(IntEnum):
    """Known layer-selection values from the shared Kaitai schema."""

    SEGMENT = int(GoveeShared.SelectType.segment)
    CONTINUOUS = int(GoveeShared.SelectType.select_ic_continuously)
    RANDOM = int(GoveeShared.SelectType.select_ic_randomly)
    CUSTOM = int(GoveeShared.SelectType.customize_segment)


@dataclass(frozen=True, slots=True)
class AppliedArea:
    """The two raw nibbles in a layer's applied-area byte.

    The field names follow the catalogue schema and do not infer physical coverage.
    """

    start_tenths: int
    width_tenths: int

    def __post_init__(self) -> None:
        _validate_nibble(self.start_tenths, "applied-area low nibble")
        _validate_nibble(self.width_tenths, "applied-area high nibble")


@dataclass(frozen=True, slots=True)
class Selection:
    type: int
    param_1: int
    param_2: int

    def __post_init__(self) -> None:
        _validate_byte(self.type, "selection type")
        _validate_byte(self.param_1, "selection parameter 1")
        _validate_byte(self.param_2, "selection parameter 2")


@dataclass(frozen=True, slots=True)
class BrightnessPattern:
    scope_high: int
    scope_low: int
    order: int
    change_speed: int
    brightest_retention: int
    darkest_retention: int

    def __post_init__(self) -> None:
        _validate_byte(self.scope_high, "brightness scope high")
        _validate_byte(self.scope_low, "brightness scope low")
        _validate_byte(self.order, "brightness order")
        _validate_byte(self.change_speed, "brightness change speed")
        _validate_byte(self.brightest_retention, "brightest retention")
        _validate_byte(self.darkest_retention, "darkest retention")


@dataclass(frozen=True, slots=True)
class Movement:
    enabled: bool
    enter_exit: bool
    direction: int
    distance: int
    speed: int
    unknown_flags: int = 0

    def __post_init__(self) -> None:
        _validate_bool(self.enabled, "movement enabled")
        _validate_bool(self.enter_exit, "movement enter-exit")
        if not _is_int(self.direction) or not 0 <= self.direction <= 3:
            raise LayeredSceneValidationError("movement direction must be an integer from 0 to 3")
        _validate_byte(self.distance, "movement distance")
        _validate_byte(self.speed, "movement speed")
        _validate_byte(self.unknown_flags, "movement unknown flags")
        if self.unknown_flags & _MOVEMENT_KNOWN_FLAGS:
            raise LayeredSceneValidationError("movement unknown flags overlap known flags")


@dataclass(frozen=True, slots=True)
class Distribution:
    method: int
    backwards: bool = False

    def __post_init__(self) -> None:
        if not _is_int(self.method) or not 0 <= self.method <= 0x7F:
            raise LayeredSceneValidationError("distribution method must be an integer from 0 to 127")
        _validate_bool(self.backwards, "distribution backwards")


@dataclass(frozen=True, slots=True)
class EffectLayer:
    area: AppliedArea
    selection: Selection
    brightness_gradient: bool
    brightness_patterns: tuple[BrightnessPattern, ...]
    distribution: Distribution
    colour_speed: int
    colour_retention: int
    palette: tuple[RGB, ...]
    selected_movement: Movement
    overall_movement: Movement
    priority: int
    unknown_flags: int = 0
    excess: bytes = b""

    def __post_init__(self) -> None:
        _validate_instance(self.area, AppliedArea, "layer area")
        _validate_instance(self.selection, Selection, "layer selection")
        _validate_bool(self.brightness_gradient, "layer brightness gradient")
        _validate_items(self.brightness_patterns, BrightnessPattern, "layer brightness patterns")
        _validate_instance(self.distribution, Distribution, "layer distribution")
        _validate_byte(self.colour_speed, "colour speed")
        _validate_byte(self.colour_retention, "colour retention")
        _validate_palette(self.palette)
        _validate_instance(self.selected_movement, Movement, "selected-area movement")
        _validate_instance(self.overall_movement, Movement, "overall movement")
        _validate_byte(self.priority, "layer priority")
        _validate_byte(self.unknown_flags, "layer unknown flags")
        if self.unknown_flags & _LAYER_GRADIENT_FLAG:
            raise LayeredSceneValidationError("layer unknown flags overlap the gradient flag")
        if not isinstance(self.excess, bytes):
            raise LayeredSceneValidationError("layer excess must be bytes")


@dataclass(frozen=True, slots=True)
class LayeredEffect:
    layers: tuple[EffectLayer, ...]

    def __post_init__(self) -> None:
        _validate_items(self.layers, EffectLayer, "effect layers")


@dataclass(frozen=True, slots=True)
class CatalogueRef:
    sku: str
    scene_id: int
    effect_id: int
    catalogue_schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.sku, str) or not self.sku:
            raise LayeredSceneValidationError("catalogue SKU must not be empty")
        _validate_non_negative(self.scene_id, "catalogue scene ID")
        _validate_non_negative(self.effect_id, "catalogue effect ID")
        if not _is_int(self.catalogue_schema_version) or self.catalogue_schema_version < 1:
            raise LayeredSceneValidationError("catalogue schema version must be a positive integer")


@dataclass(frozen=True, slots=True)
class LayeredScene:
    template: CatalogueRef
    effect: LayeredEffect
    speed_index: int | None = None
    raw_param: bytes = b""

    def __post_init__(self) -> None:
        _validate_instance(self.template, CatalogueRef, "scene template")
        _validate_instance(self.effect, LayeredEffect, "scene effect")
        if self.speed_index is not None:
            _validate_non_negative(self.speed_index, "scene speed index")
        if not isinstance(self.raw_param, bytes):
            raise LayeredSceneValidationError("scene raw parameter must be bytes")


def layered_effect_to_value(effect: LayeredEffect) -> dict[str, JsonValue]:
    """Return an effect as JSON-compatible values."""
    _validate_instance(effect, LayeredEffect, "layered effect")
    return {"layers": [_layer_to_value(layer) for layer in effect.layers]}


def layered_effect_from_value(raw: Mapping[str, Any]) -> LayeredEffect:
    """Restore an effect from JSON-compatible values."""
    return LayeredEffect(
        tuple(
            _layer_from_value(_as_mapping(layer, "effect layer"))
            for layer in _required_sequence(_as_mapping(raw, "layered effect"), "layers")
        )
    )


def layered_scene_to_value(scene: LayeredScene) -> dict[str, JsonValue]:
    """Return a layered scene as JSON-compatible values."""
    _validate_instance(scene, LayeredScene, "layered scene")
    return {
        "template": _catalogue_ref_to_value(scene.template),
        "effect": layered_effect_to_value(scene.effect),
        "speed_index": scene.speed_index,
        "raw_param": scene.raw_param.hex(),
    }


def layered_scene_from_value(raw: Mapping[str, Any]) -> LayeredScene:
    """Restore a layered scene from JSON-compatible values."""
    value = _as_mapping(raw, "layered scene")
    return LayeredScene(
        template=_catalogue_ref_from_value(_required_mapping(value, "template")),
        effect=layered_effect_from_value(_required_mapping(value, "effect")),
        speed_index=_optional_int(value, "speed_index"),
        raw_param=_hex_bytes(value.get("raw_param"), "scene raw parameter"),
    )


def _layer_to_value(layer: EffectLayer) -> dict[str, JsonValue]:
    return {
        "area": {
            "start_tenths": layer.area.start_tenths,
            "width_tenths": layer.area.width_tenths,
        },
        "selection": {
            "type": layer.selection.type,
            "param_1": layer.selection.param_1,
            "param_2": layer.selection.param_2,
        },
        "brightness_gradient": layer.brightness_gradient,
        "brightness_patterns": [
            {
                "scope_high": pattern.scope_high,
                "scope_low": pattern.scope_low,
                "order": pattern.order,
                "change_speed": pattern.change_speed,
                "brightest_retention": pattern.brightest_retention,
                "darkest_retention": pattern.darkest_retention,
            }
            for pattern in layer.brightness_patterns
        ],
        "distribution": {
            "method": layer.distribution.method,
            "backwards": layer.distribution.backwards,
        },
        "colour_speed": layer.colour_speed,
        "colour_retention": layer.colour_retention,
        "palette": [list(colour) for colour in layer.palette],
        "selected_movement": _movement_to_value(layer.selected_movement),
        "overall_movement": _movement_to_value(layer.overall_movement),
        "priority": layer.priority,
        "unknown_flags": layer.unknown_flags,
        "excess": layer.excess.hex(),
    }


def _layer_from_value(raw: Mapping[str, Any]) -> EffectLayer:
    area = _required_mapping(raw, "area")
    selection = _required_mapping(raw, "selection")
    distribution = _required_mapping(raw, "distribution")
    return EffectLayer(
        area=AppliedArea(
            start_tenths=_required_int(area, "start_tenths"),
            width_tenths=_required_int(area, "width_tenths"),
        ),
        selection=Selection(
            type=_required_int(selection, "type"),
            param_1=_required_int(selection, "param_1"),
            param_2=_required_int(selection, "param_2"),
        ),
        brightness_gradient=_required_bool(raw, "brightness_gradient"),
        brightness_patterns=tuple(
            _brightness_pattern_from_value(_as_mapping(pattern, "brightness pattern"))
            for pattern in _required_sequence(raw, "brightness_patterns")
        ),
        distribution=Distribution(
            method=_required_int(distribution, "method"),
            backwards=_required_bool(distribution, "backwards"),
        ),
        colour_speed=_required_int(raw, "colour_speed"),
        colour_retention=_required_int(raw, "colour_retention"),
        palette=_palette_from_value(raw.get("palette")),
        selected_movement=_movement_from_value(_required_mapping(raw, "selected_movement")),
        overall_movement=_movement_from_value(_required_mapping(raw, "overall_movement")),
        priority=_required_int(raw, "priority"),
        unknown_flags=_required_int(raw, "unknown_flags"),
        excess=_hex_bytes(raw.get("excess"), "layer excess"),
    )


def _brightness_pattern_from_value(raw: Mapping[str, Any]) -> BrightnessPattern:
    return BrightnessPattern(
        scope_high=_required_int(raw, "scope_high"),
        scope_low=_required_int(raw, "scope_low"),
        order=_required_int(raw, "order"),
        change_speed=_required_int(raw, "change_speed"),
        brightest_retention=_required_int(raw, "brightest_retention"),
        darkest_retention=_required_int(raw, "darkest_retention"),
    )


def _movement_to_value(movement: Movement) -> dict[str, JsonValue]:
    return {
        "enabled": movement.enabled,
        "enter_exit": movement.enter_exit,
        "direction": movement.direction,
        "distance": movement.distance,
        "speed": movement.speed,
        "unknown_flags": movement.unknown_flags,
    }


def _movement_from_value(raw: Mapping[str, Any]) -> Movement:
    return Movement(
        enabled=_required_bool(raw, "enabled"),
        enter_exit=_required_bool(raw, "enter_exit"),
        direction=_required_int(raw, "direction"),
        distance=_required_int(raw, "distance"),
        speed=_required_int(raw, "speed"),
        unknown_flags=_required_int(raw, "unknown_flags"),
    )


def _catalogue_ref_to_value(reference: CatalogueRef) -> dict[str, JsonValue]:
    return {
        "sku": reference.sku,
        "scene_id": reference.scene_id,
        "effect_id": reference.effect_id,
        "catalogue_schema_version": reference.catalogue_schema_version,
    }


def _catalogue_ref_from_value(raw: Mapping[str, Any]) -> CatalogueRef:
    return CatalogueRef(
        sku=_required_str(raw, "sku"),
        scene_id=_required_int(raw, "scene_id"),
        effect_id=_required_int(raw, "effect_id"),
        catalogue_schema_version=_required_int(raw, "catalogue_schema_version"),
    )


def _validate_items[ItemT](value: tuple[ItemT, ...], item_type: type[ItemT], name: str) -> None:
    if not isinstance(value, tuple):
        raise LayeredSceneValidationError(f"{name} must be a tuple")
    if len(value) > _BYTE_COUNT:
        raise LayeredSceneValidationError(f"{name} must contain at most {_BYTE_COUNT} items")
    for item in value:
        _validate_instance(item, item_type, name)


def _validate_palette(palette: tuple[RGB, ...]) -> None:
    if not isinstance(palette, tuple):
        raise LayeredSceneValidationError("layer palette must be a tuple")
    if len(palette) > _BYTE_COUNT:
        raise LayeredSceneValidationError(f"layer palette must contain at most {_BYTE_COUNT} colours")
    for colour in palette:
        _validate_rgb(colour, "layer palette colour")


def _validate_rgb(value: RGB, name: str) -> None:
    if not isinstance(value, tuple) or len(value) != 3:
        raise LayeredSceneValidationError(f"{name} must be an RGB tuple")
    for channel in value:
        _validate_byte(channel, f"{name} channel")


def _validate_instance[ItemT](value: object, item_type: type[ItemT], name: str) -> None:
    if not isinstance(value, item_type):
        raise LayeredSceneValidationError(f"{name} must be {item_type.__name__}")


def _validate_non_negative(value: int, name: str) -> None:
    if not _is_int(value) or value < 0:
        raise LayeredSceneValidationError(f"{name} must be a non-negative integer")


def _validate_nibble(value: int, name: str) -> None:
    if not _is_int(value) or not 0 <= value <= 0x0F:
        raise LayeredSceneValidationError(f"{name} must be an integer from 0 to 15")


def _validate_byte(value: int, name: str) -> None:
    if not _is_int(value) or not 0 <= value <= 0xFF:
        raise LayeredSceneValidationError(f"{name} must be an integer from 0 to 255")


def _validate_bool(value: bool, name: str) -> None:
    if not isinstance(value, bool):
        raise LayeredSceneValidationError(f"{name} must be a boolean")


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _as_mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise LayeredSceneValidationError(f"{name} must be a mapping")
    return cast(Mapping[str, Any], value)


def _required_mapping(raw: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    if key not in raw:
        raise LayeredSceneValidationError(f"missing required field {key!r}")
    return _as_mapping(raw[key], key)


def _required_sequence(raw: Mapping[str, Any], key: str) -> Sequence[Any]:
    value = raw.get(key)
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise LayeredSceneValidationError(f"{key} must be a list")
    return value


def _required_int(raw: Mapping[str, Any], key: str) -> int:
    value = raw.get(key)
    if not _is_int(value):
        raise LayeredSceneValidationError(f"{key} must be an integer")
    return cast(int, value)


def _optional_int(raw: Mapping[str, Any], key: str) -> int | None:
    value = raw.get(key)
    if value is None:
        return None
    if not _is_int(value):
        raise LayeredSceneValidationError(f"{key} must be an integer or null")
    return cast(int, value)


def _required_bool(raw: Mapping[str, Any], key: str) -> bool:
    value = raw.get(key)
    if not isinstance(value, bool):
        raise LayeredSceneValidationError(f"{key} must be a boolean")
    return value


def _required_str(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str):
        raise LayeredSceneValidationError(f"{key} must be a string")
    return value


def _palette_from_value(value: object) -> tuple[RGB, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise LayeredSceneValidationError("palette must be a list")
    return tuple(_rgb_from_value(colour, "palette colour") for colour in value)


def _rgb_from_value(value: object, name: str) -> RGB:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes) or len(value) != 3:
        raise LayeredSceneValidationError(f"{name} must contain three integer channels")
    if any(not _is_int(channel) for channel in value):
        raise LayeredSceneValidationError(f"{name} must contain three integer channels")
    rgb = cast(RGB, tuple(value))
    _validate_rgb(rgb, name)
    return rgb


def _hex_bytes(value: object, name: str) -> bytes:
    if not isinstance(value, str):
        raise LayeredSceneValidationError(f"{name} must be a hexadecimal string")
    try:
        return bytes.fromhex(value)
    except ValueError as exc:
        raise LayeredSceneValidationError(f"{name} must be a hexadecimal string") from exc
