"""Typed custom-effect content model, validators and JSON codec (pure: no HA/BLE imports)."""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal
from uuid import uuid4

type RGB = tuple[int, int, int]


@dataclass(frozen=True)
class SegmentContent:
    kind: Literal["segments"] = "segments"
    colors: tuple[RGB | None, ...] = ()
    brightness: tuple[int | None, ...] | None = None


@dataclass(frozen=True)
class SketchContent:
    kind: Literal["sketch"] = "sketch"
    motion: int = 0x09
    speed: int = 0x33
    brightness: int = 0x64
    background: RGB = (0, 0, 0)
    colors: tuple[RGB | None, ...] = ()


@dataclass(frozen=True)
class VibrantContent:
    kind: Literal["vibrant"] = "vibrant"
    stops: tuple[RGB, ...] = ()


@dataclass(frozen=True)
class FlatContent:
    kind: Literal["flat"] = "flat"
    family: int = 0x00
    variant: int = 0x00
    speed: int = 0x32
    palette: tuple[RGB, ...] = ()


@dataclass(frozen=True)
class ComboContent:
    kind: Literal["combo"] = "combo"
    variant: int = 0x00
    speed: int = 0x32
    palette: tuple[RGB, ...] = ()
    effects: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True)
class UnknownContent:
    kind: str
    raw: dict[str, Any]


type AuthorableContent = SegmentContent | SketchContent | VibrantContent | FlatContent | ComboContent
type EffectContent = AuthorableContent | UnknownContent


@dataclass(frozen=True)
class CustomEffect:
    id: str
    display_name: str
    name_key: str
    content: EffectContent


class EffectValidationError(ValueError):
    """Raised when content violates a catalogue-sourced bound; the key maps to a translated error."""

    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


# CAT 2.4: Finger Sketch motion codes (Cycle, Clockwise, Counter-clockwise, Twinkle, Gradient, Breathe).
_SKETCH_MOTION_CODES: frozenset[int] = frozenset({0x02, 0x09, 0x0A, 0x0F, 0x13, 0x14})
# CAT 2.4/2.7: sketch speed and brightness are 0..100 percentage bytes (observed max 0x64).
_SKETCH_SPEED_RANGE: range = range(0, 101)
_SKETCH_BRIGHT_RANGE: range = range(0, 101)

# CAT 2.6: confirmed flat (FAMILY, VARIANT) pairs, keyed by family (variants have catalogue gaps).
_FLAT_VARIANTS_BY_FAMILY: dict[int, tuple[int, ...]] = {
    0x00: (0x00, 0x01, 0x02),  # Fade 1..3
    0x01: (0x00, 0x02),  # Jumping 1..2 (variant skips 0x01)
    0x02: (0x00, 0x01, 0x02),  # Twinkle 1..3
    0x03: (0x03, 0x04, 0x05),  # Marquee 1..3
    0x04: (0x06, 0x07, 0x08),  # Music 1..3
    0x08: (0x09, 0x0A),  # Chasing 1..2
    0x09: (0x09, 0x0A),  # Rainbow 1..2
    0x0A: (0x00,),  # Crossing
}
_FLAT_FAMILY_VARIANTS: frozenset[tuple[int, int]] = frozenset(
    (family, variant) for family, variants in _FLAT_VARIANTS_BY_FAMILY.items() for variant in variants
)

_CROSSING_FAMILY = 0x0A


def _flat_palette_max(family: int) -> int:
    # CAT 2.7: Crossing caps at 3 colours; every other flat family allows up to 8.
    return 3 if family == _CROSSING_FAMILY else 8


def _require(condition: bool, key: str) -> None:
    if not condition:
        raise EffectValidationError(key)


def _is_rgb(value: object) -> bool:
    return (
        isinstance(value, tuple)
        and len(value) == 3
        and all(isinstance(channel, int) and 0 <= channel <= 255 for channel in value)
    )


def validate_content(content: AuthorableContent, *, segment_count: int) -> None:
    match content:
        case SegmentContent():
            _require(len(content.colors) <= segment_count, "too_many_segments")
            _require(all(_is_rgb(c) for c in content.colors if c is not None), "bad_rgb")
        case VibrantContent():
            _require(2 <= len(content.stops) <= 5, "vibrant_stops_range")
            _require(all(_is_rgb(s) for s in content.stops), "vibrant_bad_rgb")
        case SketchContent():
            _require(len(content.colors) <= segment_count, "too_many_segments")
            _require(all(_is_rgb(c) for c in content.colors if c is not None), "bad_rgb")
            _require(_is_rgb(content.background), "sketch_bad_background")
            _require(content.motion in _SKETCH_MOTION_CODES, "sketch_motion_invalid")
            _require(content.speed in _SKETCH_SPEED_RANGE, "sketch_speed_range")
            _require(content.brightness in _SKETCH_BRIGHT_RANGE, "sketch_brightness_range")
        case FlatContent():
            _require((content.family, content.variant) in _FLAT_FAMILY_VARIANTS, "flat_family_variant_invalid")
            _require(len(content.palette) <= _flat_palette_max(content.family), "palette_too_large")
            _require(all(_is_rgb(s) for s in content.palette), "flat_bad_rgb")
        case ComboContent():
            _require(len(content.effects) <= 4, "combo_too_many")
            _require(all(fv in _FLAT_FAMILY_VARIANTS for fv in content.effects), "combo_family_variant_invalid")
            _require(len(content.palette) <= 8, "palette_too_large")
            _require(all(_is_rgb(s) for s in content.palette), "combo_bad_rgb")


