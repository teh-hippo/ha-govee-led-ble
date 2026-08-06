"""Timer write commands for the Govee BLE coordinator."""

from collections.abc import Callable, Iterable
from datetime import time as dt_time
from typing import Any

from .coordinator_base import (
    SCHEDULE_TIMER_PACKET_TYPE,
    SLEEP_TIMER_PACKET_TYPE,
    WAKEUP_TIMER_PACKET_TYPE,
    _CoordinatorBase,
)
from .protocol import (
    SCHEDULE_TIMER_QUERY,
    SLEEP_TIMER_QUERY,
    WAKEUP_TIMER_QUERY,
    ParsedTimerSchedule,
    Weekday,
    build_timer_schedule,
    build_timer_sleep,
    build_timer_wakeup,
)


class _TimerWriteMixin(_CoordinatorBase):
    """Timer writes that preserve hidden fields and require device read-back."""

    def _require_timer_support(self) -> None:
        if not self.profile.supports_timers:
            raise ValueError(f"{self.model} does not support timers")

    async def _commit_timer_write(
        self,
        packet: bytes,
        snapshot: dict[str, Any],
        *,
        query: bytes,
        domain: int,
        accept: Callable[[], bool],
    ) -> None:
        """Write and read back a timer register, rolling back every optimistic field on failure."""
        succeeded = False
        try:
            for _ in range(2):
                await self.send_command(packet)
                if await self.refresh_query_state(query, domain, accept):
                    succeeded = True
                    self.async_set_updated_data(self.data or {})
                    return
            raise RuntimeError("Timer write was not confirmed by the device")
        finally:
            if not succeeded:
                for field, value in snapshot.items():
                    setattr(self, field, value)

    async def _require_sleep_state(self) -> None:
        if all(
            value is not None
            for value in (
                self.sleep_timer_enabled,
                self.sleep_timer_start_brightness,
                self.sleep_timer_minutes,
            )
        ):
            return
        if not await self.refresh_query_state(
            SLEEP_TIMER_QUERY,
            SLEEP_TIMER_PACKET_TYPE,
            lambda: all(
                value is not None
                for value in (
                    self.sleep_timer_enabled,
                    self.sleep_timer_start_brightness,
                    self.sleep_timer_minutes,
                )
            ),
        ):
            raise RuntimeError("Sleep timer state could not be read")

    async def _require_wakeup_state(self) -> None:
        if all(
            value is not None
            for value in (
                self.wakeup_timer_end_brightness,
                self.wakeup_timer_enabled,
                self.wakeup_timer_time,
                self.wakeup_timer_repeat_days,
                self.wakeup_timer_duration_minutes,
            )
        ):
            return
        if not await self.refresh_query_state(
            WAKEUP_TIMER_QUERY,
            WAKEUP_TIMER_PACKET_TYPE,
            lambda: all(
                value is not None
                for value in (
                    self.wakeup_timer_end_brightness,
                    self.wakeup_timer_enabled,
                    self.wakeup_timer_time,
                    self.wakeup_timer_repeat_days,
                    self.wakeup_timer_duration_minutes,
                )
            ),
        ):
            raise RuntimeError("Wake-up timer state could not be read")

    async def async_set_sleep_timer(self, *, enabled: bool | None = None, minutes: int | None = None) -> None:
        self._require_timer_support()
        async with self._control_lock:
            await self._require_sleep_state()
            snapshot: dict[str, Any] = {
                "sleep_timer_enabled": self.sleep_timer_enabled,
                "sleep_timer_start_brightness": self.sleep_timer_start_brightness,
                "sleep_timer_minutes": self.sleep_timer_minutes,
                "sleep_timer_current_minutes": self.sleep_timer_current_minutes,
            }
            if enabled is not None:
                self.sleep_timer_enabled = enabled
            if minutes is not None:
                self.sleep_timer_minutes = minutes
            assert self.sleep_timer_start_brightness is not None and self.sleep_timer_minutes is not None
            self.sleep_timer_current_minutes = self.sleep_timer_minutes
            expected = (
                bool(self.sleep_timer_enabled),
                self.sleep_timer_start_brightness,
                self.sleep_timer_minutes,
            )
            packet = build_timer_sleep(*expected, self.sleep_timer_minutes)
            await self._commit_timer_write(
                packet,
                snapshot,
                query=SLEEP_TIMER_QUERY,
                domain=SLEEP_TIMER_PACKET_TYPE,
                accept=lambda: (
                    (
                        self.sleep_timer_enabled,
                        self.sleep_timer_start_brightness,
                        self.sleep_timer_minutes,
                    )
                    == expected
                ),
            )

    async def async_set_wakeup_timer(self, *, enabled: bool | None = None, wake_time: dt_time | None = None) -> None:
        self._require_timer_support()
        async with self._control_lock:
            await self._require_wakeup_state()
            snapshot: dict[str, Any] = {
                "wakeup_timer_enabled": self.wakeup_timer_enabled,
                "wakeup_timer_end_brightness": self.wakeup_timer_end_brightness,
                "wakeup_timer_time": self.wakeup_timer_time,
                "wakeup_timer_repeat_days": self.wakeup_timer_repeat_days,
                "wakeup_timer_duration_minutes": self.wakeup_timer_duration_minutes,
            }
            if enabled is not None:
                self.wakeup_timer_enabled = enabled
            if wake_time is not None:
                self.wakeup_timer_time = wake_time
            assert (
                self.wakeup_timer_end_brightness is not None
                and self.wakeup_timer_time is not None
                and self.wakeup_timer_repeat_days is not None
                and self.wakeup_timer_duration_minutes is not None
            )
            expected = (
                bool(self.wakeup_timer_enabled),
                self.wakeup_timer_end_brightness,
                self.wakeup_timer_time,
                self.wakeup_timer_repeat_days,
                self.wakeup_timer_duration_minutes,
            )
            packet = build_timer_wakeup(
                expected[0],
                expected[1],
                expected[2].hour,
                expected[2].minute,
                expected[3],
                expected[4],
            )
            await self._commit_timer_write(
                packet,
                snapshot,
                query=WAKEUP_TIMER_QUERY,
                domain=WAKEUP_TIMER_PACKET_TYPE,
                accept=lambda: (
                    (
                        self.wakeup_timer_enabled,
                        self.wakeup_timer_end_brightness,
                        self.wakeup_timer_time,
                        self.wakeup_timer_repeat_days,
                        self.wakeup_timer_duration_minutes,
                    )
                    == expected
                ),
            )

    async def async_set_schedule_timer(
        self, slot: int, *, on_action: bool, hour: int, minute: int, days: Iterable[Weekday] = ()
    ) -> None:
        self._require_timer_support()
        async with self._control_lock:
            snapshot: dict[str, Any] = {"schedule_timers": list(self.schedule_timers)}
            repeat_days = frozenset(days)
            expected = ParsedTimerSchedule(
                enabled=True, on_action=on_action, hour=hour, minute=minute, repeat_days=repeat_days
            )
            self.schedule_timers[slot] = expected
            packet = build_timer_schedule(slot, True, on_action, hour, minute, repeat_days)
            await self._commit_timer_write(
                packet,
                snapshot,
                query=SCHEDULE_TIMER_QUERY,
                domain=SCHEDULE_TIMER_PACKET_TYPE,
                accept=lambda: self.schedule_timers[slot] == expected,
            )

    async def async_clear_schedule_timer(self, slot: int) -> None:
        self._require_timer_support()
        async with self._control_lock:
            if self.schedule_timers[slot] is None and not await self.refresh_query_state(
                SCHEDULE_TIMER_QUERY,
                SCHEDULE_TIMER_PACKET_TYPE,
                lambda: self.schedule_timers[slot] is not None,
            ):
                raise RuntimeError(f"Schedule timer slot {slot} could not be read")
            snapshot: dict[str, Any] = {"schedule_timers": list(self.schedule_timers)}
            previous = self.schedule_timers[slot]
            assert previous is not None
            self.schedule_timers[slot] = None
            packet = build_timer_schedule(
                slot,
                False,
                previous.on_action,
                previous.hour,
                previous.minute,
                previous.repeat_days,
            )

            def cleared() -> bool:
                record = self.schedule_timers[slot]
                return record is not None and not record.enabled

            await self._commit_timer_write(
                packet,
                snapshot,
                query=SCHEDULE_TIMER_QUERY,
                domain=SCHEDULE_TIMER_PACKET_TYPE,
                accept=cleared,
            )
