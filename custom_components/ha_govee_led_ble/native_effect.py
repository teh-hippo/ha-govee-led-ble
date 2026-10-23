"""Lossless semantic content for native layered effects."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .layered_scene import (
    CatalogueRef,
    LayeredSceneValidationError,
    _as_mapping,
    _catalogue_ref_from_value,
    _catalogue_ref_to_value,
    _hex_bytes,
    _optional_int,
    _required_int,
    _required_sequence,
    _required_str,
)

type RGB = tuple[int, int, int]


def _number(value: int, maximum: int, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= maximum:
        raise LayeredSceneValidationError(f"{name} must be an integer from 0 to {maximum}")


def _rgb(value: RGB) -> None:
    if not isinstance(value, tuple) or len(value) != 3:
        raise LayeredSceneValidationError("native colour must contain three channels")
    for channel in value:
        _number(channel, 255, "colour channel")


@dataclass(frozen=True, slots=True)
class NativeDiyLayer:
    kind: int
    speed: int
    palette: tuple[RGB, ...]
    parameters: bytes = b""
    parameter: int = 0
    flag: int = 0
    points: tuple[int, ...] = ()
    direction: int = 0
    angle: int = 0
    opaque: bytes = b""

    def __post_init__(self) -> None:
        _number(self.kind, 255, "layer kind")
        _number(self.speed, 100, "layer speed")
        for name in ("parameter", "flag", "direction"):
            _number(getattr(self, name), 255, name)
        _number(self.angle, 65535, "angle")
        if len(self.palette) > 255 or len(self.points) > 255:
            raise LayeredSceneValidationError("native palette or point list exceeds its count field")
        for colour in self.palette:
            _rgb(colour)
        for point in self.points:
            _number(point, 255, "point")
        if not isinstance(self.parameters, bytes) or not isinstance(self.opaque, bytes):
            raise LayeredSceneValidationError("native unknown fields must be bytes")


@dataclass(frozen=True, slots=True)
class NativePaintGroup:
    colour: RGB
    indices: tuple[int, ...]

    def __post_init__(self) -> None:
        _rgb(self.colour)
        if len(self.indices) > 65535:
            raise LayeredSceneValidationError("native point group exceeds its count field")
        for point in self.indices:
            _number(point, 132, "physical point")


@dataclass(frozen=True, slots=True)
class NativePaintLayer:
    groups: tuple[NativePaintGroup, ...]
    action: int = 1
    speed: int = 50
    brightness: int = 100
    priority: int = 1
    duration: int = 0
    opaque: bytes = bytes(4)
    data_opaque: bytes = b""
    trailing: bytes = b""

    def __post_init__(self) -> None:
        for name in ("action", "speed", "brightness", "priority"):
            _number(getattr(self, name), 255, name)
        _number(self.duration, 65535, "duration")
        if len(self.groups) > 65535 or any(not isinstance(group, NativePaintGroup) for group in self.groups):
            raise LayeredSceneValidationError("invalid native paint groups")
        if not isinstance(self.opaque, bytes) or len(self.opaque) != 4:
            raise LayeredSceneValidationError("native paint opaque field must contain four bytes")
        if not isinstance(self.data_opaque, bytes) or not isinstance(self.trailing, bytes):
            raise LayeredSceneValidationError("native paint extension fields must be bytes")


@dataclass(frozen=True, slots=True)
class NativeOpaqueLayer:
    kind: int
    data: bytes

    def __post_init__(self) -> None:
        _number(self.kind, 255, "layer kind")
        if not isinstance(self.data, bytes):
            raise LayeredSceneValidationError("unknown native layer must contain bytes")


type NativeLayer = NativeDiyLayer | NativePaintLayer | NativeOpaqueLayer


@dataclass(frozen=True, slots=True)
class NativeEffect:
    family: int
    layers: tuple[NativeLayer, ...]
    backgrounds: tuple[RGB, ...] = ()
    background_flag: int = 0
    background: RGB = (0, 0, 0)
    background_brightness: int = 100
    show_type: int = 1
    opaque: bytes = b""
    preset_id: int | None = None
    template: CatalogueRef | None = None
    speed_index: int | None = None
    model: str = "H60A6"

    def __post_init__(self) -> None:
        if self.model != "H60A6" or self.family not in (797, 798):
            raise LayeredSceneValidationError("unsupported native effect model or family")
        if not 1 <= len(self.layers) <= 255 or len(self.backgrounds) > 255:
            raise LayeredSceneValidationError("native effect exceeds its layer or background count field")
        expected = NativeDiyLayer if self.family == 797 else NativePaintLayer
        if any(not isinstance(layer, expected | NativeOpaqueLayer) for layer in self.layers):
            raise LayeredSceneValidationError("native layer does not match its effect family")
        for name in ("background_flag", "background_brightness", "show_type"):
            _number(getattr(self, name), 255, name)
        for colour in (*self.backgrounds, self.background):
            _rgb(colour)
        if not isinstance(self.opaque, bytes):
            raise LayeredSceneValidationError("native extension field must be bytes")
        if self.preset_id is not None:
            _number(self.preset_id, 255, "native preset")
        if self.template is not None and self.template.sku != self.model:
            raise LayeredSceneValidationError("native scene identity does not match its model")
        if self.speed_index is not None:
            _number(self.speed_index, 255, "scene speed index")


def native_effect_to_value(content: NativeEffect) -> dict[str, Any]:
    layers: list[dict[str, Any]] = []
    for layer in content.layers:
        if isinstance(layer, NativeDiyLayer):
            layers.append(
                {
                    "type": "diy",
                    "kind": layer.kind,
                    "speed": layer.speed,
                    "palette": [list(colour) for colour in layer.palette],
                    "parameters": layer.parameters.hex(),
                    "parameter": layer.parameter,
                    "flag": layer.flag,
                    "points": list(layer.points),
                    "direction": layer.direction,
                    "angle": layer.angle,
                    "opaque": layer.opaque.hex(),
                }
            )
        elif isinstance(layer, NativePaintLayer):
            layers.append(
                {
                    "type": "paint",
                    "groups": [
                        {"colour": list(group.colour), "indices": list(group.indices)} for group in layer.groups
                    ],
                    "action": layer.action,
                    "speed": layer.speed,
                    "brightness": layer.brightness,
                    "priority": layer.priority,
                    "duration": layer.duration,
                    "opaque": layer.opaque.hex(),
                    "data_opaque": layer.data_opaque.hex(),
                    "trailing": layer.trailing.hex(),
                }
            )
        else:
            layers.append({"type": "opaque", "kind": layer.kind, "data": layer.data.hex()})
    return {
        "kind": "native_effect",
        "model": content.model,
        "family": content.family,
        "layers": layers,
        "backgrounds": [list(colour) for colour in content.backgrounds],
        "background_flag": content.background_flag,
        "background": list(content.background),
        "background_brightness": content.background_brightness,
        "show_type": content.show_type,
        "opaque": content.opaque.hex(),
        "preset_id": content.preset_id,
        "template": None if content.template is None else _catalogue_ref_to_value(content.template),
        "speed_index": content.speed_index,
    }


def native_effect_from_value(raw: Mapping[str, Any]) -> NativeEffect:
    layers: list[NativeLayer] = []
    for value in _required_sequence(raw, "layers"):
        layer = _as_mapping(value, "native layer")
        layer_type = _required_str(layer, "type")
        if layer_type == "diy":
            layers.append(
                NativeDiyLayer(
                    kind=_required_int(layer, "kind"),
                    speed=_required_int(layer, "speed"),
                    palette=tuple(_colour(value) for value in _required_sequence(layer, "palette")),
                    parameters=_hex_bytes(layer.get("parameters", ""), "native parameters"),
                    parameter=_optional_int(layer, "parameter") or 0,
                    flag=_optional_int(layer, "flag") or 0,
                    points=tuple(_required_sequence(layer, "points")),
                    direction=_optional_int(layer, "direction") or 0,
                    angle=_optional_int(layer, "angle") or 0,
                    opaque=_hex_bytes(layer.get("opaque", ""), "native layer opaque"),
                )
            )
        elif layer_type == "paint":
            groups = tuple(
                NativePaintGroup(
                    colour=_colour(_as_mapping(group, "paint group").get("colour")),
                    indices=tuple(_required_sequence(_as_mapping(group, "paint group"), "indices")),
                )
                for group in _required_sequence(layer, "groups")
            )
            layers.append(
                NativePaintLayer(
                    groups=groups,
                    action=_required_int(layer, "action"),
                    speed=_required_int(layer, "speed"),
                    brightness=_required_int(layer, "brightness"),
                    priority=_required_int(layer, "priority"),
                    duration=_required_int(layer, "duration"),
                    opaque=_hex_bytes(layer.get("opaque", ""), "native paint opaque"),
                    data_opaque=_hex_bytes(layer.get("data_opaque", ""), "native paint data opaque"),
                    trailing=_hex_bytes(layer.get("trailing", ""), "native paint trailing"),
                )
            )
        elif layer_type == "opaque":
            layers.append(
                NativeOpaqueLayer(
                    kind=_required_int(layer, "kind"),
                    data=_hex_bytes(layer.get("data"), "native layer data"),
                )
            )
        else:
            raise LayeredSceneValidationError("unsupported native layer type")
    return NativeEffect(
        model=_required_str(raw, "model"),
        family=_required_int(raw, "family"),
        layers=tuple(layers),
        backgrounds=tuple(_colour(value) for value in _required_sequence(raw, "backgrounds")),
        background_flag=_required_int(raw, "background_flag"),
        background=_colour(raw.get("background")),
        background_brightness=_required_int(raw, "background_brightness"),
        show_type=_required_int(raw, "show_type"),
        opaque=_hex_bytes(raw.get("opaque", ""), "native opaque"),
        preset_id=_optional_int(raw, "preset_id"),
        template=None
        if raw.get("template") is None
        else _catalogue_ref_from_value(_as_mapping(raw["template"], "native template")),
        speed_index=_optional_int(raw, "speed_index"),
    )


def _colour(value: object) -> RGB:
    if not isinstance(value, list | tuple) or len(value) != 3:
        raise LayeredSceneValidationError("native colour must contain three channels")
    colour = tuple(value)
    _rgb(colour)
    return colour
