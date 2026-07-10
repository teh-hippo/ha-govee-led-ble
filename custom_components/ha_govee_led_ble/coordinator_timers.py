"""Timer write commands for the Govee BLE coordinator."""

from collections.abc import Iterable
from datetime import time as dt_time
from typing import Any

from .coordinator_base import WAKEUP_END_BRIGHTNESS, _CoordinatorBase
from .protocol import ParsedTimerSchedule, Weekday, build_timer_schedule, build_timer_sleep, build_timer_wakeup


class _TimerWriteMixin(_CoordinatorBase):
    """Optimistic sleep/wake-up/schedule timer writes with rollback on BLE failure."""

    async def _commit_timer_write(self, packet: bytes, snapshot: dict[str, Any]) -> None:
        """Write a timer packet, restoring the snapshotted optimistic fields on BLE failure."""
        try:
            await self.send_command(packet)
        except Exception:
            for field, value in snapshot.items():
                setattr(self, field, value)
            raise
        self.async_set_updated_data(self.data or {})

    async def async_set_sleep_timer(self, *, enabled: bool | None = None, minutes: int | None = None) -> None:
        snapshot: dict[str, Any] = {
            "sleep_timer_enabled": self.sleep_timer_enabled,
            "sleep_timer_minutes": self.sleep_timer_minutes,
        }
        if enabled is not None:
            self.sleep_timer_enabled = enabled
        if minutes is not None:
            self.sleep_timer_minutes = minutes
        packet = build_timer_sleep(bool(self.sleep_timer_enabled), self.brightness_pct, self.sleep_timer_minutes or 0)
        await self._commit_timer_write(packet, snapshot)

    async def async_set_wakeup_timer(self, *, enabled: bool | None = None, wake_time: dt_time | None = None) -> None:
        snapshot: dict[str, Any] = {
            "wakeup_timer_enabled": self.wakeup_timer_enabled,
            "wakeup_timer_time": self.wakeup_timer_time,
        }
        if enabled is not None:
            self.wakeup_timer_enabled = enabled
        if wake_time is not None:
            self.wakeup_timer_time = wake_time
        when = self.wakeup_timer_time or dt_time(0, 0)
        packet = build_timer_wakeup(bool(self.wakeup_timer_enabled), WAKEUP_END_BRIGHTNESS, when.hour, when.minute)
        await self._commit_timer_write(packet, snapshot)

    async def async_set_schedule_timer(
        self, slot: int, *, on_action: bool, hour: int, minute: int, days: Iterable[Weekday] = ()
    ) -> None:
        snapshot: dict[str, Any] = {"schedule_timers": list(self.schedule_timers)}
        repeat_days = frozenset(days)
        self.schedule_timers[slot] = ParsedTimerSchedule(
            enabled=True, on_action=on_action, hour=hour, minute=minute, repeat_days=repeat_days
        )
        packet = build_timer_schedule(slot, True, on_action, hour, minute, repeat_days)
        await self._commit_timer_write(packet, snapshot)

    async def async_clear_schedule_timer(self, slot: int) -> None:
        snapshot: dict[str, Any] = {"schedule_timers": list(self.schedule_timers)}
        self.schedule_timers[slot] = None
        packet = build_timer_schedule(slot, False, False, 0, 0)
        await self._commit_timer_write(packet, snapshot)
