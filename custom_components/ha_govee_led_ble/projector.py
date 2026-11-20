"""Complete appearance values for independently controlled projector optics."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

type RGB = tuple[int, int, int]


class ProjectorControl(StrEnum):
    AURORA_MOVEMENT = "projector_aurora_movement"
    AURORA_EFFECT_SPEED = "projector_aurora_effect_speed"
    AURORA_PATTERN = "projector_aurora_pattern"
    STAR_FLICKER = "projector_star_flicker"
    STAR_FLICKER_SPEED = "projector_star_flicker_speed"
    STAR_MOVEMENT = "projector_star_movement"
    STAR_MOVEMENT_SPEED = "projector_star_movement_speed"


def _integer(value: int, maximum: int, name: str) -> None:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f"{name} must be an integer from 0 to {maximum}")


@dataclass(frozen=True, slots=True)
class ProjectorSource:
    enabled: bool
    brightness: int
    pattern: int
    speed: int
    palette: tuple[RGB, ...]

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool or type(self.pattern) is not int or not 0 <= self.pattern <= 4:
            raise ValueError("Invalid projector source")
        for name in ("brightness", "speed"):
            _integer(getattr(self, name), 100, name)
        if not isinstance(self.palette, tuple) or not (1 if self.enabled else 0) <= len(self.palette) <= 8:
            raise ValueError("Projector palette requires up to eight colours and one when enabled")
        for colour in self.palette:
            if not isinstance(colour, tuple) or len(colour) != 3:
                raise ValueError("Projector colours require three channels")
            for channel in colour:
                _integer(channel, 255, "colour channel")


@dataclass(frozen=True, slots=True)
class ProjectorStars:
    enabled: bool
    brightness: int
    flicker_enabled: bool
    flicker_speed: int
    movement_enabled: bool
    movement_speed: int

    def __post_init__(self) -> None:
        for name in ("enabled", "flicker_enabled", "movement_enabled"):
            if type(getattr(self, name)) is not bool:
                raise ValueError("Projector switches require boolean values")
        for name, enabled in (
            ("brightness", self.enabled),
            ("flicker_speed", self.flicker_enabled),
            ("movement_speed", self.movement_enabled),
        ):
            _integer(getattr(self, name), 100 if enabled else 255, name)


@dataclass(frozen=True, slots=True)
class ProjectorLayer:
    movement_speed: int
    direction: int
    coarse: ProjectorSource
    fine: ProjectorSource | None
    stars: ProjectorStars
    duration: int = 0
    opaque: bytes = b""

    def __post_init__(self) -> None:
        _integer(self.movement_speed, 100, "movement speed")
        _integer(self.direction, 1, "direction")
        _integer(self.duration, 65535, "duration")
        if (
            not isinstance(self.coarse, ProjectorSource)
            or self.fine is not None
            and not isinstance(self.fine, ProjectorSource)
            or not isinstance(self.stars, ProjectorStars)
            or not isinstance(self.opaque, bytes)
        ):
            raise ValueError("Invalid projector layer")


@dataclass(frozen=True, slots=True)
class ProjectorAppearance:
    stars: ProjectorStars
    enabled: bool
    movement_speed: int
    brightness: int
    pattern: int
    effect_speed: int
    coarse: tuple[RGB, ...]
    fine: tuple[RGB, ...] | None = None
    coarse_enabled: bool = True
    fine_enabled: bool = True
    opaque: bytes = b""

    def __post_init__(self) -> None:
        _integer(self.movement_speed, 100, "movement speed")
        for value in (self.enabled, self.coarse_enabled, self.fine_enabled):
            if type(value) is not bool:
                raise ValueError("Projector switches require boolean values")
        if not isinstance(self.stars, ProjectorStars):
            raise ValueError("Invalid projector stars")
        if not isinstance(self.opaque, bytes):
            raise ValueError("Invalid projector appearance extension")
        ProjectorSource(
            self.enabled and self.coarse_enabled, self.brightness, self.pattern, self.effect_speed, self.coarse
        )
        if self.fine is not None:
            ProjectorSource(
                self.enabled and self.fine_enabled, self.brightness, self.pattern, self.effect_speed, self.fine
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "stars": stars_to_value(self.stars),
            "enabled": self.enabled,
            "movement_speed": self.movement_speed,
            "brightness": self.brightness,
            "pattern": self.pattern,
            "effect_speed": self.effect_speed,
            "coarse": [list(rgb) for rgb in self.coarse],
            "fine": None if self.fine is None else [list(rgb) for rgb in self.fine],
            "coarse_enabled": self.coarse_enabled,
            "fine_enabled": self.fine_enabled,
            "opaque": self.opaque.hex(),
        }

    @classmethod
    def from_dict(cls, value: Any) -> ProjectorAppearance:
        if not isinstance(value, dict):
            raise ValueError("Invalid projector appearance")
        required = {
            "stars",
            "enabled",
            "movement_speed",
            "brightness",
            "pattern",
            "effect_speed",
            "coarse",
            "fine",
            "coarse_enabled",
            "fine_enabled",
            "opaque",
        }
        if set(value) != required:
            raise ValueError("Invalid projector appearance fields")
        return cls(
            **{key: item for key, item in value.items() if key not in {"stars", "coarse", "fine", "opaque"}},
            stars=stars_from_value(value["stars"]),
            coarse=tuple(tuple(rgb) for rgb in value["coarse"]),
            fine=None if value["fine"] is None else tuple(tuple(rgb) for rgb in value["fine"]),
            opaque=bytes.fromhex(value["opaque"]),
        )


def source_to_value(source: ProjectorSource) -> dict[str, Any]:
    return {
        "enabled": source.enabled,
        "brightness": source.brightness,
        "pattern": source.pattern,
        "speed": source.speed,
        "palette": [list(colour) for colour in source.palette],
    }


def source_from_value(value: Any) -> ProjectorSource:
    if not isinstance(value, dict) or set(value) != {"enabled", "brightness", "pattern", "speed", "palette"}:
        raise ValueError("Invalid projector source fields")
    palette = value["palette"]
    if not isinstance(palette, list) or any(not isinstance(colour, list) for colour in palette):
        raise ValueError("Invalid projector palette")
    return ProjectorSource(
        enabled=value["enabled"],
        brightness=value["brightness"],
        pattern=value["pattern"],
        speed=value["speed"],
        palette=tuple(tuple(colour) for colour in palette),
    )


def stars_to_value(stars: ProjectorStars) -> dict[str, Any]:
    return {
        "enabled": stars.enabled,
        "brightness": stars.brightness,
        "flicker_enabled": stars.flicker_enabled,
        "flicker_speed": stars.flicker_speed,
        "movement_enabled": stars.movement_enabled,
        "movement_speed": stars.movement_speed,
    }


def stars_from_value(value: Any) -> ProjectorStars:
    fields = {"enabled", "brightness", "flicker_enabled", "flicker_speed", "movement_enabled", "movement_speed"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("Invalid projector star fields")
    return ProjectorStars(**value)
