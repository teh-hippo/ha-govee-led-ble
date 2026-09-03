"""H6179 schedule and clock entity-service orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from datetime import time as dt_time
from typing import Protocol

import voluptuous as vol
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import service
from homeassistant.helpers.typing import VolDictType

from .const import DOMAIN
from .control_arbiter import ControlIntent, async_control_intent
from .generated_protocol_adapter import (
    build_h6179_clock_sync,
    build_h6179_limit,
    build_h6179_schedule_slot,
    build_h6179_sleep,
    build_h6179_wake,
)
from .h6179_schedule import (
    MAX_SLEEP_DURATION_MINUTES,
    MAX_SLEEP_START_BRIGHTNESS,
    MAX_TARGET_BRIGHTNESS,
    MAX_WAKE_DURATION_MINUTES,
    MIN_SLEEP_START_BRIGHTNESS,
    MIN_TARGET_BRIGHTNESS,
    MIN_WAKE_DURATION_MINUTES,
    ClockSync,
    RepeatDay,
    ScheduleAction,
    ScheduleState,
    ScheduleValidationError,
    validate_slot,
)

SERVICE_RESYNC_CLOCK = "resync_clock"
SERVICE_CONFIGURE_SCHEDULE_SLOT = "configure_schedule_slot"
SERVICE_DISABLE_SCHEDULE_SLOT = "disable_schedule_slot"
SERVICE_CONFIGURE_SLEEP = "configure_sleep"
SERVICE_DISABLE_SLEEP = "disable_sleep"
SERVICE_CONFIGURE_WAKE = "configure_wake"
SERVICE_DISABLE_WAKE = "disable_wake"
SERVICE_SET_LIMIT_CONTROL = "set_limit_control"

REPEAT_ONE_TIME = "one_time"
REPEAT_EVERY_DAY = "every_day"
REPEAT_SELECTED_DAYS = "selected_days"

_WEEKDAY_MASKS = {
    "monday": int(RepeatDay.MONDAY),
    "tuesday": int(RepeatDay.TUESDAY),
    "wednesday": int(RepeatDay.WEDNESDAY),
    "thursday": int(RepeatDay.THURSDAY),
    "friday": int(RepeatDay.FRIDAY),
    "saturday": int(RepeatDay.SATURDAY),
    "sunday": int(RepeatDay.SUNDAY),
}


def _coerce_integer(value: str | int | float) -> int:
    if isinstance(value, bool):
        raise vol.Invalid("expected an integer")
    return int(value)


_SLOT = vol.All(_coerce_integer, vol.Range(min=1, max=4))
_PERCENTAGE = vol.All(
    _coerce_integer,
    vol.Range(
        min=MIN_SLEEP_START_BRIGHTNESS,
        max=MAX_SLEEP_START_BRIGHTNESS,
    ),
)
_SLEEP_DURATION = vol.All(_coerce_integer, vol.Range(min=0, max=MAX_SLEEP_DURATION_MINUTES))
_WAKE_DURATION = vol.All(
    _coerce_integer,
    vol.Range(min=MIN_WAKE_DURATION_MINUTES, max=MAX_WAKE_DURATION_MINUTES),
)
_WAKE_BRIGHTNESS = vol.All(
    _coerce_integer,
    vol.Range(min=MIN_TARGET_BRIGHTNESS, max=MAX_TARGET_BRIGHTNESS),
)
_REPEAT = vol.In((REPEAT_ONE_TIME, REPEAT_EVERY_DAY, REPEAT_SELECTED_DAYS))
_WEEKDAYS = vol.All([vol.In(tuple(_WEEKDAY_MASKS))], vol.Length(min=1), vol.Unique())

_CONFIGURE_SCHEDULE_SLOT_SCHEMA: VolDictType = {
    vol.Required("slot"): _SLOT,
    vol.Optional("action"): vol.In(tuple(action.value for action in ScheduleAction)),
    vol.Optional("time"): cv.time,
    vol.Optional("repeat"): _REPEAT,
    vol.Optional("weekdays"): _WEEKDAYS,
}
_DISABLE_SCHEDULE_SLOT_SCHEMA: VolDictType = {
    vol.Required("slot"): _SLOT,
}
_CONFIGURE_SLEEP_SCHEMA: VolDictType = {
    vol.Optional("start_brightness"): _PERCENTAGE,
    vol.Optional("duration_minutes"): _SLEEP_DURATION,
}
_CONFIGURE_WAKE_SCHEMA: VolDictType = {
    vol.Optional("time"): cv.time,
    vol.Optional("repeat"): _REPEAT,
    vol.Optional("weekdays"): _WEEKDAYS,
    vol.Optional("duration_minutes"): _WAKE_DURATION,
    vol.Optional("target_brightness"): _WAKE_BRIGHTNESS,
}
_SET_LIMIT_CONTROL_SCHEMA: VolDictType = {
    vol.Required("enabled"): cv.boolean,
}

H6179_ENTITY_SERVICES: tuple[tuple[str, VolDictType, str], ...] = (
    (SERVICE_RESYNC_CLOCK, {}, "async_resync_clock"),
    (
        SERVICE_CONFIGURE_SCHEDULE_SLOT,
        _CONFIGURE_SCHEDULE_SLOT_SCHEMA,
        "async_configure_schedule_slot",
    ),
    (
        SERVICE_DISABLE_SCHEDULE_SLOT,
        _DISABLE_SCHEDULE_SLOT_SCHEMA,
        "async_disable_schedule_slot",
    ),
    (SERVICE_CONFIGURE_SLEEP, _CONFIGURE_SLEEP_SCHEMA, "async_configure_sleep"),
    (SERVICE_DISABLE_SLEEP, {}, "async_disable_sleep"),
    (SERVICE_CONFIGURE_WAKE, _CONFIGURE_WAKE_SCHEMA, "async_configure_wake"),
    (SERVICE_DISABLE_WAKE, {}, "async_disable_wake"),
    (
        SERVICE_SET_LIMIT_CONTROL,
        _SET_LIMIT_CONTROL_SCHEMA,
        "async_set_limit_control",
    ),
)


class H6179ServiceCoordinator(Protocol):
    """Coordinator surface required by H6179 service orchestration."""

    model: str
    h6179_schedule_state: ScheduleState
    h6179_schedule_slot_one_time: tuple[bool, bool, bool, bool]
    h6179_wake_one_time: bool

    async def send_command(self, packet: bytes) -> None: ...

    async def async_refresh_status_domains(
        self,
        domains: frozenset[str],
        *,
        required_domains: frozenset[str] | None = None,
        timeout: float = 2.0,
    ) -> bool: ...


def async_register_h6179_services(hass: HomeAssistant) -> None:
    """Register H6179 entity actions once coordinator state wiring is available."""
    for name, schema, method in H6179_ENTITY_SERVICES:
        service.async_register_platform_entity_service(
            hass,
            DOMAIN,
            name,
            entity_domain=Platform.LIGHT,
            func=method,
            schema=schema,
        )


def _require_h6179(coordinator: H6179ServiceCoordinator) -> None:
    if coordinator.model != "H6179":
        raise ValueError(f"{coordinator.model} has no H6179 schedule controls")


async def _refresh_domain(coordinator: H6179ServiceCoordinator, domain: str) -> bool:
    domains = frozenset({domain})
    return await coordinator.async_refresh_status_domains(
        domains,
        required_domains=domains,
    )


async def _read_domain(coordinator: H6179ServiceCoordinator, domain: str) -> None:
    if not await _refresh_domain(coordinator, domain):
        raise RuntimeError(f"Failed to read H6179 {domain} state")


async def _write_verified(
    coordinator: H6179ServiceCoordinator,
    *,
    packet: bytes,
    domain: str,
    apply_optimistic: Callable[[], None],
    is_verified: Callable[[], bool],
    rollback: Callable[[], None],
) -> None:
    try:
        for _attempt in range(2):
            apply_optimistic()
            await coordinator.send_command(packet)
            if await _refresh_domain(coordinator, domain) and is_verified():
                return
        raise RuntimeError(f"Failed to confirm H6179 {domain} state")
    except Exception:
        rollback()
        raise


def _resolve_repeat(
    current_mask: int,
    current_one_time: bool,
    repeat: str | None,
    weekdays: list[str] | None,
) -> tuple[int, bool]:
    if repeat is None and weekdays is None:
        return current_mask, current_one_time
    if repeat is None:
        repeat = REPEAT_SELECTED_DAYS
    if repeat == REPEAT_ONE_TIME:
        if weekdays is not None:
            raise ScheduleValidationError("one-time schedules cannot include weekdays")
        return 0, True
    if repeat == REPEAT_EVERY_DAY:
        if weekdays is not None:
            raise ScheduleValidationError("every-day schedules cannot include weekdays")
        return 0, False
    if repeat != REPEAT_SELECTED_DAYS or not weekdays:
        raise ScheduleValidationError("selected-day schedules require at least one weekday")
    mask = 0
    try:
        for day in weekdays:
            mask |= _WEEKDAY_MASKS[day]
    except KeyError as err:
        raise ScheduleValidationError(f"unknown weekday: {err.args[0]}") from err
    return mask, False


def _slot_index(slot: int) -> int:
    if not isinstance(slot, int) or isinstance(slot, bool):
        raise ScheduleValidationError("schedule slot must be an integer from 1 to 4")
    slot_index = slot - 1
    validate_slot(slot_index)
    return slot_index


def _schedule_action(action: str | None) -> ScheduleAction | None:
    if action is None:
        return None
    try:
        return ScheduleAction(action)
    except ValueError as err:
        raise ScheduleValidationError("schedule action must be on or off") from err


async def async_resync_clock(
    coordinator: H6179ServiceCoordinator,
    local_time: datetime,
) -> None:
    """Write the Home Assistant local wall clock to an H6179."""
    _require_h6179(coordinator)
    clock = ClockSync(local_time.replace(microsecond=0))
    async with async_control_intent(coordinator, ControlIntent.USER):
        previous = coordinator.h6179_schedule_state
        updated = replace(previous, clock_sync=clock)
        coordinator.h6179_schedule_state = updated
        try:
            await coordinator.send_command(build_h6179_clock_sync(clock))
        except Exception:
            coordinator.h6179_schedule_state = replace(
                coordinator.h6179_schedule_state,
                clock_sync=previous.clock_sync,
            )
            raise


async def async_configure_schedule_slot(
    coordinator: H6179ServiceCoordinator,
    *,
    slot: int,
    action: str | None = None,
    schedule_time: dt_time | None = None,
    repeat: str | None = None,
    weekdays: list[str] | None = None,
) -> None:
    """Enable and partially update one user-facing schedule slot."""
    _require_h6179(coordinator)
    slot_index = _slot_index(slot)
    async with async_control_intent(coordinator, ControlIntent.USER):
        await _read_domain(coordinator, "schedules")
        previous_state = coordinator.h6179_schedule_state
        previous_one_time = coordinator.h6179_schedule_slot_one_time
        current = previous_state.schedule_slots[slot_index]
        repeat_day_mask, one_time = _resolve_repeat(
            current.repeat_day_mask,
            previous_one_time[slot_index],
            repeat,
            weekdays,
        )
        updated_state = previous_state.updated_slot(
            slot_index,
            enabled=True,
            action=_schedule_action(action),
            time=schedule_time,
            repeat_day_mask=repeat_day_mask,
        )
        updated = updated_state.schedule_slots[slot_index]
        one_time_values = list(previous_one_time)
        one_time_values[slot_index] = one_time
        updated_one_time = (
            one_time_values[0],
            one_time_values[1],
            one_time_values[2],
            one_time_values[3],
        )

        def apply_optimistic() -> None:
            coordinator.h6179_schedule_state = replace(
                coordinator.h6179_schedule_state,
                schedule_slots=updated_state.schedule_slots,
            )
            coordinator.h6179_schedule_slot_one_time = updated_one_time

        def rollback() -> None:
            coordinator.h6179_schedule_state = replace(
                coordinator.h6179_schedule_state,
                schedule_slots=previous_state.schedule_slots,
            )
            coordinator.h6179_schedule_slot_one_time = previous_one_time

        await _write_verified(
            coordinator,
            packet=build_h6179_schedule_slot(updated, one_time=one_time),
            domain="schedules",
            apply_optimistic=apply_optimistic,
            is_verified=lambda: (
                coordinator.h6179_schedule_state.schedule_slots[slot_index] == updated
                and coordinator.h6179_schedule_slot_one_time == updated_one_time
            ),
            rollback=rollback,
        )


async def async_disable_schedule_slot(
    coordinator: H6179ServiceCoordinator,
    *,
    slot: int,
) -> None:
    """Disable one schedule slot without discarding its hidden fields."""
    _require_h6179(coordinator)
    slot_index = _slot_index(slot)
    async with async_control_intent(coordinator, ControlIntent.USER):
        await _read_domain(coordinator, "schedules")
        previous_state = coordinator.h6179_schedule_state
        previous_one_time = coordinator.h6179_schedule_slot_one_time
        updated = previous_state.schedule_slots[slot_index].updated(enabled=False)
        updated_state = previous_state.updated_slot(slot_index, enabled=False)

        def apply_optimistic() -> None:
            coordinator.h6179_schedule_state = replace(
                coordinator.h6179_schedule_state,
                schedule_slots=updated_state.schedule_slots,
            )

        def rollback() -> None:
            coordinator.h6179_schedule_state = replace(
                coordinator.h6179_schedule_state,
                schedule_slots=previous_state.schedule_slots,
            )

        await _write_verified(
            coordinator,
            packet=build_h6179_schedule_slot(
                updated,
                one_time=previous_one_time[slot_index],
            ),
            domain="schedules",
            apply_optimistic=apply_optimistic,
            is_verified=lambda: coordinator.h6179_schedule_state.schedule_slots[slot_index] == updated,
            rollback=rollback,
        )


async def async_configure_sleep(
    coordinator: H6179ServiceCoordinator,
    *,
    start_brightness: int | None = None,
    duration_minutes: int | None = None,
) -> None:
    """Enable and partially update sleep mode."""
    _require_h6179(coordinator)
    async with async_control_intent(coordinator, ControlIntent.USER):
        await _read_domain(coordinator, "sleep")
        previous = coordinator.h6179_schedule_state
        updated_state = previous.updated_sleep(
            enabled=True,
            start_brightness=start_brightness,
            duration_minutes=duration_minutes,
        )
        updated = updated_state.sleep

        def apply_optimistic() -> None:
            coordinator.h6179_schedule_state = replace(
                coordinator.h6179_schedule_state,
                sleep=updated,
            )

        def rollback() -> None:
            coordinator.h6179_schedule_state = replace(
                coordinator.h6179_schedule_state,
                sleep=previous.sleep,
            )

        await _write_verified(
            coordinator,
            packet=build_h6179_sleep(updated),
            domain="sleep",
            apply_optimistic=apply_optimistic,
            is_verified=lambda: (
                coordinator.h6179_schedule_state.sleep.to_action_payload() == updated.to_action_payload()
            ),
            rollback=rollback,
        )


async def async_disable_sleep(coordinator: H6179ServiceCoordinator) -> None:
    """Disable sleep mode without discarding its hidden fields."""
    _require_h6179(coordinator)
    async with async_control_intent(coordinator, ControlIntent.USER):
        await _read_domain(coordinator, "sleep")
        previous = coordinator.h6179_schedule_state
        updated_state = previous.updated_sleep(enabled=False)
        updated = updated_state.sleep

        def apply_optimistic() -> None:
            coordinator.h6179_schedule_state = replace(
                coordinator.h6179_schedule_state,
                sleep=updated,
            )

        def rollback() -> None:
            coordinator.h6179_schedule_state = replace(
                coordinator.h6179_schedule_state,
                sleep=previous.sleep,
            )

        await _write_verified(
            coordinator,
            packet=build_h6179_sleep(updated),
            domain="sleep",
            apply_optimistic=apply_optimistic,
            is_verified=lambda: (
                coordinator.h6179_schedule_state.sleep.to_action_payload() == updated.to_action_payload()
            ),
            rollback=rollback,
        )


async def async_configure_wake(
    coordinator: H6179ServiceCoordinator,
    *,
    wake_time: dt_time | None = None,
    repeat: str | None = None,
    weekdays: list[str] | None = None,
    duration_minutes: int | None = None,
    target_brightness: int | None = None,
) -> None:
    """Enable and partially update wake mode."""
    _require_h6179(coordinator)
    async with async_control_intent(coordinator, ControlIntent.USER):
        await _read_domain(coordinator, "wake")
        previous_state = coordinator.h6179_schedule_state
        previous_one_time = coordinator.h6179_wake_one_time
        current = previous_state.wake
        repeat_day_mask, one_time = _resolve_repeat(
            current.repeat_day_mask,
            previous_one_time,
            repeat,
            weekdays,
        )
        updated_state = previous_state.updated_wake(
            enabled=True,
            time=wake_time,
            repeat_day_mask=repeat_day_mask,
            duration_minutes=duration_minutes,
            target_brightness=target_brightness,
        )
        updated = updated_state.wake

        def apply_optimistic() -> None:
            coordinator.h6179_schedule_state = replace(
                coordinator.h6179_schedule_state,
                wake=updated,
            )
            coordinator.h6179_wake_one_time = one_time

        def rollback() -> None:
            coordinator.h6179_schedule_state = replace(
                coordinator.h6179_schedule_state,
                wake=previous_state.wake,
            )
            coordinator.h6179_wake_one_time = previous_one_time

        await _write_verified(
            coordinator,
            packet=build_h6179_wake(updated, one_time=one_time),
            domain="wake",
            apply_optimistic=apply_optimistic,
            is_verified=lambda: (
                coordinator.h6179_schedule_state.wake == updated and coordinator.h6179_wake_one_time is one_time
            ),
            rollback=rollback,
        )


async def async_disable_wake(coordinator: H6179ServiceCoordinator) -> None:
    """Disable wake mode without discarding its hidden fields."""
    _require_h6179(coordinator)
    async with async_control_intent(coordinator, ControlIntent.USER):
        await _read_domain(coordinator, "wake")
        previous_state = coordinator.h6179_schedule_state
        previous_one_time = coordinator.h6179_wake_one_time
        updated_state = previous_state.updated_wake(enabled=False)
        updated = updated_state.wake

        def apply_optimistic() -> None:
            coordinator.h6179_schedule_state = replace(
                coordinator.h6179_schedule_state,
                wake=updated,
            )

        def rollback() -> None:
            coordinator.h6179_schedule_state = replace(
                coordinator.h6179_schedule_state,
                wake=previous_state.wake,
            )

        await _write_verified(
            coordinator,
            packet=build_h6179_wake(updated, one_time=previous_one_time),
            domain="wake",
            apply_optimistic=apply_optimistic,
            is_verified=lambda: coordinator.h6179_schedule_state.wake == updated,
            rollback=rollback,
        )


async def async_set_limit_control(
    coordinator: H6179ServiceCoordinator,
    *,
    enabled: bool,
) -> None:
    """Set the experimental H6179 limit-control flag."""
    _require_h6179(coordinator)
    async with async_control_intent(coordinator, ControlIntent.USER):
        await _read_domain(coordinator, "limit")
        previous = coordinator.h6179_schedule_state
        updated_state = previous.updated_limit(enabled=enabled)
        updated = updated_state.limit_state

        def apply_optimistic() -> None:
            coordinator.h6179_schedule_state = replace(
                coordinator.h6179_schedule_state,
                limit_state=updated,
            )

        def rollback() -> None:
            coordinator.h6179_schedule_state = replace(
                coordinator.h6179_schedule_state,
                limit_state=previous.limit_state,
            )

        await _write_verified(
            coordinator,
            packet=build_h6179_limit(updated),
            domain="limit",
            apply_optimistic=apply_optimistic,
            is_verified=lambda: coordinator.h6179_schedule_state.limit_state == updated,
            rollback=rollback,
        )
