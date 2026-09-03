"""Tests for protocol-neutral H6179 schedule values."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, time, timedelta, timezone

import pytest

from custom_components.ha_govee_led_ble.h6179_schedule import (
    MAX_REPEAT_DAY_MASK,
    MAX_SLEEP_DURATION_MINUTES,
    MAX_SLEEP_REMAINING_MINUTES,
    MAX_SLEEP_START_BRIGHTNESS,
    MAX_TARGET_BRIGHTNESS,
    MAX_TIMEZONE_OFFSET_MINUTES,
    MAX_WAKE_DURATION_MINUTES,
    MIN_SLEEP_START_BRIGHTNESS,
    MIN_TARGET_BRIGHTNESS,
    MIN_TIMEZONE_OFFSET_MINUTES,
    MIN_WAKE_DURATION_MINUTES,
    NEUTRAL_LIMIT_STATE,
    ClockSync,
    LimitState,
    RepeatDay,
    ScheduleAction,
    ScheduleSlot,
    ScheduleState,
    ScheduleValidationError,
    SleepState,
    WakeState,
    validate_repeat_day_mask,
    validate_schedule_time,
    validate_slot,
    validate_timezone_offset_minutes,
)


def test_clock_sync_is_compact_aware_and_json_ready():
    clock = ClockSync(datetime(2026, 9, 3, 19, 20, 4, tzinfo=timezone(timedelta(hours=10))))

    assert clock.timezone_offset_minutes == 600
    assert clock.to_action_payload() == {
        "local_time": "2026-09-03T19:20:04+10:00",
        "timezone_offset_minutes": 600,
    }


@pytest.mark.parametrize(
    "value, message",
    [
        (datetime(2026, 9, 3, 19, 20), "UTC offset"),
        (datetime(2026, 9, 3, 19, 20, 0, 1, UTC), "second precision"),
        (datetime(2026, 9, 3, tzinfo=timezone(timedelta(hours=14, minutes=1))), "timezone offset"),
        (datetime(2026, 9, 3, tzinfo=timezone(timedelta(hours=-12, minutes=-1))), "timezone offset"),
        (datetime(2026, 9, 3, tzinfo=timezone(timedelta(seconds=1))), "whole minutes"),
    ],
)
def test_clock_sync_rejects_values_the_domain_cannot_represent(value, message):
    with pytest.raises(ScheduleValidationError, match=message):
        ClockSync(value)


def test_validation_apis_accept_boundaries_and_reject_bool():
    validate_slot(0)
    validate_slot(3)
    validate_repeat_day_mask(0)
    validate_repeat_day_mask(MAX_REPEAT_DAY_MASK)
    validate_timezone_offset_minutes(MIN_TIMEZONE_OFFSET_MINUTES)
    validate_timezone_offset_minutes(MAX_TIMEZONE_OFFSET_MINUTES)
    validate_schedule_time(time(23, 59))

    for validator, value in (
        (validate_slot, True),
        (validate_repeat_day_mask, True),
        (validate_timezone_offset_minutes, True),
    ):
        with pytest.raises(ScheduleValidationError):
            validator(value)
    with pytest.raises(ScheduleValidationError, match="minute precision"):
        validate_schedule_time(time(12, 0, 1))
    with pytest.raises(ScheduleValidationError, match="must not include"):
        validate_schedule_time(time(12, tzinfo=UTC))


def test_schedule_slot_validates_fields_and_exposes_entity_payload():
    weekdays = int(RepeatDay.MONDAY | RepeatDay.TUESDAY | RepeatDay.WEDNESDAY | RepeatDay.THURSDAY | RepeatDay.FRIDAY)
    slot = ScheduleSlot(2, True, ScheduleAction.ON, time(6, 30), weekdays)

    assert slot.to_action_payload() == {
        "slot": 2,
        "enabled": True,
        "action": "on",
        "time": "06:30",
        "repeat_day_mask": 0x1F,
    }

    for candidate in (
        {"slot": 4},
        {"enabled": 1},
        {"action": "on"},
        {"time": time(6, 30, 1)},
        {"repeat_day_mask": 0x80},
    ):
        values = {
            "slot": 2,
            "enabled": True,
            "action": ScheduleAction.ON,
            "time": time(6, 30),
            "repeat_day_mask": weekdays,
            **candidate,
        }
        with pytest.raises(ScheduleValidationError):
            ScheduleSlot(**values)


def test_schedule_slot_partial_updates_and_disable_preserve_other_fields():
    original = ScheduleSlot(1, True, ScheduleAction.ON, time(7, 15), int(RepeatDay.MONDAY | RepeatDay.FRIDAY))

    disabled = original.updated(enabled=False)
    moved = disabled.updated(time=time(8, 45))

    assert disabled == ScheduleSlot(1, False, ScheduleAction.ON, time(7, 15), 0x11)
    assert moved == ScheduleSlot(1, False, ScheduleAction.ON, time(8, 45), 0x11)
    assert original.enabled is True


def test_sleep_state_validates_range_and_partial_updates():
    original = SleepState(
        enabled=False,
        start_brightness=61,
        duration_minutes=45,
        remaining_minutes=12,
    )

    enabled = original.updated(enabled=True)
    changed = enabled.updated(duration_minutes=30)
    disabled = changed.updated(enabled=False)

    assert enabled == SleepState(True, 61, 45, 12)
    assert changed.to_action_payload() == {
        "enabled": True,
        "start_brightness": 61,
        "duration_minutes": 30,
    }
    assert changed.to_status_fields() == {
        "enabled": True,
        "start_brightness": 61,
        "duration_minutes": 30,
        "remaining_minutes": 12,
    }
    assert disabled == SleepState(False, 61, 30, 12)
    assert original == SleepState(False, 61, 45, 12)

    for field, value in (
        ("start_brightness", MIN_SLEEP_START_BRIGHTNESS - 1),
        ("start_brightness", MAX_SLEEP_START_BRIGHTNESS + 1),
        ("duration_minutes", MAX_SLEEP_DURATION_MINUTES + 1),
        ("remaining_minutes", MAX_SLEEP_REMAINING_MINUTES + 1),
    ):
        with pytest.raises(ScheduleValidationError):
            original.updated(**{field: value})


def test_wake_state_validates_ranges_and_partial_updates():
    original = WakeState(
        enabled=False,
        time=time(6, 15),
        repeat_day_mask=int(RepeatDay.MONDAY | RepeatDay.FRIDAY),
        duration_minutes=20,
        target_brightness=80,
    )

    enabled = original.updated(enabled=True)
    moved = enabled.updated(time=time(7, 30), target_brightness=90)
    disabled = moved.updated(enabled=False)

    assert enabled == WakeState(True, time(6, 15), 0x11, 20, 80)
    assert moved.to_action_payload() == {
        "enabled": True,
        "time": "07:30",
        "repeat_day_mask": 0x11,
        "duration_minutes": 20,
        "target_brightness": 90,
    }
    assert disabled == WakeState(False, time(7, 30), 0x11, 20, 90)

    for duration in (MIN_WAKE_DURATION_MINUTES - 1, MAX_WAKE_DURATION_MINUTES + 1):
        with pytest.raises(ScheduleValidationError):
            original.updated(duration_minutes=duration)
    for brightness in (MIN_TARGET_BRIGHTNESS - 1, MAX_TARGET_BRIGHTNESS + 1):
        with pytest.raises(ScheduleValidationError):
            original.updated(target_brightness=brightness)


def test_neutral_state_has_four_ordered_disabled_records_and_reversible_limit():
    state = ScheduleState.neutral()

    assert tuple(record.slot for record in state.schedule_slots) == (0, 1, 2, 3)
    assert not any(record.enabled for record in state.schedule_slots)
    assert state.sleep == SleepState.disabled()
    assert state.wake == WakeState.disabled()
    assert state.clock_sync is None
    assert state.limit_state is NEUTRAL_LIMIT_STATE
    assert state.limit_state.to_status_fields() == {"enabled": False}

    limited = state.updated_limit(enabled=True)
    restored = limited.updated_limit(enabled=False)

    assert limited.limit_state == LimitState(enabled=True)
    assert limited.limit_state.to_action_payload() == {"enabled": True}
    assert limited.limit_state.to_status_fields() == {"enabled": True}
    assert restored.limit_state == NEUTRAL_LIMIT_STATE


def test_schedule_state_partial_updates_preserve_unmentioned_records():
    state = ScheduleState.neutral()

    scheduled = state.updated_slot(
        1,
        enabled=True,
        action=ScheduleAction.ON,
        time=time(6, 30),
        repeat_day_mask=int(RepeatDay.MONDAY | RepeatDay.FRIDAY),
    )
    sleeping = scheduled.updated_sleep(
        start_brightness=72,
        duration_minutes=25,
        remaining_minutes=19,
    ).updated_sleep(enabled=True)
    waking = sleeping.updated_wake(
        enabled=True,
        time=time(7),
        repeat_day_mask=int(RepeatDay.SATURDAY | RepeatDay.SUNDAY),
        duration_minutes=30,
        target_brightness=75,
    )

    assert scheduled.schedule_slots[0] is state.schedule_slots[0]
    assert scheduled.schedule_slots[1].enabled is True
    assert sleeping.schedule_slots == scheduled.schedule_slots
    assert sleeping.sleep == SleepState(True, 72, 25, 19)
    assert waking.wake == WakeState(True, time(7), 0x60, 30, 75)
    assert waking.limit_state is NEUTRAL_LIMIT_STATE


def test_schedule_state_rejects_missing_duplicate_and_mistyped_records():
    neutral = ScheduleState.neutral()

    with pytest.raises(ScheduleValidationError, match="exactly 4"):
        ScheduleState(neutral.schedule_slots[:3], neutral.sleep, neutral.wake)
    with pytest.raises(ScheduleValidationError, match="ordered"):
        ScheduleState(
            (neutral.schedule_slots[0], neutral.schedule_slots[0], *neutral.schedule_slots[2:]),
            neutral.sleep,
            neutral.wake,
        )
    with pytest.raises(ScheduleValidationError, match="tuple"):
        ScheduleState(list(neutral.schedule_slots), neutral.sleep, neutral.wake)


def test_domain_objects_are_immutable():
    slot = ScheduleSlot.disabled(0)

    with pytest.raises(FrozenInstanceError):
        slot.enabled = True
