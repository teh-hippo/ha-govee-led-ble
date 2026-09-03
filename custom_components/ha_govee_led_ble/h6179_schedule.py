"""Protocol-neutral H6179 schedule values."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from datetime import time as dt_time
from enum import IntFlag, StrEnum
from typing import Self

SCHEDULE_SLOT_COUNT = 4
MIN_TIMEZONE_OFFSET_MINUTES = -12 * 60
MAX_TIMEZONE_OFFSET_MINUTES = 14 * 60
MAX_REPEAT_DAY_MASK = 0x7F
MIN_SLEEP_START_BRIGHTNESS = 0
MAX_SLEEP_START_BRIGHTNESS = 100
MAX_SLEEP_DURATION_MINUTES = 0xFF
MAX_SLEEP_REMAINING_MINUTES = 0xFF
MIN_WAKE_DURATION_MINUTES = 10
MAX_WAKE_DURATION_MINUTES = 60
MIN_TARGET_BRIGHTNESS = 10
MAX_TARGET_BRIGHTNESS = 100

ActionPayload = dict[str, bool | int | str]
StatusFields = Mapping[str, object]


class ScheduleValidationError(ValueError):
    """An H6179 schedule value is invalid."""


class ScheduleAction(StrEnum):
    OFF = "off"
    ON = "on"


class RepeatDay(IntFlag):
    MONDAY = 1 << 0
    TUESDAY = 1 << 1
    WEDNESDAY = 1 << 2
    THURSDAY = 1 << 3
    FRIDAY = 1 << 4
    SATURDAY = 1 << 5
    SUNDAY = 1 << 6


def _validate_bool(value: object, name: str) -> None:
    if not isinstance(value, bool):
        raise ScheduleValidationError(f"{name} must be a boolean")


def _validate_int(value: object, name: str, minimum: int, maximum: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ScheduleValidationError(f"{name} must be an integer from {minimum} to {maximum}")


def validate_slot(slot: int) -> None:
    """Validate a zero-based schedule slot."""
    _validate_int(slot, "schedule slot", 0, SCHEDULE_SLOT_COUNT - 1)


def validate_repeat_day_mask(repeat_day_mask: int) -> None:
    """Validate the semantic Monday-to-Sunday repeat mask."""
    _validate_int(repeat_day_mask, "repeat-day mask", 0, MAX_REPEAT_DAY_MASK)


def validate_schedule_time(value: dt_time) -> None:
    """Validate a local minute-precision schedule time."""
    if not isinstance(value, dt_time):
        raise ScheduleValidationError("schedule time must be a datetime.time")
    if value.tzinfo is not None:
        raise ScheduleValidationError("schedule time must not include a UTC offset")
    if value.second or value.microsecond:
        raise ScheduleValidationError("schedule time must have minute precision")


def validate_timezone_offset_minutes(offset_minutes: int) -> None:
    """Validate a real-world UTC offset range."""
    _validate_int(
        offset_minutes,
        "timezone offset",
        MIN_TIMEZONE_OFFSET_MINUTES,
        MAX_TIMEZONE_OFFSET_MINUTES,
    )


def _timezone_offset_minutes(value: datetime) -> int:
    offset = value.utcoffset()
    if offset is None:
        raise ScheduleValidationError("local time must include a UTC offset")
    seconds = offset.total_seconds()
    if seconds % 60:
        raise ScheduleValidationError("local time UTC offset must use whole minutes")
    offset_minutes = int(seconds // 60)
    validate_timezone_offset_minutes(offset_minutes)
    return offset_minutes


@dataclass(frozen=True, slots=True)
class ClockSync:
    """One local wall-clock value with its UTC offset."""

    local_time: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.local_time, datetime):
            raise ScheduleValidationError("local time must be a datetime")
        if self.local_time.microsecond:
            raise ScheduleValidationError("local time must have second precision")
        _timezone_offset_minutes(self.local_time)

    @property
    def timezone_offset_minutes(self) -> int:
        return _timezone_offset_minutes(self.local_time)

    def to_action_payload(self) -> ActionPayload:
        return {
            "local_time": self.local_time.isoformat(timespec="seconds"),
            "timezone_offset_minutes": self.timezone_offset_minutes,
        }

    def to_status_fields(self) -> StatusFields:
        return self.to_action_payload()


@dataclass(frozen=True, slots=True)
class ScheduleSlot:
    slot: int
    enabled: bool
    action: ScheduleAction
    time: dt_time
    repeat_day_mask: int

    def __post_init__(self) -> None:
        validate_slot(self.slot)
        _validate_bool(self.enabled, "schedule enabled")
        if not isinstance(self.action, ScheduleAction):
            raise ScheduleValidationError("schedule action must be ScheduleAction.ON or ScheduleAction.OFF")
        validate_schedule_time(self.time)
        validate_repeat_day_mask(self.repeat_day_mask)

    @classmethod
    def disabled(cls, slot: int) -> Self:
        return cls(
            slot=slot,
            enabled=False,
            action=ScheduleAction.OFF,
            time=dt_time(),
            repeat_day_mask=0,
        )

    def updated(
        self,
        *,
        enabled: bool | None = None,
        action: ScheduleAction | None = None,
        time: dt_time | None = None,
        repeat_day_mask: int | None = None,
    ) -> Self:
        """Return a validated partial update, retaining unspecified fields."""
        return replace(
            self,
            enabled=self.enabled if enabled is None else enabled,
            action=self.action if action is None else action,
            time=self.time if time is None else time,
            repeat_day_mask=self.repeat_day_mask if repeat_day_mask is None else repeat_day_mask,
        )

    def to_action_payload(self) -> ActionPayload:
        return {
            "slot": self.slot,
            "enabled": self.enabled,
            "action": self.action.value,
            "time": self.time.isoformat(timespec="minutes"),
            "repeat_day_mask": self.repeat_day_mask,
        }

    def to_status_fields(self) -> StatusFields:
        return self.to_action_payload()


@dataclass(frozen=True, slots=True)
class SleepState:
    enabled: bool
    start_brightness: int
    duration_minutes: int
    remaining_minutes: int

    def __post_init__(self) -> None:
        _validate_bool(self.enabled, "sleep enabled")
        _validate_int(
            self.start_brightness,
            "sleep start brightness",
            MIN_SLEEP_START_BRIGHTNESS,
            MAX_SLEEP_START_BRIGHTNESS,
        )
        _validate_int(self.duration_minutes, "sleep duration", 0, MAX_SLEEP_DURATION_MINUTES)
        _validate_int(self.remaining_minutes, "sleep remaining time", 0, MAX_SLEEP_REMAINING_MINUTES)

    @classmethod
    def disabled(
        cls,
        *,
        start_brightness: int = 0,
        duration_minutes: int = 0,
        remaining_minutes: int = 0,
    ) -> Self:
        return cls(
            enabled=False,
            start_brightness=start_brightness,
            duration_minutes=duration_minutes,
            remaining_minutes=remaining_minutes,
        )

    def updated(
        self,
        *,
        enabled: bool | None = None,
        start_brightness: int | None = None,
        duration_minutes: int | None = None,
        remaining_minutes: int | None = None,
    ) -> Self:
        """Return a validated partial update, retaining unspecified fields."""
        return replace(
            self,
            enabled=self.enabled if enabled is None else enabled,
            start_brightness=self.start_brightness if start_brightness is None else start_brightness,
            duration_minutes=self.duration_minutes if duration_minutes is None else duration_minutes,
            remaining_minutes=self.remaining_minutes if remaining_minutes is None else remaining_minutes,
        )

    def to_action_payload(self) -> ActionPayload:
        return {
            "enabled": self.enabled,
            "start_brightness": self.start_brightness,
            "duration_minutes": self.duration_minutes,
        }

    def to_status_fields(self) -> StatusFields:
        return {
            **self.to_action_payload(),
            "remaining_minutes": self.remaining_minutes,
        }


@dataclass(frozen=True, slots=True)
class WakeState:
    enabled: bool
    time: dt_time
    repeat_day_mask: int
    duration_minutes: int
    target_brightness: int

    def __post_init__(self) -> None:
        _validate_bool(self.enabled, "wake enabled")
        validate_schedule_time(self.time)
        validate_repeat_day_mask(self.repeat_day_mask)
        _validate_int(
            self.duration_minutes,
            "wake duration",
            MIN_WAKE_DURATION_MINUTES,
            MAX_WAKE_DURATION_MINUTES,
        )
        _validate_int(
            self.target_brightness,
            "wake target brightness",
            MIN_TARGET_BRIGHTNESS,
            MAX_TARGET_BRIGHTNESS,
        )

    @classmethod
    def disabled(cls) -> Self:
        return cls(
            enabled=False,
            time=dt_time(),
            repeat_day_mask=0,
            duration_minutes=MIN_WAKE_DURATION_MINUTES,
            target_brightness=MAX_TARGET_BRIGHTNESS,
        )

    def updated(
        self,
        *,
        enabled: bool | None = None,
        time: dt_time | None = None,
        repeat_day_mask: int | None = None,
        duration_minutes: int | None = None,
        target_brightness: int | None = None,
    ) -> Self:
        """Return a validated partial update, retaining unspecified fields."""
        return replace(
            self,
            enabled=self.enabled if enabled is None else enabled,
            time=self.time if time is None else time,
            repeat_day_mask=self.repeat_day_mask if repeat_day_mask is None else repeat_day_mask,
            duration_minutes=self.duration_minutes if duration_minutes is None else duration_minutes,
            target_brightness=self.target_brightness if target_brightness is None else target_brightness,
        )

    def to_action_payload(self) -> ActionPayload:
        return {
            "enabled": self.enabled,
            "time": self.time.isoformat(timespec="minutes"),
            "repeat_day_mask": self.repeat_day_mask,
            "duration_minutes": self.duration_minutes,
            "target_brightness": self.target_brightness,
        }

    def to_status_fields(self) -> StatusFields:
        return self.to_action_payload()


@dataclass(frozen=True, slots=True)
class LimitState:
    enabled: bool = False

    def __post_init__(self) -> None:
        _validate_bool(self.enabled, "limit enabled")

    def updated(self, *, enabled: bool) -> Self:
        return replace(self, enabled=enabled)

    def to_action_payload(self) -> ActionPayload:
        return {"enabled": self.enabled}

    def to_status_fields(self) -> StatusFields:
        return self.to_action_payload()


NEUTRAL_LIMIT_STATE = LimitState()


@dataclass(frozen=True, slots=True)
class ScheduleState:
    schedule_slots: tuple[ScheduleSlot, ...]
    sleep: SleepState
    wake: WakeState
    clock_sync: ClockSync | None = None
    limit_state: LimitState = NEUTRAL_LIMIT_STATE

    def __post_init__(self) -> None:
        if not isinstance(self.schedule_slots, tuple) or len(self.schedule_slots) != SCHEDULE_SLOT_COUNT:
            raise ScheduleValidationError(f"schedule slots must be a tuple of exactly {SCHEDULE_SLOT_COUNT} records")
        for slot, record in enumerate(self.schedule_slots):
            if not isinstance(record, ScheduleSlot):
                raise ScheduleValidationError("schedule slots must contain ScheduleSlot records")
            if record.slot != slot:
                raise ScheduleValidationError("schedule slot records must be ordered by slot number")
        if not isinstance(self.sleep, SleepState):
            raise ScheduleValidationError("sleep state must be SleepState")
        if not isinstance(self.wake, WakeState):
            raise ScheduleValidationError("wake state must be WakeState")
        if self.clock_sync is not None and not isinstance(self.clock_sync, ClockSync):
            raise ScheduleValidationError("clock sync must be ClockSync or None")
        if not isinstance(self.limit_state, LimitState):
            raise ScheduleValidationError("limit state must be LimitState")

    @classmethod
    def neutral(cls) -> Self:
        return cls(
            schedule_slots=tuple(ScheduleSlot.disabled(slot) for slot in range(SCHEDULE_SLOT_COUNT)),
            sleep=SleepState.disabled(),
            wake=WakeState.disabled(),
        )

    def updated_slot(
        self,
        slot: int,
        *,
        enabled: bool | None = None,
        action: ScheduleAction | None = None,
        time: dt_time | None = None,
        repeat_day_mask: int | None = None,
    ) -> Self:
        """Partially update one slot without discarding its other values."""
        validate_slot(slot)
        records = list(self.schedule_slots)
        records[slot] = records[slot].updated(
            enabled=enabled,
            action=action,
            time=time,
            repeat_day_mask=repeat_day_mask,
        )
        return replace(self, schedule_slots=tuple(records))

    def updated_sleep(
        self,
        *,
        enabled: bool | None = None,
        start_brightness: int | None = None,
        duration_minutes: int | None = None,
        remaining_minutes: int | None = None,
    ) -> Self:
        return replace(
            self,
            sleep=self.sleep.updated(
                enabled=enabled,
                start_brightness=start_brightness,
                duration_minutes=duration_minutes,
                remaining_minutes=remaining_minutes,
            ),
        )

    def updated_wake(
        self,
        *,
        enabled: bool | None = None,
        time: dt_time | None = None,
        repeat_day_mask: int | None = None,
        duration_minutes: int | None = None,
        target_brightness: int | None = None,
    ) -> Self:
        return replace(
            self,
            wake=self.wake.updated(
                enabled=enabled,
                time=time,
                repeat_day_mask=repeat_day_mask,
                duration_minutes=duration_minutes,
                target_brightness=target_brightness,
            ),
        )

    def updated_limit(self, *, enabled: bool) -> Self:
        return replace(self, limit_state=self.limit_state.updated(enabled=enabled))

    def to_status_fields(self) -> StatusFields:
        return {
            "clock_sync": None if self.clock_sync is None else self.clock_sync.to_status_fields(),
            "schedule_slots": tuple(record.to_status_fields() for record in self.schedule_slots),
            "sleep": self.sleep.to_status_fields(),
            "wake": self.wake.to_status_fields(),
            "limit_state": self.limit_state.to_status_fields(),
        }
