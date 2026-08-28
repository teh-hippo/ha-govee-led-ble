"""Versioned, wire-independent custom-effect definitions."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any, cast
from uuid import UUID, uuid4

from .const import MODEL_PROFILES
from .effect_limits import (
    MAX_EFFECT_DOCUMENT_BYTES,
    MAX_EFFECT_KIND_LENGTH,
    MAX_EFFECT_NAME_LENGTH,
    MAX_IDENTIFIER_LENGTH,
    validate_bounded_string,
    validate_json_document,
    validate_revision,
    validate_timestamp,
)
from .generated_protocol_adapter import MAX_SCENE_PARAM_BYTES
from .layered_scene import AppliedArea as AppliedArea
from .layered_scene import BrightnessOrder as BrightnessOrder
from .layered_scene import BrightnessPattern as BrightnessPattern
from .layered_scene import CatalogueRef as CatalogueRef
from .layered_scene import Distribution as Distribution
from .layered_scene import EffectLayer as EffectLayer
from .layered_scene import LayeredEffect as LayeredEffect
from .layered_scene import LayeredScene as LayeredScene
from .layered_scene import LayeredSceneValidationError as LayeredSceneValidationError
from .layered_scene import Movement as Movement
from .layered_scene import Selection as Selection
from .layered_scene import SelectionType as SelectionType
from .layered_scene import (
    _as_mapping,
    _hex_bytes,
    _optional_int,
    _required_bool,
    _required_int,
    _required_mapping,
    _required_sequence,
    _required_str,
    _validate_bool,
    layered_effect_from_value,
    layered_effect_to_value,
    layered_scene_from_value,
    layered_scene_to_value,
)
from .layered_scene import (
    _catalogue_ref_from_value as _catalogue_ref_from_dict,
)
from .layered_scene import (
    _catalogue_ref_to_value as _catalogue_ref_to_dict,
)

EFFECT_SCHEMA_VERSION = 2
MAX_PALETTE_COLOURS = 8
MAX_MULTI_EFFECTS = 4
H617A_SEGMENT_COUNT = 15

PALETTE_CONFIG_RESERVED_MASK = 0x08
VIDEO_PROFILE_MODES = frozenset({"movie", "game"})

type RGB = tuple[int, int, int]
type JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


EffectValidationError = LayeredSceneValidationError


class UnsupportedEffectSchemaError(EffectValidationError):
    """The document uses a schema version this integration cannot read."""


class SourceKind(StrEnum):
    AUTHORED = "authored"
    IMPORTED = "imported"
    CATALOGUE_TEMPLATE = "catalogue_template"
    CAPTURED_FIXTURE = "captured_fixture"
    MIGRATED = "migrated"


@dataclass(frozen=True, slots=True)
class Origin:
    kind: SourceKind = SourceKind.AUTHORED
    source_id: str | None = None

    def __post_init__(self) -> None:
        validate_bounded_string(
            self.source_id or "",
            "source ID",
            maximum=MAX_IDENTIFIER_LENGTH,
            error_type=EffectValidationError,
            allow_empty=True,
        )


@dataclass(frozen=True, slots=True)
class TargetHint:
    model: str
    segment_count: int | None = None

    def __post_init__(self) -> None:
        validate_bounded_string(
            self.model,
            "target model",
            maximum=MAX_IDENTIFIER_LENGTH,
            error_type=EffectValidationError,
        )
        if self.segment_count is not None and self.segment_count < 1:
            raise EffectValidationError("target segment count must be positive")


@dataclass(frozen=True, slots=True)
class PaintedEffect:
    effect: str
    speed: int
    brightness: int
    segments: tuple[RGB | None, ...]

    def __post_init__(self) -> None:
        validate_bounded_string(
            self.effect,
            "painted effect name",
            maximum=MAX_EFFECT_KIND_LENGTH,
            error_type=EffectValidationError,
        )
        _validate_percent(self.speed, "speed")
        _validate_percent(self.brightness, "brightness")
        if len(self.segments) != H617A_SEGMENT_COUNT:
            raise EffectValidationError(f"painted effect must contain exactly {H617A_SEGMENT_COUNT} segments")
        for segment in self.segments:
            if segment is not None:
                _validate_rgb(segment, "painted segment")


@dataclass(frozen=True, slots=True)
class SingleEffect:
    family: int
    variant: int
    speed: int
    palette: tuple[RGB, ...]

    def __post_init__(self) -> None:
        _validate_byte(self.family, "family")
        if self.family == 0xFF:
            raise EffectValidationError("family 255 is reserved for Multi")
        _validate_byte(self.variant, "variant")
        _validate_percent(self.speed, "speed")
        _validate_palette(self.palette)


@dataclass(frozen=True, slots=True)
class PaletteDiyEffect:
    model: str
    family: int
    variant: int
    speed: int
    palette: tuple[RGB, ...]

    def __post_init__(self) -> None:
        _validate_identifier(self.model, "model")
        _validate_byte(self.family, "family")
        _validate_byte(self.variant, "variant")
        _validate_percent(self.speed, "speed")
        _validate_palette(self.palette)


@dataclass(frozen=True, slots=True)
class MusicProfile:
    model: str
    mode: str
    sensitivity: int
    colour: RGB | None = None
    calm: bool | None = None
    parameters: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_identifier(self.model, "model")
        _validate_identifier(self.mode, "mode")
        profile = MODEL_PROFILES.get(self.model)
        if profile is None:
            raise EffectValidationError(f"unsupported music-profile model {self.model!r}")
        _validate_range(
            self.sensitivity,
            "sensitivity",
            minimum=profile.music_sensitivity_min,
            maximum=profile.music_sensitivity_max,
        )
        if self.colour is not None:
            _validate_rgb(self.colour, "colour")
        if self.calm is not None and not isinstance(self.calm, bool):
            raise EffectValidationError("calm must be a boolean or null")
        if not isinstance(self.parameters, Mapping):
            raise EffectValidationError("parameters must be a mapping")
        validate_json_document(
            dict(self.parameters),
            "parameters",
            maximum_bytes=MAX_EFFECT_DOCUMENT_BYTES,
            error_type=EffectValidationError,
        )


def _validate_supported_model(value: str, feature: str) -> None:
    _validate_identifier(value, f"{feature} model")
    if value not in MODEL_PROFILES:
        raise EffectValidationError(f"unsupported {feature} model {value!r}")


@dataclass(frozen=True, slots=True)
class RelativeBrightness:
    left: int
    top: int
    right: int
    bottom: int

    def __post_init__(self) -> None:
        _validate_range(self.left, "left", minimum=1, maximum=100)
        _validate_range(self.top, "top", minimum=1, maximum=100)
        _validate_range(self.right, "right", minimum=1, maximum=100)
        _validate_range(self.bottom, "bottom", minimum=1, maximum=100)


@dataclass(frozen=True, slots=True)
class VideoProfile:
    model: str
    mode: str
    full_screen: bool
    saturation: int
    sound_effects: bool
    sound_effects_softness: int
    white_balance_position: int
    relative_brightness: RelativeBrightness
    blank_screen: bool

    def __post_init__(self) -> None:
        _validate_identifier(self.model, "model")
        _validate_identifier(self.mode, "mode")
        if self.mode not in VIDEO_PROFILE_MODES:
            raise EffectValidationError("mode must be 'movie' or 'game'")
        _validate_bool(self.full_screen, "full_screen")
        _validate_percent(self.saturation, "saturation")
        _validate_bool(self.sound_effects, "sound_effects")
        _validate_range(self.sound_effects_softness, "sound_effects_softness", minimum=1, maximum=100)
        _validate_range(self.white_balance_position, "white_balance_position", minimum=1, maximum=20)
        if not isinstance(self.relative_brightness, RelativeBrightness):
            raise EffectValidationError("relative_brightness must be a relative-brightness mapping")
        _validate_bool(self.blank_screen, "blank_screen")


@dataclass(frozen=True, slots=True)
class EffectPair:
    family: int
    variant: int

    def __post_init__(self) -> None:
        _validate_byte(self.family, "effect family")
        if self.family == 0xFF:
            raise EffectValidationError("effect family 255 is reserved for Multi")
        _validate_byte(self.variant, "effect variant")


@dataclass(frozen=True, slots=True)
class MultiEffect:
    effects: tuple[EffectPair, ...]
    speed: int
    palette: tuple[RGB, ...]

    def __post_init__(self) -> None:
        if not 1 <= len(self.effects) <= MAX_MULTI_EFFECTS:
            raise EffectValidationError(f"Multi must contain 1 to {MAX_MULTI_EFFECTS} effects")
        _validate_percent(self.speed, "speed")
        _validate_palette(self.palette)


@dataclass(frozen=True, slots=True)
class WorkshopEffect:
    model: str
    template: str
    effect: LayeredEffect
    raw_param: bytes = b""
    trailing_padding: int = 0

    def __post_init__(self) -> None:
        _validate_supported_model(self.model, "Workshop")
        _validate_identifier(self.template, "Workshop template")
        if not isinstance(self.effect, LayeredEffect):
            raise EffectValidationError("Workshop effect must be layered content")
        if not isinstance(self.raw_param, bytes):
            raise EffectValidationError("Workshop source parameter must be bytes")
        if (
            not isinstance(self.trailing_padding, int)
            or isinstance(self.trailing_padding, bool)
            or not 0 <= self.trailing_padding <= MAX_SCENE_PARAM_BYTES
        ):
            raise EffectValidationError(
                f"Workshop trailing padding must be an integer from 0 to {MAX_SCENE_PARAM_BYTES}"
            )


@dataclass(frozen=True, slots=True)
class BuiltinScene:
    template: CatalogueRef
    speed_index: int | None = None

    def __post_init__(self) -> None:
        if self.speed_index is not None:
            _validate_byte(self.speed_index, "scene speed index")


@dataclass(frozen=True, slots=True)
class SceneStep:
    value: int
    colour: RGB
    inline_colour: RGB | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.value, int) or not 0 <= self.value <= 0xFFFF:
            raise EffectValidationError("scene step value must be from 0 to 65535")
        _validate_rgb(self.colour, "scene step colour")
        if self.inline_colour is not None:
            _validate_rgb(self.inline_colour, "scene inline colour")


@dataclass(frozen=True, slots=True)
class PaletteScene:
    template: CatalogueRef
    layout: int
    brightness_flag: bool
    steps: tuple[SceneStep, ...]
    palette: tuple[RGB, ...] = ()
    speed_index: int | None = None
    config_flags: int = 0
    trailing_padding: int = 0

    def __post_init__(self) -> None:
        if self.layout not in (0, 1):
            raise EffectValidationError("type-1 scene layout must be 0 or 1")
        _validate_palette_scene_count(self.steps, "steps")
        if self.layout == 0:
            _validate_palette_scene_palette(self.palette)
            if any(step.inline_colour is not None for step in self.steps):
                raise EffectValidationError("layout 0 steps must not have inline colours")
        elif self.palette:
            raise EffectValidationError("layout 1 scenes must not have a shared palette")
        elif any(step.inline_colour is None for step in self.steps):
            raise EffectValidationError("layout 1 steps require inline colours")
        if self.speed_index is not None:
            _validate_byte(self.speed_index, "scene speed index")
        if self.config_flags & ~PALETTE_CONFIG_RESERVED_MASK:
            raise EffectValidationError("type-1 scene config flags must only set reserved config bits")
        if (
            not isinstance(self.trailing_padding, int)
            or isinstance(self.trailing_padding, bool)
            or not 0 <= self.trailing_padding <= MAX_SCENE_PARAM_BYTES
        ):
            raise EffectValidationError(
                f"type-1 scene trailing padding must be an integer from 0 to {MAX_SCENE_PARAM_BYTES}"
            )


@dataclass(frozen=True, slots=True)
class OpaqueContent:
    kind: str
    body: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        validate_bounded_string(
            self.kind,
            "opaque content kind",
            maximum=MAX_EFFECT_KIND_LENGTH,
            error_type=EffectValidationError,
        )
        validate_json_document(
            dict(self.body),
            "opaque content",
            maximum_bytes=MAX_EFFECT_DOCUMENT_BYTES,
            error_type=EffectValidationError,
        )


type EffectContent = (
    PaintedEffect
    | SingleEffect
    | PaletteDiyEffect
    | MusicProfile
    | VideoProfile
    | MultiEffect
    | LayeredEffect
    | WorkshopEffect
    | BuiltinScene
    | PaletteScene
    | LayeredScene
    | OpaqueContent
)


def effect_content_to_dict(content: EffectContent) -> dict[str, JsonValue]:
    return _content_to_dict(content)


def effect_content_from_dict(raw: Mapping[str, Any]) -> EffectContent:
    return _content_from_dict(raw)


@dataclass(frozen=True, slots=True)
class LibraryItem:
    id: UUID
    version: int
    updated_at: str
    name: str
    content: EffectContent
    content_hash: str = ""
    origin: Origin = field(default_factory=Origin)
    target_hint: TargetHint | None = None
    extensions: Mapping[str, JsonValue] = field(default_factory=dict)
    schema_version: int = EFFECT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != EFFECT_SCHEMA_VERSION:
            raise UnsupportedEffectSchemaError(f"unsupported effect schema version {self.schema_version}")
        validate_revision(
            self.version,
            "version",
            minimum=1,
            error_type=EffectValidationError,
        )
        validate_timestamp(
            self.updated_at,
            "effect updated timestamp",
            error_type=EffectValidationError,
        )
        if not self.name.strip():
            raise EffectValidationError("effect name must not be empty")
        if len(self.name) > MAX_EFFECT_NAME_LENGTH:
            raise EffectValidationError(f"effect name must not exceed {MAX_EFFECT_NAME_LENGTH} characters")
        resolved_hash = effect_content_hash(self.content)
        if self.content_hash and self.content_hash != resolved_hash:
            raise EffectValidationError("effect content hash does not match content")
        object.__setattr__(self, "content_hash", resolved_hash)
        validate_json_document(
            self.to_dict(),
            "effect document",
            maximum_bytes=MAX_EFFECT_DOCUMENT_BYTES,
            error_type=EffectValidationError,
        )

    @classmethod
    def new(
        cls,
        name: str,
        content: EffectContent,
        *,
        origin: Origin | None = None,
        target_hint: TargetHint | None = None,
        updated_at: str | None = None,
        extensions: Mapping[str, JsonValue] | None = None,
    ) -> LibraryItem:
        return cls(
            id=uuid4(),
            version=1,
            updated_at=updated_at or datetime.now(UTC).isoformat(),
            name=name,
            content=content,
            origin=origin or Origin(),
            target_hint=target_hint,
            extensions={} if extensions is None else extensions,
        )

    def to_dict(self) -> dict[str, JsonValue]:
        document: dict[str, JsonValue] = {
            "schema_version": self.schema_version,
            "id": str(self.id),
            "version": self.version,
            "updated_at": self.updated_at,
            "name": self.name,
            "content": _content_to_dict(self.content),
            "content_hash": self.content_hash,
            "origin": _origin_to_dict(self.origin),
            "extensions": dict(self.extensions),
        }
        if self.target_hint is not None:
            document["target_hint"] = {
                "model": self.target_hint.model,
                "segment_count": self.target_hint.segment_count,
            }
        return document

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> LibraryItem:
        validate_json_document(
            raw,
            "effect document",
            maximum_bytes=MAX_EFFECT_DOCUMENT_BYTES,
            error_type=EffectValidationError,
        )
        schema_version = _required_int(raw, "schema_version")
        if schema_version != EFFECT_SCHEMA_VERSION:
            raise UnsupportedEffectSchemaError(f"unsupported effect schema version {schema_version}")
        try:
            item_id = UUID(_required_str(raw, "id"))
        except ValueError as exc:
            raise EffectValidationError("effect ID must be a UUID") from exc
        origin_raw = _required_mapping(raw, "origin")
        target_raw = raw.get("target_hint")
        extensions_raw = raw.get("extensions", {})
        if not isinstance(extensions_raw, Mapping):
            raise EffectValidationError("extensions must be a mapping")
        return cls(
            id=item_id,
            version=_required_int(raw, "version"),
            updated_at=_required_str(raw, "updated_at"),
            name=_required_str(raw, "name"),
            content=_content_from_dict(_required_mapping(raw, "content")),
            content_hash=_required_str(raw, "content_hash"),
            origin=_origin_from_dict(origin_raw),
            target_hint=(
                None
                if target_raw is None
                else TargetHint(
                    model=_required_str(_as_mapping(target_raw, "target_hint"), "model"),
                    segment_count=_optional_int(
                        _as_mapping(target_raw, "target_hint"),
                        "segment_count",
                    ),
                )
            ),
            extensions=cast(dict[str, JsonValue], dict(extensions_raw)),
            schema_version=schema_version,
        )


def _validate_percent(value: int, name: str) -> None:
    _validate_range(value, name, minimum=0, maximum=100)


def _validate_byte(value: int, name: str) -> None:
    _validate_range(value, name, minimum=0, maximum=0xFF)


def _validate_range(value: int, name: str, *, minimum: int, maximum: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise EffectValidationError(f"{name} must be an integer from {minimum} to {maximum}")


def _validate_identifier(value: str, name: str) -> None:
    validate_bounded_string(
        value,
        name,
        maximum=MAX_IDENTIFIER_LENGTH,
        error_type=EffectValidationError,
    )


def _validate_rgb(value: RGB, name: str) -> None:
    if (
        not isinstance(value, tuple)
        or len(value) != 3
        or any(not isinstance(channel, int) or not 0 <= channel <= 0xFF for channel in value)
    ):
        raise EffectValidationError(f"{name} must be an RGB tuple with channels from 0 to 255")


def _validate_palette(palette: Sequence[RGB]) -> None:
    if not 1 <= len(palette) <= MAX_PALETTE_COLOURS:
        raise EffectValidationError(f"palette must contain 1 to {MAX_PALETTE_COLOURS} colours")
    for colour in palette:
        _validate_rgb(colour, "palette colour")


def _validate_palette_scene_count(values: Sequence[object], name: str) -> None:
    if len(values) > 0xFF:
        raise EffectValidationError(f"type-1 scene {name} must contain 0 to 255 items")


def _validate_palette_scene_palette(palette: Sequence[RGB]) -> None:
    _validate_palette_scene_count(palette, "palette")
    for colour in palette:
        _validate_rgb(colour, "palette colour")


def _content_to_dict(content: EffectContent) -> dict[str, JsonValue]:
    if isinstance(content, PaintedEffect):
        return {
            "kind": "h617a_painted",
            "effect": content.effect,
            "speed": content.speed,
            "brightness": content.brightness,
            "segments": [None if segment is None else list(segment) for segment in content.segments],
        }
    if isinstance(content, SingleEffect):
        return {
            "kind": "h617a_single",
            "family": content.family,
            "variant": content.variant,
            "speed": content.speed,
            "palette": [list(colour) for colour in content.palette],
        }
    if isinstance(content, PaletteDiyEffect):
        return {
            "kind": "palette_diy",
            "model": content.model,
            "family": content.family,
            "variant": content.variant,
            "speed": content.speed,
            "palette": [list(colour) for colour in content.palette],
        }
    if isinstance(content, MusicProfile):
        return {
            "kind": "music_profile",
            "model": content.model,
            "mode": content.mode,
            "sensitivity": content.sensitivity,
            "colour": None if content.colour is None else list(content.colour),
            "calm": content.calm,
            "parameters": dict(content.parameters),
        }
    if isinstance(content, VideoProfile):
        return {
            "kind": "video_profile",
            "model": content.model,
            "mode": content.mode,
            "full_screen": content.full_screen,
            "saturation": content.saturation,
            "sound_effects": content.sound_effects,
            "sound_effects_softness": content.sound_effects_softness,
            "white_balance_position": content.white_balance_position,
            "relative_brightness": _relative_brightness_to_dict(content.relative_brightness),
            "blank_screen": content.blank_screen,
        }
    if isinstance(content, MultiEffect):
        return {
            "kind": "h617a_multi",
            "effects": [{"family": effect.family, "variant": effect.variant} for effect in content.effects],
            "speed": content.speed,
            "palette": [list(colour) for colour in content.palette],
        }
    if isinstance(content, WorkshopEffect):
        return {
            "kind": "workshop",
            "model": content.model,
            "template": content.template,
            "effect": layered_effect_to_value(content.effect),
            "raw_param": content.raw_param.hex(),
            "trailing_padding": content.trailing_padding,
        }
    if isinstance(content, LayeredEffect):
        return {"kind": "advanced", **layered_effect_to_value(content)}
    if isinstance(content, BuiltinScene):
        return {
            "kind": "scene_builtin",
            "template": _catalogue_ref_to_dict(content.template),
            "speed_index": content.speed_index,
        }
    if isinstance(content, PaletteScene):
        return {
            "kind": "scene_palette",
            "template": _catalogue_ref_to_dict(content.template),
            "layout": content.layout,
            "brightness_flag": content.brightness_flag,
            "steps": [
                {
                    "value": step.value,
                    "colour": list(step.colour),
                    "inline_colour": (list(step.inline_colour) if step.inline_colour is not None else None),
                }
                for step in content.steps
            ],
            "palette": [list(colour) for colour in content.palette],
            "speed_index": content.speed_index,
            "config_flags": content.config_flags,
            "trailing_padding": content.trailing_padding,
        }
    if isinstance(content, LayeredScene):
        return {"kind": "scene_layered", **layered_scene_to_value(content)}
    return {"kind": content.kind, **dict(content.body)}


def _content_from_dict(raw: Mapping[str, Any]) -> EffectContent:
    kind = _required_str(raw, "kind")
    if kind == "h617a_painted":
        return PaintedEffect(
            effect=_required_str(raw, "effect"),
            speed=_required_int(raw, "speed"),
            brightness=_required_int(raw, "brightness"),
            segments=_painted_segments_from_value(raw.get("segments")),
        )
    if kind == "h617a_single":
        return SingleEffect(
            family=_required_int(raw, "family"),
            variant=_required_int(raw, "variant"),
            speed=_required_int(raw, "speed"),
            palette=_palette_from_value(raw.get("palette")),
        )
    if kind == "palette_diy":
        return PaletteDiyEffect(
            model=_required_str(raw, "model"),
            family=_required_int(raw, "family"),
            variant=_required_int(raw, "variant"),
            speed=_required_int(raw, "speed"),
            palette=_palette_from_value(raw.get("palette")),
        )
    if kind == "music_profile":
        return MusicProfile(
            model=_required_str(raw, "model"),
            mode=_required_str(raw, "mode"),
            sensitivity=_required_int(raw, "sensitivity"),
            colour=_required_optional_rgb(raw, "colour"),
            calm=_required_optional_bool(raw, "calm"),
            parameters=cast(dict[str, JsonValue], dict(_required_mapping(raw, "parameters"))),
        )
    if kind == "video_profile":
        return VideoProfile(
            model=_required_str(raw, "model"),
            mode=_required_str(raw, "mode"),
            full_screen=_required_bool(raw, "full_screen"),
            saturation=_required_int(raw, "saturation"),
            sound_effects=_required_bool(raw, "sound_effects"),
            sound_effects_softness=_required_int(raw, "sound_effects_softness"),
            white_balance_position=_required_int(raw, "white_balance_position"),
            relative_brightness=_relative_brightness_from_dict(_required_mapping(raw, "relative_brightness")),
            blank_screen=_required_bool(raw, "blank_screen"),
        )
    if kind == "h617a_multi":
        return MultiEffect(
            effects=tuple(
                EffectPair(
                    family=_required_int(_as_mapping(effect, "effect pair"), "family"),
                    variant=_required_int(_as_mapping(effect, "effect pair"), "variant"),
                )
                for effect in _required_sequence(raw, "effects")
            ),
            speed=_required_int(raw, "speed"),
            palette=_palette_from_value(raw.get("palette")),
        )
    if kind == "workshop":
        return WorkshopEffect(
            model=_required_str(raw, "model"),
            template=_required_str(raw, "template"),
            effect=layered_effect_from_value(_required_mapping(raw, "effect")),
            raw_param=_hex_bytes(raw.get("raw_param", ""), "Workshop source parameter"),
            trailing_padding=_optional_int(raw, "trailing_padding") or 0,
        )
    if kind == "advanced":
        return layered_effect_from_value(raw)
    if kind == "scene_builtin":
        return BuiltinScene(
            template=_catalogue_ref_from_dict(_required_mapping(raw, "template")),
            speed_index=_optional_int(raw, "speed_index"),
        )
    if kind == "scene_palette":
        return PaletteScene(
            template=_catalogue_ref_from_dict(_required_mapping(raw, "template")),
            layout=_required_int(raw, "layout"),
            brightness_flag=_required_bool(raw, "brightness_flag"),
            steps=tuple(
                _scene_step_from_dict(_as_mapping(step, "scene step")) for step in _required_sequence(raw, "steps")
            ),
            palette=_palette_from_value(raw.get("palette")),
            speed_index=_optional_int(raw, "speed_index"),
            config_flags=_optional_int(raw, "config_flags") or 0,
            trailing_padding=_optional_int(raw, "trailing_padding") or 0,
        )
    if kind == "scene_layered":
        return layered_scene_from_value(raw)
    body = dict(raw)
    body.pop("kind")
    return OpaqueContent(kind=kind, body=cast(dict[str, JsonValue], body))


def _painted_segments_from_value(value: object) -> tuple[RGB | None, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise EffectValidationError("painted segments must be a list")
    if len(value) != H617A_SEGMENT_COUNT:
        raise EffectValidationError(f"painted effect must contain exactly {H617A_SEGMENT_COUNT} segments")
    return tuple(None if segment is None else _rgb_from_value(segment, "painted segment") for segment in value)


def _relative_brightness_to_dict(relative_brightness: RelativeBrightness) -> dict[str, JsonValue]:
    return {
        "left": relative_brightness.left,
        "top": relative_brightness.top,
        "right": relative_brightness.right,
        "bottom": relative_brightness.bottom,
    }


def _relative_brightness_from_dict(raw: Mapping[str, Any]) -> RelativeBrightness:
    return RelativeBrightness(
        left=_required_int(raw, "left"),
        top=_required_int(raw, "top"),
        right=_required_int(raw, "right"),
        bottom=_required_int(raw, "bottom"),
    )


def _scene_step_from_dict(raw: Mapping[str, Any]) -> SceneStep:
    inline = raw.get("inline_colour")
    return SceneStep(
        value=_required_int(raw, "value"),
        colour=_rgb_from_value(raw.get("colour"), "scene step colour"),
        inline_colour=(None if inline is None else _rgb_from_value(inline, "scene inline colour")),
    )


def _rgb_from_value(value: object, name: str) -> RGB:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, str | bytes)
        or len(value) != 3
        or any(not isinstance(channel, int) for channel in value)
    ):
        raise EffectValidationError(f"{name} must contain three integer channels")
    rgb = cast(tuple[int, int, int], tuple(value))
    _validate_rgb(rgb, name)
    return rgb


def _palette_from_value(value: object) -> tuple[RGB, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise EffectValidationError("palette must be a list")
    return tuple(_rgb_from_value(colour, "palette colour") for colour in cast(Sequence[object], value))


def effect_content_hash(content: EffectContent) -> str:
    encoded = json.dumps(
        _content_to_dict(content),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return sha256(encoded).hexdigest()


def _origin_to_dict(origin: Origin) -> dict[str, JsonValue]:
    return {
        "kind": origin.kind.value,
        "source_id": origin.source_id,
    }


def _origin_from_dict(raw: Mapping[str, Any]) -> Origin:
    try:
        kind = SourceKind(_required_str(raw, "kind"))
    except ValueError as exc:
        raise EffectValidationError("unknown origin kind") from exc
    return Origin(
        kind=kind,
        source_id=_optional_str(raw, "source_id"),
    )


def _optional_str(raw: Mapping[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise EffectValidationError(f"{key} must be a string or null")
    return value


def _required_optional_rgb(raw: Mapping[str, Any], key: str) -> RGB | None:
    if key not in raw:
        raise EffectValidationError(f"missing required field {key!r}")
    value = raw[key]
    return None if value is None else _rgb_from_value(value, key)


def _required_optional_bool(raw: Mapping[str, Any], key: str) -> bool | None:
    if key not in raw:
        raise EffectValidationError(f"missing required field {key!r}")
    value = raw[key]
    if value is None:
        return None
    if not isinstance(value, bool):
        raise EffectValidationError(f"{key} must be a boolean or null")
    return value
