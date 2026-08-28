"""Effect-content migration helpers for retired schema versions."""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

from .const import MODEL_PROFILES

type RGB = tuple[int, int, int]

PAINTED_SEGMENT_COUNT = MODEL_PROFILES["H617A"].segment_count


class LegacyEffectMigrationError(ValueError):
    """Legacy effect content cannot be converted safely."""


def migrate_effect_content_v1(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise LegacyEffectMigrationError("legacy effect content must be a mapping")
    raw = dict(value)
    if raw.get("kind") != "h617a_painted":
        return copy.deepcopy(raw)
    background = _rgb(raw.get("background"), "legacy painted background")
    segments: list[list[int] | None] = [
        None if background == (0, 0, 0) else list(background) for _ in range(PAINTED_SEGMENT_COUNT)
    ]
    groups = raw.get("groups")
    if not isinstance(groups, Sequence) or isinstance(groups, str | bytes | bytearray):
        raise LegacyEffectMigrationError("legacy paint groups must be a sequence")
    claimed: set[int] = set()
    for index, value_group in enumerate(groups):
        if not isinstance(value_group, Mapping):
            raise LegacyEffectMigrationError(f"legacy paint group {index} must be a mapping")
        group = dict(value_group)
        fill = _rgb(group.get("fill"), f"legacy paint group {index} fill")
        indices = group.get("segments")
        if not isinstance(indices, Sequence) or isinstance(indices, str | bytes | bytearray) or not indices:
            raise LegacyEffectMigrationError(f"legacy paint group {index} segments must be a non-empty sequence")
        for segment in indices:
            if not isinstance(segment, int) or isinstance(segment, bool) or not 0 <= segment < PAINTED_SEGMENT_COUNT:
                raise LegacyEffectMigrationError(f"legacy painted segment {segment!r} is outside the supported range")
            if segment in claimed:
                raise LegacyEffectMigrationError(f"legacy painted segment {segment} appears in multiple groups")
            claimed.add(segment)
            segments[segment] = list(fill)
    return {
        "kind": "h617a_painted",
        "effect": raw.get("effect"),
        "speed": raw.get("speed"),
        "brightness": raw.get("brightness"),
        "segments": segments,
    }


def _rgb(value: object, name: str) -> RGB:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, str | bytes | bytearray)
        or len(value) != 3
        or any(
            not isinstance(channel, int) or isinstance(channel, bool) or not 0 <= channel <= 0xFF for channel in value
        )
    ):
        raise LegacyEffectMigrationError(f"{name} must contain three integer channels from 0 to 255")
    return (value[0], value[1], value[2])