_CONTENT_TYPES: dict[str, type[AuthorableContent]] = {
    "segments": SegmentContent,
    "sketch": SketchContent,
    "vibrant": VibrantContent,
    "flat": FlatContent,
    "combo": ComboContent,
}


def _rgb_to_json(rgb: RGB) -> list[int]:
    return [rgb[0], rgb[1], rgb[2]]


def _opt_rgb_to_json(value: RGB | None) -> list[int] | None:
    return None if value is None else _rgb_to_json(value)


def _rgb_from_json(value: Any) -> RGB:
    red, green, blue = value
    return (int(red), int(green), int(blue))


def _opt_rgb_from_json(value: Any) -> RGB | None:
    return None if value is None else _rgb_from_json(value)


def content_to_dict(content: EffectContent) -> dict[str, Any]:
    if isinstance(content, UnknownContent):
        return {"kind": content.kind, **content.raw}
    if isinstance(content, SegmentContent):
        return {
            "kind": content.kind,
            "colors": [_opt_rgb_to_json(c) for c in content.colors],
            "brightness": None if content.brightness is None else list(content.brightness),
        }
    if isinstance(content, SketchContent):
        return {
            "kind": content.kind,
            "motion": content.motion,
            "speed": content.speed,
            "brightness": content.brightness,
            "background": _rgb_to_json(content.background),
            "colors": [_opt_rgb_to_json(c) for c in content.colors],
        }
    if isinstance(content, VibrantContent):
        return {"kind": content.kind, "stops": [_rgb_to_json(s) for s in content.stops]}
    if isinstance(content, FlatContent):
        return {
            "kind": content.kind,
            "family": content.family,
            "variant": content.variant,
            "speed": content.speed,
            "palette": [_rgb_to_json(s) for s in content.palette],
        }
    return {
        "kind": content.kind,
        "variant": content.variant,
        "speed": content.speed,
        "palette": [_rgb_to_json(s) for s in content.palette],
        "effects": [[family, variant] for family, variant in content.effects],
    }


def _segment_from_dict(data: dict[str, Any]) -> SegmentContent:
    raw_brightness = data.get("brightness")
    brightness = None if raw_brightness is None else tuple(None if b is None else int(b) for b in raw_brightness)
    return SegmentContent(
        colors=tuple(_opt_rgb_from_json(c) for c in data.get("colors", ())),
        brightness=brightness,
    )


def _sketch_from_dict(data: dict[str, Any]) -> SketchContent:
    return SketchContent(
        motion=int(data.get("motion", 0x09)),
        speed=int(data.get("speed", 0x33)),
        brightness=int(data.get("brightness", 0x64)),
        background=_rgb_from_json(data.get("background", (0, 0, 0))),
        colors=tuple(_opt_rgb_from_json(c) for c in data.get("colors", ())),
    )


def _vibrant_from_dict(data: dict[str, Any]) -> VibrantContent:
    return VibrantContent(stops=tuple(_rgb_from_json(s) for s in data.get("stops", ())))


def _flat_from_dict(data: dict[str, Any]) -> FlatContent:
    return FlatContent(
        family=int(data.get("family", 0x00)),
        variant=int(data.get("variant", 0x00)),
        speed=int(data.get("speed", 0x32)),
        palette=tuple(_rgb_from_json(s) for s in data.get("palette", ())),
    )


def _combo_from_dict(data: dict[str, Any]) -> ComboContent:
    return ComboContent(
        variant=int(data.get("variant", 0x00)),
        speed=int(data.get("speed", 0x32)),
        palette=tuple(_rgb_from_json(s) for s in data.get("palette", ())),
        effects=tuple((int(family), int(variant)) for family, variant in data.get("effects", ())),
    )


def content_from_dict(data: dict[str, Any]) -> EffectContent:
    kind = data.get("kind")
    if not isinstance(kind, str) or kind not in _CONTENT_TYPES:
        return UnknownContent(
            kind=kind if isinstance(kind, str) else "unknown",
            raw={key: value for key, value in data.items() if key != "kind"},
        )
    if kind == "segments":
        return _segment_from_dict(data)
    if kind == "sketch":
        return _sketch_from_dict(data)
    if kind == "vibrant":
        return _vibrant_from_dict(data)
    if kind == "flat":
        return _flat_from_dict(data)
    return _combo_from_dict(data)


_EFFECT_QUOTE_CHARS = "\"'“”‘’"


def normalise_name(name: str) -> str:
    core = name.strip().strip(_EFFECT_QUOTE_CHARS).strip().lower()
    return " ".join(core.split()).casefold()


def new_effect_id(existing: Iterable[str]) -> str:
    taken = set(existing)
    while True:
        candidate = uuid4().hex[:8]
        if candidate not in taken:
            return candidate
