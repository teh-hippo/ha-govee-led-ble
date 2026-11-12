"""Revision-aware rollback of optimistic coordinator control state."""

from __future__ import annotations

from copy import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .const import ReadDomain

if TYPE_CHECKING:
    from .coordinator_base import _CoordinatorBase

_CONTROL_STATE_FIELDS = (
    "is_on",
    "brightness_pct",
    "rgb_color",
    "color_temp_kelvin",
    "effect",
    "video_saturation",
    "rgb_color_source",
    "color_temp_kelvin_source",
    "segment_colors",
    "video_full_screen",
    "video_sound_effects",
    "video_sound_effects_softness",
    "white_brightness",
    "music_sensitivity",
    "_music_calm",
    "music_color",
    "diy_code",
    "music_mode",
    "video_mode",
    "color_mode",
    "_scene_code",
    "segment_brightness",
    "segment_state_source",
    "segment_state_observed_at",
    "_segment_groups_observed",
    "_segment_query_colors",
    "_segment_query_brightness",
)


@dataclass(frozen=True, slots=True)
class ControlStateSnapshot:
    values: dict[str, Any]
    profile_generation: int
    revisions: dict[str, int]
    segment_revision: int
    static_attempts: int


class ControlStateCheckpoint:
    def __init__(self, coordinator: _CoordinatorBase) -> None:
        self._coordinator = coordinator
        self._snapshots: list[ControlStateSnapshot] = []
        self.checkpoint()

    @property
    def current(self) -> ControlStateSnapshot:
        return self._snapshots[-1]

    def checkpoint(self) -> ControlStateSnapshot:
        coordinator = self._coordinator
        snapshot = ControlStateSnapshot(
            {field: copy(getattr(coordinator, field)) for field in _CONTROL_STATE_FIELDS},
            coordinator._profile_generation,
            dict(coordinator._field_revisions),
            coordinator._domain_revisions.get(ReadDomain.SEGMENTS, 0),
            coordinator._static_write_attempts,
        )
        self._snapshots.append(snapshot)
        return snapshot

    def mode_observed(self, snapshot: ControlStateSnapshot) -> bool:
        return self._coordinator._field_revisions.get("color_mode", 0) != snapshot.revisions.get("color_mode", 0)

    def _restorable_values(self, snapshot: ControlStateSnapshot) -> dict[str, Any]:
        coordinator = self._coordinator
        if coordinator._profile_generation != snapshot.profile_generation:
            return {}
        mode_updated = self.mode_observed(snapshot)
        colour_updated = any(
            coordinator._field_revisions.get(field, 0) != snapshot.revisions.get(field, 0)
            for field in ("rgb_color", "color_temp_kelvin")
        )
        segments_updated = coordinator._field_revisions.get("segment_colors", 0) != snapshot.revisions.get(
            "segment_colors", 0
        )
        segment_page_received = coordinator._domain_revisions.get(ReadDomain.SEGMENTS, 0) != snapshot.segment_revision
        values: dict[str, Any] = {}
        for field, value in snapshot.values.items():
            if coordinator._static_write_attempts != snapshot.static_attempts and (
                field.startswith(("segment_", "_segment_")) or field in {"rgb_color_source", "color_temp_kelvin_source"}
            ):
                continue
            if field.startswith("_segment_"):
                if segment_page_received:
                    continue
            elif field.startswith("segment_"):
                if segments_updated:
                    continue
            elif field not in {"is_on", "brightness_pct"} and mode_updated:
                continue
            if (colour_updated or segments_updated) and field in {
                "rgb_color",
                "color_temp_kelvin",
                "rgb_color_source",
                "color_temp_kelvin_source",
            }:
                continue
            revision_field = "music_calm" if field == "_music_calm" else field
            if revision_field in {"is_on", "brightness_pct", "music_calm"} and coordinator._field_revisions.get(
                revision_field, 0
            ) != snapshot.revisions.get(revision_field, 0):
                continue
            values[field] = value
        return values

    def restore(self) -> None:
        values: dict[str, Any] = {}
        for snapshot in reversed(self._snapshots):
            values.update(self._restorable_values(snapshot))
        for field, value in values.items():
            setattr(self._coordinator, field, value)
