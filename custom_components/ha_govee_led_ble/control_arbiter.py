"""Priority arbitration for per-device BLE control transactions."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class ControlIntent(IntEnum):
    """BLE transaction priority."""

    BACKGROUND = 0
    PREVIEW = 1
    APPLY = 2
    USER = 3


@dataclass(frozen=True, slots=True)
class PreviewAdmission:
    """A preview generation invalidated by any later foreground intent."""

    _arbiter: BLEControlArbiter
    generation: int

    @property
    def is_current(self) -> bool:
        return self._arbiter.preview_generation == self.generation


@dataclass(slots=True)
class _Waiter:
    task: asyncio.Task[Any]
    intent: ControlIntent
    sequence: int


class BLEControlArbiter:
    """Serialise one device while preferring higher-priority queued work."""

    def __init__(self) -> None:
        self._condition = asyncio.Condition()
        self._owner: asyncio.Task[Any] | None = None
        self._depth = 0
        self._active_intent: ControlIntent | None = None
        self._intent_stack: list[ControlIntent] = []
        self._waiters: list[_Waiter] = []
        self._sequence = 0
        self._preview_generation = 0

    @property
    def active_intent(self) -> ControlIntent | None:
        return self._active_intent

    @property
    def current_task_intent(self) -> ControlIntent | None:
        try:
            task = asyncio.current_task()
        except RuntimeError:
            return None
        return self._active_intent if task is self._owner else None

    @property
    def preview_generation(self) -> int:
        return self._preview_generation

    def locked(self) -> bool:
        return self._owner is not None

    def admit_preview(self) -> PreviewAdmission:
        self._preview_generation += 1
        return PreviewAdmission(self, self._preview_generation)

    def invalidate_previews(self) -> None:
        self._preview_generation += 1

    @asynccontextmanager
    async def hold(self, intent: ControlIntent, *, wait: bool = True) -> AsyncIterator[bool]:
        acquired = await self._acquire(intent, wait=wait)
        try:
            yield acquired
        finally:
            if acquired:
                await self._release()

    async def __aenter__(self) -> BLEControlArbiter:
        await self._acquire(ControlIntent.USER, wait=True)
        return self

    async def __aexit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        await self._release()

    async def _acquire(self, intent: ControlIntent, *, wait: bool) -> bool:
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("BLE control arbitration requires an asyncio task")
        if self._owner is task:
            self._depth += 1
            self._intent_stack.append(intent)
            self._active_intent = max(self._intent_stack)
            return True
        async with self._condition:
            if intent > ControlIntent.PREVIEW:
                self.invalidate_previews()
            if not wait and (self._owner is not None or self._waiters):
                return False
            self._sequence += 1
            waiter = _Waiter(task, intent, self._sequence)
            self._waiters.append(waiter)
            try:
                await self._condition.wait_for(lambda: self._owner is None and self._next_waiter() is waiter)
            except asyncio.CancelledError:
                self._waiters.remove(waiter)
                self._condition.notify_all()
                raise
            self._waiters.remove(waiter)
            self._owner = task
            self._depth = 1
            self._active_intent = intent
            self._intent_stack = [intent]
            return True

    async def _release(self) -> None:
        task = asyncio.current_task()
        async with self._condition:
            if task is None or self._owner is not task:
                raise RuntimeError("BLE control intent released by a task that does not own it")
            self._depth -= 1
            self._intent_stack.pop()
            if self._depth:
                self._active_intent = max(self._intent_stack)
                return
            self._owner = None
            self._active_intent = None
            self._intent_stack = []
            self._condition.notify_all()

    def _next_waiter(self) -> _Waiter | None:
        if not self._waiters:
            return None
        return min(self._waiters, key=lambda waiter: (-int(waiter.intent), waiter.sequence))


@asynccontextmanager
async def async_control_intent(
    coordinator: Any,
    intent: ControlIntent,
    *,
    wait: bool = True,
) -> AsyncIterator[bool]:
    """Acquire a coordinator intent, falling back to legacy test-double locks."""
    arbiter = getattr(coordinator, "_control_arbiter", None)
    if isinstance(arbiter, BLEControlArbiter):
        async with arbiter.hold(intent, wait=wait) as acquired:
            yield acquired
        return

    lock = coordinator._control_lock
    if not wait and lock.locked():
        yield False
        return
    await lock.acquire()
    try:
        yield True
    finally:
        lock.release()
