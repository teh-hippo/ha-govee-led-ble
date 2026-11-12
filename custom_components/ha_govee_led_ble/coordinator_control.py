"""Revision-aware rollback of optimistic coordinator control state."""

from __future__ import annotations

import logging
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from copy import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from bleak.exc import BleakError

from .const import ModelProfile, ReadDomain
from .control_arbiter import ControlIntent, async_control_intent
from .coordinator_refresh import RefreshRequest

if TYPE_CHECKING:
    from .coordinator_base import _CoordinatorBase
    from .native_profile_controls import ProfileWriter

_LOGGER = logging.getLogger(__name__)

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


class ControlWriteRequest:
    def __init__(
        self,
        coordinator: _CoordinatorBase,
        *,
        identity_guard: Callable[[], None] | None = None,
        effect_guard: Callable[[], None] | None = None,
    ) -> None:
        self._coordinator = coordinator
        self._identity_guard = identity_guard
        self._effect_guard = effect_guard
        self._client, self._token = coordinator._client, coordinator._notification_token
        self._attempted_fields: dict[str, int] = {}
        self._tracked_field: str | None = None
        self._tracked_attempts = self._tracked_revision = 0
        self.phase = "power"

    @property
    def has_attempted_writes(self) -> bool:
        return bool(self._attempted_fields)

    def before_write(self) -> None:
        if self._identity_guard is not None:
            self._identity_guard()
        if self._effect_guard is not None:
            self._effect_guard()
        if (
            self._identity_guard is not None
            and self._tracked_field is not None
            and self._coordinator.control_write_attempts == self._tracked_attempts
        ):
            self._tracked_revision = self._coordinator._field_revisions.get(self._tracked_field, 0)

    @contextmanager
    def track(self, field: str) -> Generator[None]:
        self._tracked_field = field
        self._tracked_attempts = self._coordinator.control_write_attempts
        self._tracked_revision = self._coordinator._field_revisions.get(field, 0)
        try:
            yield
        finally:
            if self._identity_guard is not None and self._coordinator.control_write_attempts != self._tracked_attempts:
                self._attempted_fields[field] = self._tracked_revision
            self._tracked_field = None

    async def send(self, packet: bytes) -> None:
        if self._effect_guard is not None:
            await async_send_guarded_command(self._coordinator, packet, write_guard=self.before_write)
        elif self._identity_guard is not None:
            await self._coordinator.send_command(packet, write_guard=self.before_write)
        else:
            await self._coordinator.send_command(packet)

    def mark_interrupted(self) -> None:
        coordinator = self._coordinator
        for field, revision in self._attempted_fields.items():
            if coordinator._field_revisions.get(field, 0) <= revision:
                uncertain = "color" if field in {"rgb_color", "color_temp_kelvin"} else field
                coordinator._h607c_uncertain_state_fields.add(uncertain)
                if uncertain == "color":
                    coordinator._h607c_failed_color_write = True
                for expected in ("color_mode", "rgb_color", "color_temp_kelvin") if uncertain == "color" else (field,):
                    coordinator._expected_state.pop(expected, None)

    async def reconcile(self) -> None:
        coordinator, client = self._coordinator, self._client
        if (
            not coordinator._h607c_uncertain_state_fields.intersection({"is_on", "brightness_pct"})
            or client is None
            or coordinator._client is not client
            or not client.is_connected
            or coordinator._notification_token is not self._token
            or (coordinator._encryption is not None and not coordinator._encryption.ready)
        ):
            return
        try:
            await coordinator._refresh_connected_state(
                RefreshRequest(
                    refresh_all=True,
                    query_segments=False,
                    query_native_settings=False,
                    required_domains=coordinator.profile.read_domains & {ReadDomain.POWER, ReadDomain.BRIGHTNESS},
                )
            )
        except BleakError, ValueError, TimeoutError:
            _LOGGER.debug("Could not reconcile interrupted Govee %s request", coordinator.model, exc_info=True)
        coordinator.async_set_updated_data(coordinator.data or {})

    def complete(self, *, colour_requested: bool) -> None:
        if self._identity_guard is not None and colour_requested:
            self._coordinator._h607c_failed_color_write = False


async def async_send_guarded_command(
    coordinator: _CoordinatorBase,
    packet: bytes,
    *,
    write_guard: Callable[[], None] | None = None,
    prepared_profile: ModelProfile | None = None,
    writer: ProfileWriter | None = None,
    state_values: Mapping[str, Any] | None = None,
    expected_values: Mapping[str, Any] | None = None,
    on_write: Callable[[], None] | None = None,
) -> None:
    profile = coordinator.profile if prepared_profile is None else prepared_profile
    if coordinator._client is None or not coordinator._client.is_connected:
        current_intent = coordinator._control_arbiter.current_task_intent
        async with async_control_intent(coordinator, current_intent or ControlIntent.USER):
            async with coordinator._lock:
                await coordinator._ensure_connected()
    client, token = coordinator._client, coordinator._notification_token
    generation = coordinator._authorization_generation

    def check() -> None:
        if (
            coordinator.profile != profile
            or coordinator._client is not client
            or coordinator._notification_token is not token
            or coordinator._authorization_generation != generation
        ):
            raise ValueError("Control profile, identity or subscription changed before write; refresh and retry")
        if write_guard is not None:
            write_guard()

    check()
    if writer is None:

        def commit(_index: int) -> None:
            if on_write is not None:
                on_write()

        await coordinator.async_write_effect_sequence(
            (packet,),
            intent=coordinator._control_arbiter.current_task_intent or ControlIntent.USER,
            write_guard=check,
            state_values=state_values,
            expected_values=expected_values,
            packet_on_write=commit if on_write is not None else None,
        )
    else:
        await writer(
            packet,
            write_guard=check,
            state_values=state_values,
            expected_values=expected_values,
            **({"on_write": on_write} if on_write is not None else {}),
        )
