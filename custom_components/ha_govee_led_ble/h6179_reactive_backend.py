"""Async ownership and scheduling for H6179 reactive RGB sessions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol
from uuid import uuid4

from .control_arbiter import BLEControlArbiter, ControlIntent, PreviewAdmission
from .h6179_reactive_protocol import (
    H6179_REACTIVE_MIN_UPDATE_INTERVAL,
    RGB,
    H6179ReactiveRoute,
    H6179ReactiveSession,
    ReactiveSessionExpiredError,
    ReactiveSessionResult,
    ReactiveSessionState,
)

H6179_REACTIVE_CONNECT_TIMEOUT = 8.0


class H6179ReactiveCoordinator(Protocol):
    """Coordinator surface required by the reactive backend."""

    model: str
    fw_version: str | None
    _control_arbiter: BLEControlArbiter

    async def async_preview_preflight(self, *, timeout: float = H6179_REACTIVE_CONNECT_TIMEOUT) -> None: ...

    async def async_preview_write(self, packet: bytes) -> None: ...


class ReactiveBackendStopReason(StrEnum):
    """Stable terminal states reported by the backend."""

    REQUESTED = "requested"
    SUPERSEDED = "superseded"
    TIMEOUT = "timeout"
    DISCONNECTED = "disconnected"
    UNLOADED = "unloaded"
    WRITE_FAILED = "write_failed"


@dataclass(frozen=True, slots=True)
class H6179ReactiveStatus:
    """Public state for one config entry."""

    config_entry_id: str
    state: ReactiveSessionState
    session_id: str | None = None
    route: H6179ReactiveRoute | None = None
    coalesced: bool = False
    stop_reason: ReactiveBackendStopReason | None = None

    def to_dict(self) -> dict[str, str | bool | None]:
        return {
            "config_entry_id": self.config_entry_id,
            "state": self.state.value,
            "session_id": self.session_id,
            "route": None if self.route is None else self.route.value,
            "coalesced": self.coalesced,
            "stop_reason": None if self.stop_reason is None else self.stop_reason.value,
        }


class H6179ReactiveBackendError(RuntimeError):
    """Base error raised by the reactive backend."""


class ReactiveTargetUnsupportedError(H6179ReactiveBackendError):
    """Raised when a target is not exactly H6179."""


class ReactiveTargetUnavailableError(H6179ReactiveBackendError):
    """Raised when a config entry is unloaded."""


class ReactiveBackendShutdownError(H6179ReactiveBackendError):
    """Raised after backend shutdown begins."""


class ReactiveSessionNotFoundError(H6179ReactiveBackendError):
    """Raised for a stale or unknown backend session."""


class ReactiveSessionUnauthorizedError(H6179ReactiveBackendError):
    """Raised when another owner attempts to use a session."""


class ReactiveSessionBusyError(H6179ReactiveBackendError):
    """Raised when a config entry already has an active session."""


class ReactiveSessionSupersededError(H6179ReactiveBackendError):
    """Raised after another control intent invalidates the session."""


class ReactiveWriteError(H6179ReactiveBackendError):
    """Raised when a reactive frame cannot be written."""


@dataclass(slots=True)
class _EntrySession:
    config_entry_id: str
    coordinator: H6179ReactiveCoordinator
    owner: object
    session_id: str
    session: H6179ReactiveSession
    admission: PreviewAdmission
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    timer: asyncio.TimerHandle | None = None
    tick_task: asyncio.Task[None] | None = None
    last_write_at: float | None = None
    closing: bool = False


class H6179ReactiveBackend:
    """Own one latest-only reactive session per loaded config entry."""

    def __init__(self, *, connect_timeout: float = H6179_REACTIVE_CONNECT_TIMEOUT) -> None:
        if connect_timeout <= 0:
            raise ValueError("connect_timeout must be positive")
        self._connect_timeout = connect_timeout
        self._entries: dict[str, _EntrySession] = {}
        self._last_status: dict[str, H6179ReactiveStatus] = {}
        self._blocked_entries: set[str] = set()
        self._tasks: set[asyncio.Task[None]] = set()
        self._lock = asyncio.Lock()
        self._stopping = False

    def status(self, config_entry_id: str) -> H6179ReactiveStatus:
        state = self._entries.get(config_entry_id)
        if state is not None:
            return self._active_status(state)
        return self._last_status.get(config_entry_id) or H6179ReactiveStatus(
            config_entry_id=config_entry_id,
            state=ReactiveSessionState.IDLE,
        )

    def is_active(self, config_entry_id: str) -> bool:
        return config_entry_id in self._entries

    async def async_start(
        self,
        *,
        config_entry_id: str,
        owner: object,
        coordinator: H6179ReactiveCoordinator,
        legacy_colour_order: bool = False,
    ) -> H6179ReactiveStatus:
        self._validate_config_entry_id(config_entry_id)
        owner_key = _owner_key(owner)

        async with self._lock:
            self._check_start_locked(config_entry_id, owner_key)
            if coordinator.model != "H6179":
                raise ReactiveTargetUnsupportedError("reactive RGB requires an exact H6179 target")
            admission = coordinator._control_arbiter.admit_preview()
        session = H6179ReactiveSession(
            coordinator.fw_version,
            legacy_colour_order=legacy_colour_order,
        )
        try:
            await coordinator.async_preview_preflight(timeout=self._connect_timeout)
        except Exception as exc:
            raise ReactiveTargetUnavailableError("target H6179 is unavailable") from exc

        async with self._lock:
            self._check_start_locked(config_entry_id, owner_key)
            if not admission.is_current:
                raise ReactiveSessionSupersededError("reactive session was superseded by another control")
            session_id = str(uuid4())
            result = session.start(session_id, asyncio.get_running_loop().time())
            state = _EntrySession(
                config_entry_id=config_entry_id,
                coordinator=coordinator,
                owner=owner_key,
                session_id=session_id,
                session=session,
                admission=admission,
            )
            self._entries[config_entry_id] = state
            status = self._active_status(state, result)
            self._last_status[config_entry_id] = status
            self._schedule_locked(state, result.next_due)
            return status

    async def async_update(
        self,
        *,
        config_entry_id: str,
        session_id: str,
        owner: object,
        rgb_payload: object,
    ) -> H6179ReactiveStatus:
        state = await self._require_session(config_entry_id, session_id, owner)
        async with state.lock:
            self._require_live_state(state)
            await self._require_admission_locked(state)
            rgb = RGB.from_payload(rgb_payload)
            try:
                result = state.session.update(
                    session_id,
                    rgb,
                    asyncio.get_running_loop().time(),
                )
            except ReactiveSessionExpiredError:
                await self._finish_locked(state, ReactiveBackendStopReason.TIMEOUT)
                raise
            if result.frame is not None:
                await self._write_locked(state, result.frame)
            status = self._active_status(state, result)
            self._last_status[config_entry_id] = status
            self._schedule_locked(state, result.next_due)
            return status

    async def async_stop(
        self,
        *,
        config_entry_id: str,
        session_id: str,
        owner: object,
    ) -> H6179ReactiveStatus:
        state = await self._require_session(config_entry_id, session_id, owner)
        async with state.lock:
            self._require_live_state(state)
            state.session.stop(session_id)
            return await self._finish_locked(state, ReactiveBackendStopReason.REQUESTED)

    async def async_supersede_device(self, config_entry_id: str) -> H6179ReactiveStatus:
        state = await self._entry(config_entry_id)
        if state is None:
            return self.status(config_entry_id)
        async with state.lock:
            if not self._is_live(state):
                return self.status(config_entry_id)
            state.session.supersede()
            return await self._finish_locked(state, ReactiveBackendStopReason.SUPERSEDED)

    async def async_disconnect_device(self, config_entry_id: str) -> H6179ReactiveStatus:
        state = await self._entry(config_entry_id)
        if state is None:
            return self.status(config_entry_id)
        async with state.lock:
            if not self._is_live(state):
                return self.status(config_entry_id)
            state.session.disconnect()
            return await self._finish_locked(state, ReactiveBackendStopReason.DISCONNECTED)

    async def async_unload_device(self, config_entry_id: str) -> H6179ReactiveStatus:
        async with self._lock:
            self._blocked_entries.add(config_entry_id)
            state = self._entries.get(config_entry_id)
            if state is None:
                return self.status(config_entry_id)
            state.closing = True
            self._cancel_timer(state)
            tick_task = state.tick_task
        if tick_task is not None and tick_task is not asyncio.current_task():
            await asyncio.gather(tick_task, return_exceptions=True)
        async with state.lock:
            if not self._is_live(state):
                return self.status(config_entry_id)
            state.session.disconnect()
            return await self._finish_locked(state, ReactiveBackendStopReason.UNLOADED)

    async def async_load_device(self, config_entry_id: str) -> None:
        async with self._lock:
            if self._stopping:
                raise ReactiveBackendShutdownError("reactive backend is shutting down")
            self._blocked_entries.discard(config_entry_id)

    async def async_shutdown(self) -> None:
        async with self._lock:
            if self._stopping:
                tasks = list(self._tasks)
                entry_ids: list[str] = []
            else:
                self._stopping = True
                entry_ids = list(self._entries)
                tasks = []
        for config_entry_id in entry_ids:
            await self.async_unload_device(config_entry_id)
        if tasks := [task for task in (*tasks, *self._tasks) if task is not asyncio.current_task()]:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _async_tick(self, config_entry_id: str, session_id: str) -> None:
        try:
            state = await self._entry(config_entry_id)
            if state is None or state.session_id != session_id:
                return
            async with state.lock:
                if not self._is_live(state) or state.closing:
                    return
                await self._require_admission_locked(state)
                result = state.session.tick(asyncio.get_running_loop().time())
                if result.state is ReactiveSessionState.IDLE:
                    await self._finish_locked(state, ReactiveBackendStopReason.TIMEOUT)
                    return
                if result.frame is not None:
                    await self._write_locked(state, result.frame)
                self._last_status[config_entry_id] = self._active_status(state, result)
                self._schedule_locked(state, result.next_due)
        except ReactiveSessionSupersededError, ReactiveWriteError:
            return

    async def _write_locked(self, state: _EntrySession, frame: bytes) -> None:
        try:
            if state.last_write_at is not None:
                delay = state.last_write_at + H6179_REACTIVE_MIN_UPDATE_INTERVAL - asyncio.get_running_loop().time()
                if delay > 0:
                    await asyncio.sleep(delay)
            async with state.coordinator._control_arbiter.hold(ControlIntent.PREVIEW):
                await self._require_admission_locked(state)
                await state.coordinator.async_preview_write(frame)
                await self._require_admission_locked(state)
                state.last_write_at = asyncio.get_running_loop().time()
        except ReactiveSessionSupersededError:
            raise
        except Exception as exc:
            state.session.disconnect()
            await self._finish_locked(state, ReactiveBackendStopReason.WRITE_FAILED)
            raise ReactiveWriteError("reactive frame write failed") from exc

    async def _require_admission_locked(self, state: _EntrySession) -> None:
        if state.admission.is_current:
            return
        state.session.supersede()
        await self._finish_locked(state, ReactiveBackendStopReason.SUPERSEDED)
        raise ReactiveSessionSupersededError("reactive session was superseded by another control")

    async def _require_session(
        self,
        config_entry_id: str,
        session_id: str,
        owner: object,
    ) -> _EntrySession:
        self._validate_config_entry_id(config_entry_id)
        if type(session_id) is not str or not session_id:
            raise ReactiveSessionNotFoundError("reactive session was not found")
        state = await self._entry(config_entry_id)
        if state is None:
            raise ReactiveSessionNotFoundError("reactive session was not found")
        if state.owner != _owner_key(owner):
            raise ReactiveSessionUnauthorizedError("reactive session belongs to another owner")
        if state.session_id != session_id:
            raise ReactiveSessionNotFoundError("reactive session was not found")
        return state

    async def _entry(self, config_entry_id: str) -> _EntrySession | None:
        async with self._lock:
            return self._entries.get(config_entry_id)

    def _require_live_state(self, state: _EntrySession) -> None:
        if not self._is_live(state) or state.closing:
            raise ReactiveSessionNotFoundError("reactive session was not found")

    def _check_start_locked(self, config_entry_id: str, owner: object) -> None:
        if self._stopping:
            raise ReactiveBackendShutdownError("reactive backend is shutting down")
        if config_entry_id in self._blocked_entries:
            raise ReactiveTargetUnavailableError("target config entry is not loaded")
        current = self._entries.get(config_entry_id)
        if current is None:
            return
        if current.owner != owner:
            raise ReactiveSessionUnauthorizedError("reactive session belongs to another owner")
        raise ReactiveSessionBusyError("reactive session is already active")

    def _is_live(self, state: _EntrySession) -> bool:
        return self._entries.get(state.config_entry_id) is state

    async def _finish_locked(
        self,
        state: _EntrySession,
        reason: ReactiveBackendStopReason,
    ) -> H6179ReactiveStatus:
        self._cancel_timer(state)
        status = H6179ReactiveStatus(
            config_entry_id=state.config_entry_id,
            state=ReactiveSessionState.IDLE,
            route=state.session.route,
            stop_reason=reason,
        )
        async with self._lock:
            if self._entries.get(state.config_entry_id) is state:
                self._entries.pop(state.config_entry_id)
            self._last_status[state.config_entry_id] = status
        return status

    def _schedule_locked(self, state: _EntrySession, next_due: float | None) -> None:
        self._cancel_timer(state)
        if next_due is None or state.closing or not self._is_live(state):
            return

        def due() -> None:
            state.timer = None
            if state.closing or not self._is_live(state):
                return
            task = asyncio.create_task(
                self._async_tick(state.config_entry_id, state.session_id),
                name=f"ha_govee_led_ble reactive {state.config_entry_id}",
            )
            state.tick_task = task
            self._tasks.add(task)

            def done(completed: asyncio.Task[None]) -> None:
                self._tasks.discard(completed)
                if state.tick_task is completed:
                    state.tick_task = None

            task.add_done_callback(done)

        state.timer = asyncio.get_running_loop().call_at(next_due, due)

    @staticmethod
    def _cancel_timer(state: _EntrySession) -> None:
        if state.timer is not None:
            state.timer.cancel()
            state.timer = None

    @staticmethod
    def _active_status(
        state: _EntrySession,
        result: ReactiveSessionResult | None = None,
    ) -> H6179ReactiveStatus:
        return H6179ReactiveStatus(
            config_entry_id=state.config_entry_id,
            state=ReactiveSessionState.ACTIVE,
            session_id=state.session_id,
            route=state.session.route,
            coalesced=False if result is None else result.coalesced,
        )

    @staticmethod
    def _validate_config_entry_id(config_entry_id: str) -> None:
        if type(config_entry_id) is not str or not config_entry_id:
            raise ReactiveTargetUnavailableError("config_entry_id must be a non-empty string")


def _owner_key(owner: object) -> object:
    user_id = getattr(getattr(owner, "user", None), "id", None)
    return ("user", user_id) if isinstance(user_id, str) else owner


__all__ = [
    "H6179_REACTIVE_CONNECT_TIMEOUT",
    "H6179ReactiveBackend",
    "H6179ReactiveBackendError",
    "H6179ReactiveCoordinator",
    "H6179ReactiveStatus",
    "ReactiveBackendShutdownError",
    "ReactiveBackendStopReason",
    "ReactiveSessionBusyError",
    "ReactiveSessionNotFoundError",
    "ReactiveSessionSupersededError",
    "ReactiveSessionUnauthorizedError",
    "ReactiveTargetUnavailableError",
    "ReactiveTargetUnsupportedError",
    "ReactiveWriteError",
]
