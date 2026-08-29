"""Ephemeral latest-only Effect Studio device previews."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any
from uuid import uuid4

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant

from .const import DOMAIN, protocol_model
from .control_arbiter import ControlIntent, PreviewAdmission, async_control_intent
from .effect_active_workspace import ActiveEffectWorkspace, ActiveEffectWorkspaceRepository
from .effect_catalogue import (
    H6199_PALETTE_DIY_APPLY_CODE,
    H6199_WORKSHOP_APPLY_CODE,
    validate_catalogue_template_identity,
)
from .effect_compiler import (
    ActivationMode,
    CompatibilityState,
    CompiledApplication,
    CompiledEffect,
    CompiledMusicProfile,
    CompiledVideoProfile,
    compatibility,
    compile_application,
)
from .effect_deployments import ObservationConfidence
from .effect_diagnostics import DiagnosticOutcome, DiagnosticStage, EffectDiagnosticHistory
from .effect_domain import (
    EffectContent,
    JsonValue,
    LayeredScene,
    LibraryItem,
    PaletteScene,
    SourceKind,
    effect_content_hash,
    effect_content_to_dict,
)
from .effect_identity import EffectDeviceCache
from .effect_limits import MAX_PREVIEW_SEQUENCE
from .effect_protocol_decoder import (
    UnsupportedA3EffectError,
    decode_a3_effect_frames,
)
from .effect_runtime import (
    async_apply_compiled_profile,
    observable_signature_for_state,
    resolve_diy_code,
)
from .effect_scene_defaults import NativeSceneDefault, NativeSceneDefaultRepository
from .effect_scenes import ResolvedScene, resolve_scene, resolve_scene_application_body
from .effect_template_defaults import CatalogueTemplateDefault, CatalogueTemplateDefaultRepository
from .generated_protocol_adapter import build_power
from .h6199_calibration import WHITE_BALANCE_POSITIONS
from .native_scenes import encode_authored_scene_body, resolve_native_scene_body

PREVIEW_VERIFY_DELAY = 0.75
PREVIEW_VERIFY_TIMEOUT = 4.0
PREVIEW_CONNECT_TIMEOUT = 8.0
PREVIEW_CHANNEL_IDLE_TIMEOUT = 300.0

_LOGGER = logging.getLogger(__name__)


class PreviewError(ValueError):
    """Base error for preview contract failures."""


class PreviewSessionNotFoundError(PreviewError):
    pass


class PreviewTargetUnavailableError(PreviewError):
    pass


class PreviewOwnershipError(PreviewError):
    pass


class PreviewSequenceError(PreviewError):
    pass


class PreviewShutdownError(RuntimeError):
    pass


class _PreviewSupersededError(RuntimeError):
    pass


class PreviewPhase(StrEnum):
    QUEUED = "queued"
    WRITING = "writing"
    WRITTEN = "written"
    CONFIRMED = "confirmed"
    UNCONFIRMED = "unconfirmed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PreviewWriteDisposition(StrEnum):
    NOT_STARTED = "not_started"
    MAY_HAVE_STARTED = "may_have_started"
    COMPLETED = "completed"
    UNKNOWN = "unknown"


class PreviewHealthPhase(StrEnum):
    HEALTHY = "healthy"
    CHECKING = "checking"
    DEGRADED = "degraded"


@dataclass(frozen=True, slots=True)
class PreviewStatus:
    session_id: str
    config_entry_id: str
    sequence: int
    phase: PreviewPhase
    content_kind: str
    confidence: ObservationConfidence
    error_code: str | None
    error_message: str | None = None
    write_disposition: PreviewWriteDisposition = PreviewWriteDisposition.UNKNOWN
    persist_default: bool = False
    scene_id: int | None = None
    effect_id: int | None = None
    default_action: str | None = None

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "session_id": self.session_id,
            "config_entry_id": self.config_entry_id,
            "sequence": self.sequence,
            "phase": self.phase.value,
            "content_kind": self.content_kind,
            "confidence": self.confidence.value,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "write_disposition": self.write_disposition.value,
            "persist_default": self.persist_default,
            "scene_id": self.scene_id,
            "effect_id": self.effect_id,
            "default_action": self.default_action,
        }


@dataclass(frozen=True, slots=True)
class PreviewHealthStatus:
    config_entry_id: str
    revision: int
    phase: PreviewHealthPhase
    incident_id: str | None
    error_code: str | None
    error_message: str | None
    write_disposition: PreviewWriteDisposition
    checked_at: str

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "config_entry_id": self.config_entry_id,
            "revision": self.revision,
            "phase": self.phase.value,
            "incident_id": self.incident_id,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "write_disposition": self.write_disposition.value,
            "checked_at": self.checked_at,
        }


@dataclass(frozen=True, slots=True)
class PreviewAcceptance:
    accepted: bool
    session_id: str
    config_entry_id: str
    sequence: int
    reason: str | None = None

    def to_dict(self) -> dict[str, str | int | bool | None]:
        return {
            "accepted": self.accepted,
            "session_id": self.session_id,
            "config_entry_id": self.config_entry_id,
            "sequence": self.sequence,
            "reason": self.reason,
        }


@dataclass(slots=True)
class _PreviewSession:
    owner: object
    listeners: dict[object, Callable[[PreviewStatus], None]] = field(default_factory=dict)
    last_sequence: int = 0
    expiry_handle: asyncio.TimerHandle | None = None
    latest_status: PreviewStatus | None = None
    last_request_key: tuple[str, str, bool] | None = None


@dataclass(frozen=True, slots=True)
class _PreviewRequest:
    session_id: str
    config_entry_id: str
    sequence: int
    updated_at: str
    fingerprint: str
    generation: int
    correlation_id: str
    persist_default: bool
    content_kind: str
    item: LibraryItem | None = None
    diy_code: int | None = None
    scene: ResolvedScene | None = None
    speed_index: int | None = None
    canonical_body: bytes | None = None
    default_action: str | None = None
    admission: PreviewAdmission | None = None


@dataclass(frozen=True, slots=True)
class _HealthTarget:
    expectations: Mapping[str, Any]
    confirmed_confidence: ObservationConfidence


@dataclass(slots=True)
class _DeviceWorker:
    pending: _PreviewRequest | None = None
    active: _PreviewRequest | None = None
    task: asyncio.Task[None] | None = None
    verification_task: asyncio.Task[None] | None = None
    verification_request: _PreviewRequest | None = None
    cancelled_generations: set[int] = field(default_factory=set)
    latest_accepted_generation: int = 0
    closing: bool = False


class _PreviewWriter:
    def __init__(
        self,
        manager: EffectPreviewManager,
        request: _PreviewRequest,
        coordinator: Any,
    ) -> None:
        self._manager = manager
        self._request = request
        self._coordinator = coordinator
        self.started = False
        self.completed = False

    async def begin(self) -> None:
        if not self.started:
            await self._manager._async_begin_transmission(self._request)
            self.started = True

    async def __call__(self, packet: bytes) -> None:
        await self.begin()
        if self._manager._stopping or self._manager._hass.is_stopping:
            raise PreviewShutdownError("Home Assistant is stopping")
        await self._coordinator.async_preview_write(packet)


class EffectPreviewManager:
    """Own connection-bound sessions and one latest-only worker per device."""

    def __init__(
        self,
        hass: HomeAssistant,
        device_cache: EffectDeviceCache,
        scene_defaults: NativeSceneDefaultRepository,
        template_defaults: CatalogueTemplateDefaultRepository,
        diagnostics: EffectDiagnosticHistory,
        *,
        active_workspaces: ActiveEffectWorkspaceRepository | None = None,
        verify_delay: float = PREVIEW_VERIFY_DELAY,
        verify_timeout: float = PREVIEW_VERIFY_TIMEOUT,
        connect_timeout: float = PREVIEW_CONNECT_TIMEOUT,
        channel_idle_timeout: float = PREVIEW_CHANNEL_IDLE_TIMEOUT,
    ) -> None:
        self._hass = hass
        self._device_cache = device_cache
        self._active_workspaces = active_workspaces
        self._scene_defaults = scene_defaults
        self._template_defaults = template_defaults
        self._diagnostics = diagnostics
        self._verify_delay = verify_delay
        self._verify_timeout = verify_timeout
        self._connect_timeout = connect_timeout
        self._channel_idle_timeout = channel_idle_timeout
        self._sessions: dict[str, _PreviewSession] = {}
        self._devices: dict[str, _DeviceWorker] = {}
        self._health: dict[str, PreviewHealthStatus] = {}
        self._health_targets: dict[str, _HealthTarget] = {}
        self._health_listeners: dict[object, Callable[[PreviewHealthStatus], None]] = {}
        self._health_revision = 0
        self._blocked_devices: set[str] = set()
        self._generation = 0
        self._lock = asyncio.Lock()
        self._stopping = False
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._async_handle_hass_stop)

    def open_session(
        self,
        *,
        owner: object,
    ) -> str:
        """Create a channel for direct manager callers and tests."""
        if self._stopping or self._hass.is_stopping:
            raise PreviewShutdownError("Home Assistant is stopping")
        session_id = str(uuid4())
        session = _PreviewSession(_owner_key(owner))
        self._sessions[session_id] = session
        self._schedule_session_expiry(session_id, session)
        return session_id

    def ensure_session(self, session_id: str, owner: object) -> _PreviewSession:
        """Create or attach a same-owner preview channel."""
        if self._stopping or self._hass.is_stopping:
            raise PreviewShutdownError("Home Assistant is stopping")
        owner_key = _owner_key(owner)
        session = self._sessions.get(session_id)
        if session is None:
            session = _PreviewSession(owner_key)
            self._sessions[session_id] = session
        elif session.owner != owner_key:
            raise PreviewOwnershipError("preview channel belongs to another Home Assistant user")
        self._cancel_session_expiry(session)
        if not session.listeners:
            self._schedule_session_expiry(session_id, session)
        return session

    def subscribe(
        self,
        *,
        session_id: str,
        owner: object,
        subscription_id: object,
        listener: Callable[[PreviewStatus], None],
    ) -> Callable[[], None]:
        session = self.ensure_session(session_id, owner)
        self._cancel_session_expiry(session)
        session.listeners[subscription_id] = listener

        def unsubscribe() -> None:
            current = self._sessions.get(session_id)
            if (
                current is not None
                and current.owner == _owner_key(owner)
                and current.listeners.get(subscription_id) is listener
            ):
                current.listeners.pop(subscription_id, None)
                if not current.listeners:
                    self._schedule_session_expiry(session_id, current)

        return unsubscribe

    def subscribe_health(
        self,
        *,
        subscription_id: object,
        listener: Callable[[PreviewHealthStatus], None],
    ) -> Callable[[], None]:
        self._health_listeners[subscription_id] = listener

        def unsubscribe() -> None:
            self._health_listeners.pop(subscription_id, None)

        return unsubscribe

    def health(self, config_entry_id: str) -> PreviewHealthStatus:
        return self._health.get(config_entry_id) or PreviewHealthStatus(
            config_entry_id=config_entry_id,
            revision=0,
            phase=PreviewHealthPhase.HEALTHY,
            incident_id=None,
            error_code=None,
            error_message=None,
            write_disposition=PreviewWriteDisposition.NOT_STARTED,
            checked_at=datetime.now(UTC).isoformat(),
        )

    def require_owner(self, session_id: str, owner: object) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            raise PreviewSessionNotFoundError("preview session was not found")
        if session.owner != _owner_key(owner):
            raise PreviewOwnershipError("preview channel belongs to another Home Assistant user")

    def latest_status(self, session_id: str, owner: object) -> PreviewStatus | None:
        self.require_owner(session_id, owner)
        return self._sessions[session_id].latest_status

    def _cancel_session_expiry(self, session: _PreviewSession) -> None:
        if session.expiry_handle is not None:
            session.expiry_handle.cancel()
            session.expiry_handle = None

    def _schedule_session_expiry(self, session_id: str, session: _PreviewSession) -> None:
        self._cancel_session_expiry(session)

        def expire() -> None:
            session.expiry_handle = None
            self._hass.async_create_task(
                self._async_expire_session(session_id, session.owner),
                name=f"{DOMAIN} expire preview channel",
            )

        session.expiry_handle = asyncio.get_running_loop().call_later(
            self._channel_idle_timeout,
            expire,
        )

    async def _async_expire_session(self, session_id: str, owner: object) -> None:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.owner != owner or session.listeners:
                return
            if any(
                request is not None and request.session_id == session_id
                for worker in self._devices.values()
                for request in (worker.pending, worker.active, worker.verification_request)
            ):
                self._schedule_session_expiry(session_id, session)
                return
            self._sessions.pop(session_id, None)

    async def async_queue_snapshot(
        self,
        *,
        session_id: str,
        owner: object,
        config_entry_id: str,
        sequence: int,
        updated_at: str,
        item: LibraryItem,
        persist_default: bool = False,
    ) -> PreviewAcceptance:
        self.ensure_session(session_id, owner)
        coordinator = self._loaded_coordinator(config_entry_id)
        result = compatibility(item, coordinator.model)
        if result.state is not CompatibilityState.COMPATIBLE:
            raise PreviewError("; ".join(result.reasons))
        if (
            persist_default
            and item.origin.kind is SourceKind.CATALOGUE_TEMPLATE
            and not isinstance(item.content, PaletteScene | LayeredScene)
        ):
            if item.origin.source_id is None:
                raise PreviewError("catalogue-template preview requires a template ID")
            validate_catalogue_template_identity(
                coordinator.model,
                item.origin.source_id,
                item.content,
            )
        diy_code = resolve_diy_code(item)
        fingerprint = _snapshot_fingerprint(coordinator.model, item)
        request = _PreviewRequest(
            session_id=session_id,
            config_entry_id=config_entry_id,
            sequence=sequence,
            updated_at=updated_at,
            fingerprint=fingerprint,
            generation=0,
            correlation_id=str(uuid4()),
            persist_default=persist_default,
            content_kind=str(effect_content_to_dict(item.content)["kind"]),
            item=item,
            diy_code=diy_code,
            default_action=(_snapshot_default_action(item) if persist_default else None),
        )
        return await self._async_accept(owner, request)

    async def async_queue_scene(
        self,
        *,
        session_id: str,
        owner: object,
        config_entry_id: str,
        sequence: int,
        updated_at: str,
        scene_id: int,
        effect_id: int,
        speed_index: int | None,
        persist_default: bool = False,
    ) -> PreviewAcceptance:
        self.ensure_session(session_id, owner)
        coordinator = self._loaded_coordinator(config_entry_id)
        resolved = resolve_scene(coordinator.model, scene_id, effect_id)
        if persist_default and not coordinator.profile.supports_scene_editing:
            raise PreviewError(f"edited native scenes are not supported on {coordinator.model}")
        scene_default = (
            self._scene_defaults.get(
                config_entry_id,
                scene_id,
                effect_id,
            )
            if coordinator.profile.supports_scene_editing
            else None
        )
        try:
            canonical_body, resolved_speed = resolve_scene_application_body(
                resolved.entry,
                scene_default=scene_default,
                speed_index=speed_index,
            )
        except ValueError as exc:
            raise PreviewError(str(exc)) from exc
        request = _PreviewRequest(
            session_id=session_id,
            config_entry_id=config_entry_id,
            sequence=sequence,
            updated_at=updated_at,
            fingerprint=(
                f"scene:{coordinator.model}:{scene_id}:{effect_id}:{resolved_speed}:"
                f"{sha256(canonical_body).hexdigest()}"
            ),
            generation=0,
            correlation_id=str(uuid4()),
            persist_default=persist_default,
            content_kind="scene_builtin",
            scene=resolved,
            speed_index=resolved_speed,
            canonical_body=canonical_body or None,
            default_action=(
                _scene_default_action(
                    resolved.entry,
                    canonical_body,
                    resolved_speed,
                )
                if persist_default
                else None
            ),
        )
        return await self._async_accept(owner, request)

    async def _async_accept(
        self,
        owner: object,
        request: _PreviewRequest,
    ) -> PreviewAcceptance:
        if not 1 <= request.sequence <= MAX_PREVIEW_SEQUENCE:
            raise PreviewSequenceError(f"preview sequence must be from 1 to {MAX_PREVIEW_SEQUENCE}")
        superseded: _PreviewRequest | None = None
        async with self._lock:
            session = self._session_owner_locked(request.session_id, owner)
            if self._stopping or self._hass.is_stopping:
                raise PreviewShutdownError("Home Assistant is stopping")
            if request.config_entry_id in self._blocked_devices:
                raise PreviewTargetUnavailableError("target config entry is unloading")
            request_key = _preview_request_key(request)
            if request.sequence == session.last_sequence:
                if session.last_request_key != request_key:
                    raise PreviewSequenceError("preview sequence cannot identify different desired states")
                latest = session.latest_status
                if (
                    latest is not None
                    and latest.sequence == request.sequence
                    and latest.phase
                    in {
                        PreviewPhase.WRITTEN,
                        PreviewPhase.CONFIRMED,
                    }
                ):
                    return PreviewAcceptance(True, request.session_id, request.config_entry_id, request.sequence)
                if (
                    latest is None
                    or latest.sequence != request.sequence
                    or latest.phase in {PreviewPhase.QUEUED, PreviewPhase.WRITING}
                ) and self._sequence_is_live_locked(request.session_id, request.sequence):
                    return PreviewAcceptance(True, request.session_id, request.config_entry_id, request.sequence)
            if request.sequence < session.last_sequence:
                raise PreviewSequenceError("preview sequence must increase within the session")
            worker = self._devices.setdefault(request.config_entry_id, _DeviceWorker())
            self._generation += 1
            coordinator = self._loaded_coordinator(request.config_entry_id)
            admit_preview = getattr(coordinator, "admit_preview", None)
            request = replace(
                request,
                generation=self._generation,
                admission=admit_preview() if admit_preview is not None else None,
            )
            session.last_sequence = request.sequence
            session.last_request_key = request_key
            superseded = worker.pending
            worker.pending = request
            worker.latest_accepted_generation = request.generation
            if worker.verification_task is not None:
                worker.verification_task.cancel()
                worker.verification_task = None
                worker.verification_request = None
            if worker.task is None or worker.task.done():
                worker.closing = False
                worker.task = self._hass.async_create_task(
                    self._async_device_worker(request.config_entry_id),
                    name=f"{DOMAIN} preview {request.config_entry_id}",
                )
        if superseded is not None:
            self._publish(superseded, PreviewPhase.CANCELLED, error_code="superseded")
        current_health = self.health(request.config_entry_id)
        if current_health.phase is PreviewHealthPhase.DEGRADED:
            self._set_health(
                request.config_entry_id,
                PreviewHealthPhase.CHECKING,
                error_code=current_health.error_code,
                error_message=current_health.error_message,
                write_disposition=current_health.write_disposition,
                incident_id=current_health.incident_id,
            )
        self._publish(request, PreviewPhase.QUEUED)
        return PreviewAcceptance(True, request.session_id, request.config_entry_id, request.sequence)

    def _sequence_is_live_locked(self, session_id: str, sequence: int) -> bool:
        return any(
            request is not None and request.session_id == session_id and request.sequence == sequence
            for worker in self._devices.values()
            for request in (worker.pending, worker.active, worker.verification_request)
        )

    async def async_cancel(
        self,
        *,
        session_id: str,
        owner: object,
        config_entry_id: str | None = None,
    ) -> None:
        self.require_owner(session_id, owner)
        cancelled: list[_PreviewRequest] = []
        async with self._lock:
            self._session_owner_locked(session_id, owner)
            for device_id, worker in self._devices.items():
                if config_entry_id is not None and device_id != config_entry_id:
                    continue
                if worker.pending is not None and worker.pending.session_id == session_id:
                    cancelled.append(worker.pending)
                    worker.cancelled_generations.add(worker.pending.generation)
                    worker.pending = None
                if worker.active is not None and worker.active.session_id == session_id:
                    cancelled.append(worker.active)
                    worker.cancelled_generations.add(worker.active.generation)
                if (
                    worker.verification_request is not None
                    and worker.verification_request.session_id == session_id
                    and worker.verification_task is not None
                ):
                    worker.verification_task.cancel()
                    worker.verification_task = None
                    worker.verification_request = None
        for request in cancelled:
            self._publish(request, PreviewPhase.CANCELLED, error_code="session_cancelled")
            current_health = self.health(request.config_entry_id)
            if current_health.phase is PreviewHealthPhase.CHECKING and current_health.incident_id is not None:
                self._set_health(
                    request.config_entry_id,
                    PreviewHealthPhase.DEGRADED,
                    error_code=current_health.error_code,
                    error_message=current_health.error_message,
                    write_disposition=current_health.write_disposition,
                    incident_id=current_health.incident_id,
                )

    async def async_supersede_device(
        self,
        config_entry_id: str,
        *,
        reason: str = "superseded_by_foreground",
    ) -> None:
        """Cancel queued preview state before an external foreground operation."""
        entry = self._hass.config_entries.async_get_entry(config_entry_id)
        coordinator = None if entry is None else entry.runtime_data
        invalidate = getattr(coordinator, "invalidate_previews", None)
        if invalidate is not None:
            invalidate()

        cancelled: dict[int, _PreviewRequest] = {}
        verification_task: asyncio.Task[None] | None = None
        async with self._lock:
            worker = self._devices.get(config_entry_id)
            self._health_targets.pop(config_entry_id, None)
            if worker is None:
                return
            for request in (worker.pending, worker.verification_request):
                if request is not None:
                    cancelled[request.generation] = request
                    worker.cancelled_generations.add(request.generation)
            if worker.active is not None:
                worker.cancelled_generations.add(worker.active.generation)
            worker.pending = None
            verification_task = worker.verification_task
            if verification_task is not None:
                verification_task.cancel()
                worker.verification_task = None
                worker.verification_request = None
        for request in cancelled.values():
            self._publish(request, PreviewPhase.CANCELLED, error_code=reason)
        if verification_task is not None:
            await asyncio.gather(verification_task, return_exceptions=True)

    async def async_close_session(self, session_id: str, owner: object) -> None:
        self.require_owner(session_id, owner)
        await self.async_cancel(session_id=session_id, owner=owner)
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is not None and session.owner == _owner_key(owner):
                self._cancel_session_expiry(session)
                self._sessions.pop(session_id, None)

    async def async_unload_device(self, config_entry_id: str) -> None:
        cancelled: list[_PreviewRequest] = []
        async with self._lock:
            self._blocked_devices.add(config_entry_id)
            worker = self._devices.get(config_entry_id)
            if worker is None:
                self._health.pop(config_entry_id, None)
                self._health_targets.pop(config_entry_id, None)
                return
            worker.closing = True
            if worker.pending is not None:
                cancelled.append(worker.pending)
                worker.cancelled_generations.add(worker.pending.generation)
                worker.pending = None
            if worker.active is not None:
                cancelled.append(worker.active)
                worker.cancelled_generations.add(worker.active.generation)
            task = worker.task
            verification_task = worker.verification_task
            if verification_task is not None:
                verification_task.cancel()
                worker.verification_task = None
                worker.verification_request = None
        for request in cancelled:
            self._publish(request, PreviewPhase.CANCELLED, error_code="device_unloaded")
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
        if verification_task is not None:
            await asyncio.gather(verification_task, return_exceptions=True)
        async with self._lock:
            self._devices.pop(config_entry_id, None)
            self._health.pop(config_entry_id, None)
            self._health_targets.pop(config_entry_id, None)

    async def async_load_device(self, config_entry_id: str) -> None:
        async with self._lock:
            self._blocked_devices.discard(config_entry_id)

    async def async_shutdown(self) -> None:
        async with self._lock:
            if self._stopping:
                tasks = [
                    task
                    for worker in self._devices.values()
                    for task in (worker.task, worker.verification_task)
                    if task is not None
                ]
            else:
                self._stopping = True
                tasks = []
                for worker in self._devices.values():
                    worker.closing = True
                    if worker.pending is not None:
                        self._publish(worker.pending, PreviewPhase.FAILED, error_code="shutdown_incomplete")
                        worker.cancelled_generations.add(worker.pending.generation)
                        worker.pending = None
                    if worker.verification_task is not None:
                        worker.verification_task.cancel()
                    tasks.extend(task for task in (worker.task, worker.verification_task) if task is not None)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        async with self._lock:
            self._devices.clear()
            for session in self._sessions.values():
                self._cancel_session_expiry(session)
            self._sessions.clear()
            self._health.clear()
            self._health_targets.clear()

    async def async_wait_idle(self, config_entry_id: str) -> None:
        while True:
            async with self._lock:
                worker = self._devices.get(config_entry_id)
                tasks = (
                    []
                    if worker is None
                    else [
                        task for task in (worker.task, worker.verification_task) if task is not None and not task.done()
                    ]
                )
            if not tasks:
                return
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _async_device_worker(self, config_entry_id: str) -> None:
        current_task = asyncio.current_task()
        try:
            while True:
                async with self._lock:
                    worker = self._devices.get(config_entry_id)
                    if worker is None or worker.closing:
                        return
                    request = worker.pending
                    if request is None:
                        return
                    worker.pending = None
                    worker.active = request
                await self._async_execute_request(request)
                async with self._lock:
                    worker = self._devices.get(config_entry_id)
                    if worker is None:
                        return
                    worker.active = None
                    worker.cancelled_generations.discard(request.generation)
        finally:
            async with self._lock:
                worker = self._devices.get(config_entry_id)
                if worker is not None and worker.task is current_task:
                    worker.task = None
                    if worker.pending is not None and not worker.closing:
                        worker.task = self._hass.async_create_task(
                            self._async_device_worker(config_entry_id),
                            name=f"{DOMAIN} preview {config_entry_id}",
                        )

    async def _async_execute_request(self, request: _PreviewRequest) -> None:
        if not await self._async_request_is_current(request):
            self._publish(
                request,
                PreviewPhase.CANCELLED,
                error_code="superseded",
            )
            return
        try:
            coordinator = self._loaded_coordinator(request.config_entry_id)
            compiled = (
                None
                if request.scene is not None
                else compile_application(
                    _required_item(request),
                    coordinator.model,
                    diy_code=request.diy_code,
                )
            )
        except Exception as exc:
            self._diagnostics.record(
                DiagnosticStage.COMPILATION,
                DiagnosticOutcome.FAILED,
                "preview_compilation_failed",
                correlation_id=request.correlation_id,
                config_entry_id=request.config_entry_id,
                details={"error_type": type(exc).__name__, "sequence": request.sequence},
            )
            self._publish(
                request,
                PreviewPhase.FAILED,
                error_code="compilation_failed",
                error_message="The effect could not be prepared. Review its settings before trying again.",
                write_disposition=PreviewWriteDisposition.NOT_STARTED,
            )
            current_health = self.health(request.config_entry_id)
            if current_health.phase is PreviewHealthPhase.CHECKING and current_health.incident_id is not None:
                self._set_health(
                    request.config_entry_id,
                    PreviewHealthPhase.DEGRADED,
                    error_code=current_health.error_code,
                    error_message=current_health.error_message,
                    write_disposition=current_health.write_disposition,
                    incident_id=current_health.incident_id,
                )
            return

        expectations = _verification_expectations(coordinator, request, compiled)
        if not await self._async_request_is_current(request):
            self._publish(
                request,
                PreviewPhase.CANCELLED,
                error_code="superseded",
            )
            return
        if expectations is not None:
            self._health_targets[request.config_entry_id] = _HealthTarget(
                expectations=dict(expectations),
                confirmed_confidence=_confirmed_confidence(coordinator, request, compiled),
            )
        writer: _PreviewWriter | None = None
        try:
            await coordinator.async_preview_preflight(timeout=self._connect_timeout)
            writer = _PreviewWriter(self, request, coordinator)
            if request.scene is not None:
                await coordinator.async_apply_native_scene(
                    request.scene.key,
                    speed_index=request.speed_index,
                    canonical_body=request.canonical_body,
                    before_write=writer.begin,
                    verify=False,
                    intent=ControlIntent.PREVIEW,
                )
            else:
                assert compiled is not None
                if isinstance(compiled, CompiledEffect):
                    packets = list(compiled.packets)
                    power_required = not coordinator.is_on
                    if power_required:
                        packets.insert(0, build_power(True, coordinator.model))
                    await coordinator.async_write_effect_sequence(
                        packets,
                        intent=ControlIntent.PREVIEW,
                        before_write=writer.begin,
                    )
                    if power_required:
                        coordinator.is_on = True
                    _install_effect_state(coordinator, compiled)
                else:
                    async with async_control_intent(coordinator, ControlIntent.PREVIEW):
                        await async_apply_compiled_profile(
                            coordinator,
                            compiled,
                            writer=writer,
                            verify=False,
                        )
            writer.completed = True
            if not await self._async_request_is_current(request):
                raise _PreviewSupersededError
            if self._stopping or self._hass.is_stopping:
                raise PreviewShutdownError("Home Assistant is stopping")
        except _PreviewSupersededError:
            self._health_targets.pop(request.config_entry_id, None)
            self._publish(
                request,
                PreviewPhase.CANCELLED,
                error_code="superseded",
                write_disposition=(
                    PreviewWriteDisposition.COMPLETED
                    if writer is not None and writer.completed
                    else PreviewWriteDisposition.MAY_HAVE_STARTED
                    if writer is not None and writer.started
                    else PreviewWriteDisposition.NOT_STARTED
                ),
            )
            return
        except PreviewShutdownError:
            self._publish(
                request,
                PreviewPhase.FAILED,
                error_code="shutdown_incomplete",
                error_message="Home Assistant stopped before the Live change completed.",
                write_disposition=(
                    PreviewWriteDisposition.COMPLETED
                    if writer is not None and writer.completed
                    else PreviewWriteDisposition.MAY_HAVE_STARTED
                    if writer is not None and writer.started
                    else PreviewWriteDisposition.NOT_STARTED
                ),
            )
            self._set_health(
                request.config_entry_id,
                PreviewHealthPhase.DEGRADED,
                error_code="shutdown_incomplete",
                error_message="Home Assistant stopped before the Live change completed.",
                write_disposition=(
                    PreviewWriteDisposition.COMPLETED
                    if writer is not None and writer.completed
                    else PreviewWriteDisposition.MAY_HAVE_STARTED
                    if writer is not None and writer.started
                    else PreviewWriteDisposition.NOT_STARTED
                ),
            )
            return
        except Exception as exc:
            self._diagnostics.record(
                DiagnosticStage.PACKET_PROGRESS,
                DiagnosticOutcome.FAILED,
                "preview_transport_failed",
                correlation_id=request.correlation_id,
                config_entry_id=request.config_entry_id,
                details={"error_type": type(exc).__name__, "sequence": request.sequence},
            )
            started = writer is not None and writer.started
            self._publish(
                request,
                PreviewPhase.FAILED,
                error_code="transport_failed",
                error_message=(
                    "The light could not be reached before the Live change started."
                    if not started
                    else "The connection stopped while writing. The light may have changed."
                ),
                write_disposition=(
                    PreviewWriteDisposition.MAY_HAVE_STARTED if started else PreviewWriteDisposition.NOT_STARTED
                ),
            )
            self._set_health(
                request.config_entry_id,
                PreviewHealthPhase.DEGRADED,
                error_code="transport_failed",
                error_message=(
                    "The light could not be reached before the Live change started."
                    if not started
                    else "The connection stopped while writing. The light may have changed."
                ),
                write_disposition=(
                    PreviewWriteDisposition.MAY_HAVE_STARTED if started else PreviewWriteDisposition.NOT_STARTED
                ),
            )
            return

        if request.item is not None and self._active_workspaces is not None:
            signature = observable_signature_for_state(
                coordinator,
                mode=_active_mode_for_workspace(coordinator),
                diy_code=coordinator.diy_code,
                effect=coordinator.effect,
            )
            if signature is not None:
                self._active_workspaces.set(
                    ActiveEffectWorkspace(
                        config_entry_id=request.config_entry_id,
                        model=coordinator.model,
                        selector_label=request.item.name,
                        content=_active_workspace_content(
                            request.item.content,
                            compiled,
                        ),
                        origin=request.item.origin,
                        observable_signature=signature,
                        updated_at=request.updated_at,
                        generation=self._active_workspaces.next_generation(),
                    )
                )
        self._invalidate_observed_match(request)
        coordinator.async_update_listeners()

        if request.persist_default:
            try:
                await self._async_persist_built_in_default(request)
            except Exception as exc:
                self._diagnostics.record(
                    DiagnosticStage.API_SERVICE,
                    DiagnosticOutcome.FAILED,
                    "built_in_default_storage_failed",
                    correlation_id=request.correlation_id,
                    config_entry_id=request.config_entry_id,
                    details={"error_type": type(exc).__name__, "sequence": request.sequence},
                )
                self._publish(
                    request,
                    PreviewPhase.FAILED,
                    error_code="storage_failed",
                    error_message="The light changed, but its built-in default could not be saved.",
                    write_disposition=PreviewWriteDisposition.COMPLETED,
                )
                current_health = self.health(request.config_entry_id)
                if current_health.phase is PreviewHealthPhase.CHECKING and current_health.incident_id is not None:
                    self._set_health(
                        request.config_entry_id,
                        PreviewHealthPhase.DEGRADED,
                        error_code=current_health.error_code,
                        error_message=current_health.error_message,
                        write_disposition=current_health.write_disposition,
                        incident_id=current_health.incident_id,
                    )
                return

        if await self._async_request_status_is_live(request):
            self._publish(
                request,
                PreviewPhase.WRITTEN,
                confidence=ObservationConfidence.WRITE_COMPLETED,
                write_disposition=PreviewWriteDisposition.COMPLETED,
            )
        async with self._lock:
            worker = self._devices.get(request.config_entry_id)
            if (
                worker is None
                or worker.closing
                or request.generation != worker.latest_accepted_generation
                or request.generation in worker.cancelled_generations
            ):
                return
            if expectations is not None:
                worker.verification_task = self._hass.async_create_task(
                    self._async_verify(
                        request,
                        coordinator,
                        expectations,
                        _confirmed_confidence(coordinator, request, compiled),
                    ),
                    name=f"{DOMAIN} preview verify {request.config_entry_id}",
                )
                worker.verification_request = request
        if expectations is None:
            self._mark_write_unverified(request)

    def _mark_write_unverified(self, request: _PreviewRequest) -> None:
        self._diagnostics.record_evidence_gap(
            "preview_write_unverified",
            correlation_id=request.correlation_id,
            config_entry_id=request.config_entry_id,
            details={"sequence": request.sequence},
        )
        current_health = self.health(request.config_entry_id)
        if current_health.phase is PreviewHealthPhase.CHECKING and current_health.incident_id is not None:
            self._set_health(
                request.config_entry_id,
                PreviewHealthPhase.DEGRADED,
                error_code=current_health.error_code,
                error_message=current_health.error_message,
                write_disposition=current_health.write_disposition,
                incident_id=current_health.incident_id,
            )

    async def _async_persist_built_in_default(self, request: _PreviewRequest) -> None:
        if (
            request.scene is None
            and request.item is not None
            and request.item.origin.kind is SourceKind.CATALOGUE_TEMPLATE
            and not isinstance(request.item.content, PaletteScene | LayeredScene)
        ):
            item = request.item
            template_id = item.origin.source_id
            if template_id is None:
                raise PreviewError("catalogue-template preview requires a template ID")
            template = validate_catalogue_template_identity(
                self._loaded_coordinator(request.config_entry_id).model,
                template_id,
                item.content,
            )
            if effect_content_hash(item.content) == effect_content_hash(template.content):
                await self._template_defaults.async_delete(request.config_entry_id, template_id)
                return
            await self._template_defaults.async_set(
                CatalogueTemplateDefault(
                    config_entry_id=request.config_entry_id,
                    model=self._loaded_coordinator(request.config_entry_id).model,
                    template_id=template_id,
                    updated_at=request.updated_at,
                    content=item.content,
                )
            )
            return
        if request.scene is not None:
            if request.scene.entry.scene_type == 0 or request.canonical_body is None:
                return
            scene = request.scene
            canonical_body = request.canonical_body
            speed_index = request.speed_index
        else:
            item = _required_item(request)
            if not isinstance(item.content, PaletteScene | LayeredScene):
                return
            scene = resolve_scene(
                item.content.template.sku,
                item.content.template.scene_id,
                item.content.template.effect_id,
            )
            canonical_body, speed_index = encode_authored_scene_body(
                item.content,
                scene.entry,
            )
        catalogue_body, catalogue_speed = resolve_native_scene_body(scene.entry)
        if canonical_body == catalogue_body and speed_index == catalogue_speed:
            await self._scene_defaults.async_delete(
                request.config_entry_id,
                scene.entry.scene_id,
                scene.entry.effect_id,
            )
            return
        await self._scene_defaults.async_set(
            NativeSceneDefault(
                config_entry_id=request.config_entry_id,
                scene_id=scene.entry.scene_id,
                effect_id=scene.entry.effect_id,
                updated_at=request.updated_at,
                canonical_body=canonical_body,
                speed_index=speed_index,
            )
        )

    async def _async_begin_transmission(self, request: _PreviewRequest) -> None:
        async with self._lock:
            if self._stopping or self._hass.is_stopping:
                raise PreviewShutdownError("Home Assistant is stopping")
            worker = self._devices.get(request.config_entry_id)
            if (
                worker is None
                or worker.closing
                or request.generation != worker.latest_accepted_generation
                or request.generation in worker.cancelled_generations
                or (request.admission is not None and not request.admission.is_current)
            ):
                raise _PreviewSupersededError
        self._publish(request, PreviewPhase.WRITING)

    async def _async_verify(
        self,
        request: _PreviewRequest,
        coordinator: Any,
        expectations: Mapping[str, Any],
        confirmed_confidence: ObservationConfidence,
    ) -> None:
        result: bool | None = None
        try:
            await asyncio.sleep(self._verify_delay)
            if not await self._async_verification_is_current(request):
                return
            if not await self._async_verification_is_current(request):
                return
            async with self._lock:
                worker = self._devices.get(request.config_entry_id)
                if worker is None:
                    return
            result = await self._async_observe(
                coordinator,
                expectations,
            )
        except TimeoutError:
            result = None
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._diagnostics.record(
                DiagnosticStage.VERIFICATION,
                DiagnosticOutcome.FAILED,
                "preview_verification_failed",
                correlation_id=request.correlation_id,
                config_entry_id=request.config_entry_id,
                details={"error_type": type(exc).__name__, "sequence": request.sequence},
            )
            result = None
        finally:
            async with self._lock:
                worker = self._devices.get(request.config_entry_id)
                if worker is not None:
                    if worker.verification_task is asyncio.current_task():
                        worker.verification_task = None
                        worker.verification_request = None
        if not await self._async_verification_is_current(request):
            return
        if result is True:
            phase = PreviewPhase.CONFIRMED
            confidence = confirmed_confidence
            error_code = None
            error_message = None
            self._set_health(
                request.config_entry_id,
                PreviewHealthPhase.HEALTHY,
                write_disposition=PreviewWriteDisposition.COMPLETED,
            )
            self._diagnostics.record(
                DiagnosticStage.VERIFICATION,
                DiagnosticOutcome.SUCCEEDED,
                "preview_health_confirmed",
                correlation_id=request.correlation_id,
                config_entry_id=request.config_entry_id,
                details={"sequence": request.sequence},
            )
            if self._active_workspaces is not None:
                workspace = self._active_workspaces.get(request.config_entry_id)
                if (
                    workspace is not None
                    and request.item is not None
                    and workspace.updated_at == request.updated_at
                    and workspace.selector_label == request.item.name
                ):
                    self._active_workspaces.update_confidence(
                        request.config_entry_id,
                        workspace.generation,
                        confidence,
                    )
        elif result is False:
            phase = PreviewPhase.UNCONFIRMED
            confidence = ObservationConfidence.UNKNOWN
            error_code = "device_state_mismatch"
            error_message = "The light accepted the write, but its reported state did not match the requested change."
            self._set_health(
                request.config_entry_id,
                PreviewHealthPhase.DEGRADED,
                error_code=error_code,
                error_message=error_message,
                write_disposition=PreviewWriteDisposition.COMPLETED,
            )
            self._diagnostics.record(
                DiagnosticStage.VERIFICATION,
                DiagnosticOutcome.FAILED,
                "preview_health_mismatch",
                correlation_id=request.correlation_id,
                config_entry_id=request.config_entry_id,
                details={"sequence": request.sequence},
            )
        else:
            self._mark_write_unverified(request)
            return
        self._publish(
            request,
            phase,
            confidence=confidence,
            error_code=error_code,
            error_message=error_message,
            write_disposition=PreviewWriteDisposition.COMPLETED,
        )

    async def _async_verification_is_current(self, request: _PreviewRequest) -> bool:
        async with self._lock:
            worker = self._devices.get(request.config_entry_id)
            return (
                worker is not None
                and not worker.closing
                and request.generation == worker.latest_accepted_generation
                and request.generation not in worker.cancelled_generations
                and (request.admission is None or request.admission.is_current)
            )

    async def _async_request_status_is_live(self, request: _PreviewRequest) -> bool:
        return await self._async_request_is_current(request, require_latest=False)

    async def _async_request_is_current(
        self,
        request: _PreviewRequest,
        *,
        require_latest: bool = True,
    ) -> bool:
        async with self._lock:
            worker = self._devices.get(request.config_entry_id)
            return (
                worker is not None
                and request.generation not in worker.cancelled_generations
                and (not require_latest or request.generation == worker.latest_accepted_generation)
                and (request.admission is None or request.admission.is_current)
            )

    def _invalidate_observed_match(self, request: _PreviewRequest) -> None:
        observed = self._device_cache.get(request.config_entry_id)
        if observed is None or (observed.matched_operation_id is None and observed.active_effect is None):
            return
        self._device_cache.set(
            replace(
                observed,
                observed_at=request.updated_at,
                confidence=ObservationConfidence.UNKNOWN,
                matched_operation_id=None,
                active_effect=None,
            )
        )

    def _loaded_coordinator(self, config_entry_id: str) -> Any:
        entry = self._hass.config_entries.async_get_entry(config_entry_id)
        if (
            entry is None
            or entry.domain != DOMAIN
            or entry.state is not ConfigEntryState.LOADED
            or config_entry_id in self._blocked_devices
        ):
            raise PreviewTargetUnavailableError("target config entry is not loaded")
        return entry.runtime_data

    def _session_owner_locked(self, session_id: str, owner: object) -> _PreviewSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise PreviewSessionNotFoundError("preview session was not found")
        if session.owner != _owner_key(owner):
            raise PreviewOwnershipError("preview channel belongs to another Home Assistant user")
        return session

    def _publish(
        self,
        request: _PreviewRequest,
        phase: PreviewPhase,
        *,
        confidence: ObservationConfidence = ObservationConfidence.UNKNOWN,
        error_code: str | None = None,
        error_message: str | None = None,
        write_disposition: PreviewWriteDisposition = PreviewWriteDisposition.UNKNOWN,
    ) -> None:
        session = self._sessions.get(request.session_id)
        if session is None:
            return
        status = PreviewStatus(
            request.session_id,
            request.config_entry_id,
            request.sequence,
            phase,
            request.content_kind,
            confidence,
            error_code,
            error_message,
            write_disposition,
            request.persist_default,
            *_preview_scene_identity(request),
            request.default_action,
        )
        session.latest_status = status
        for listener in tuple(session.listeners.values()):
            try:
                listener(status)
            except Exception:
                _LOGGER.debug("Preview status listener failed", exc_info=True)

    def _set_health(
        self,
        config_entry_id: str,
        phase: PreviewHealthPhase,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
        write_disposition: PreviewWriteDisposition = PreviewWriteDisposition.UNKNOWN,
        incident_id: str | None = None,
    ) -> PreviewHealthStatus:
        current = self._health.get(config_entry_id)
        self._health_revision += 1
        if phase is PreviewHealthPhase.HEALTHY:
            incident_id = None
            error_code = None
            error_message = None
        elif incident_id is None:
            incident_id = (
                current.incident_id if current is not None and current.incident_id is not None else str(uuid4())
            )
        health = PreviewHealthStatus(
            config_entry_id=config_entry_id,
            revision=self._health_revision,
            phase=phase,
            incident_id=incident_id,
            error_code=error_code,
            error_message=error_message,
            write_disposition=write_disposition,
            checked_at=datetime.now(UTC).isoformat(),
        )
        self._health[config_entry_id] = health
        for listener in tuple(self._health_listeners.values()):
            try:
                listener(health)
            except Exception:
                _LOGGER.debug("Preview health listener failed", exc_info=True)
        return health

    async def async_check_health(self, config_entry_id: str) -> PreviewHealthStatus:
        target = self._health_targets.get(config_entry_id)
        if target is None:
            raise PreviewError("no Live verification target is available for this device")
        current = self.health(config_entry_id)
        async with self._lock:
            worker = self._devices.get(config_entry_id)
            if worker is not None and (worker.pending is not None or worker.active is not None):
                raise PreviewError("a Live change is still in progress")
            generation = worker.latest_accepted_generation if worker is not None else 0
        self._set_health(
            config_entry_id,
            PreviewHealthPhase.CHECKING,
            error_code=current.error_code,
            error_message=current.error_message,
            write_disposition=current.write_disposition,
            incident_id=current.incident_id,
        )
        coordinator = self._loaded_coordinator(config_entry_id)
        result = await self._async_observe(
            coordinator,
            target.expectations,
        )
        if not await self._async_health_check_is_current(
            config_entry_id,
            generation,
        ):
            return self.health(config_entry_id)
        if result is True:
            self._diagnostics.record(
                DiagnosticStage.VERIFICATION,
                DiagnosticOutcome.SUCCEEDED,
                "preview_health_confirmed",
                config_entry_id=config_entry_id,
                details={"attempts": 1, "reconnected": False},
            )
            return self._set_health(
                config_entry_id,
                PreviewHealthPhase.HEALTHY,
                write_disposition=PreviewWriteDisposition.COMPLETED,
            )
        if result is None:
            self._diagnostics.record_evidence_gap(
                "preview_health_unverified",
                config_entry_id=config_entry_id,
                details={"attempts": 1, "result": "silent"},
            )
            return self._set_health(
                config_entry_id,
                current.phase,
                error_code=current.error_code,
                error_message=current.error_message,
                write_disposition=current.write_disposition,
                incident_id=current.incident_id,
            )
        error_code = "device_state_mismatch"
        error_message = "The light replied, but its state did not match the latest Live change."
        self._diagnostics.record(
            DiagnosticStage.VERIFICATION,
            DiagnosticOutcome.FAILED,
            "preview_health_unconfirmed",
            config_entry_id=config_entry_id,
            details={
                "attempts": 1,
                "reconnected": False,
                "result": "mismatch",
            },
        )
        return self._set_health(
            config_entry_id,
            PreviewHealthPhase.DEGRADED,
            error_code=error_code,
            error_message=error_message,
            write_disposition=PreviewWriteDisposition.COMPLETED,
            incident_id=current.incident_id,
        )

    async def _async_observe(
        self,
        coordinator: Any,
        expectations: Mapping[str, Any],
    ) -> bool | None:
        result = await coordinator.async_preview_observe(
            expectations,
            timeout=self._verify_timeout,
        )
        return result if result is None or isinstance(result, bool) else None

    async def _async_health_check_is_current(
        self,
        config_entry_id: str,
        generation: int,
    ) -> bool:
        async with self._lock:
            worker = self._devices.get(config_entry_id)
            return worker is None or (
                worker.latest_accepted_generation == generation and worker.pending is None and worker.active is None
            )

    async def _async_handle_hass_stop(self, _event: Event) -> None:
        await self.async_shutdown()


def _owner_key(owner: object) -> object:
    user_id = getattr(getattr(owner, "user", None), "id", None)
    return ("user", user_id) if isinstance(user_id, str) else owner


def _preview_request_key(request: _PreviewRequest) -> tuple[str, str, bool]:
    return (
        request.config_entry_id,
        request.fingerprint,
        request.persist_default,
    )


def _snapshot_fingerprint(model: str, item: LibraryItem) -> str:
    encoded = json.dumps(
        {
            "model": model,
            "content": effect_content_to_dict(item.content),
        },
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return sha256(encoded).hexdigest()


def _required_item(request: _PreviewRequest) -> LibraryItem:
    if request.item is None:
        raise RuntimeError("snapshot preview request has no effect content")
    return request.item


def _active_workspace_content(
    source: EffectContent,
    compiled: CompiledApplication | None,
) -> EffectContent:
    if not isinstance(compiled, CompiledEffect) or not compiled.upload_packets:
        return source
    try:
        decoded = decode_a3_effect_frames(compiled.upload_packets, compiled.model)
    except UnsupportedA3EffectError:
        return source
    return decoded if type(decoded) is type(source) else source


def _active_mode_for_workspace(coordinator: Any) -> str:
    mode = getattr(coordinator, "active_mode", None)
    if isinstance(mode, str):
        return mode
    if getattr(coordinator, "diy_code", None) is not None:
        return "custom"
    if getattr(coordinator, "effect", None) is not None:
        return "scene"
    if getattr(coordinator, "music_mode", None) not in {None, "off"}:
        return "music"
    if getattr(coordinator, "video_mode", None) not in {None, "off"}:
        return "video"
    return "colour"


def _preview_scene_identity(
    request: _PreviewRequest,
) -> tuple[int | None, int | None]:
    if request.scene is not None:
        return request.scene.entry.scene_id, request.scene.entry.effect_id
    if request.item is not None and isinstance(
        request.item.content,
        PaletteScene | LayeredScene,
    ):
        template = request.item.content.template
        return template.scene_id, template.effect_id
    return None, None


def _scene_default_action(
    scene: Any,
    canonical_body: bytes,
    speed_index: int | None,
) -> str | None:
    if scene.scene_type == 0 or not canonical_body:
        return None
    catalogue_body, catalogue_speed = resolve_native_scene_body(scene)
    return "reset" if canonical_body == catalogue_body and speed_index == catalogue_speed else "set"


def _snapshot_default_action(item: LibraryItem) -> str | None:
    if isinstance(item.content, PaletteScene | LayeredScene):
        scene = resolve_scene(
            item.content.template.sku,
            item.content.template.scene_id,
            item.content.template.effect_id,
        )
        canonical_body, speed_index = encode_authored_scene_body(
            item.content,
            scene.entry,
        )
        return _scene_default_action(
            scene.entry,
            canonical_body,
            speed_index,
        )
    if item.origin.kind is not SourceKind.CATALOGUE_TEMPLATE or item.origin.source_id is None:
        return None
    model = getattr(item.content, "model", "H617A")
    template = validate_catalogue_template_identity(
        model,
        item.origin.source_id,
        item.content,
    )
    return "reset" if effect_content_hash(item.content) == effect_content_hash(template.content) else "set"


def _install_effect_state(coordinator: Any, compiled: CompiledEffect) -> None:
    if compiled.activation_packet is None:
        return
    if compiled.activation_mode is ActivationMode.SCENE:
        coordinator.effect = compiled.expected_effect
        coordinator.diy_code = None
    else:
        coordinator.effect = None
        coordinator.diy_code = compiled.diy_code
    coordinator.music_mode = coordinator.video_mode = "off"


def _verification_expectations(
    coordinator: Any,
    request: _PreviewRequest,
    compiled: CompiledApplication | None,
) -> dict[str, Any] | None:
    if not coordinator.profile.state_readable:
        return None
    if request.scene is not None:
        if coordinator.profile.supports_color_mode_readback:
            return {"is_on": True, "effect": request.scene.key}
        return {"is_on": True}
    if isinstance(compiled, CompiledEffect):
        if compiled.activation_mode is ActivationMode.SCENE:
            if coordinator.profile.supports_color_mode_readback:
                return {"is_on": True, "effect": compiled.expected_effect}
            return {"is_on": True}
        if compiled.content_kind == "workshop":
            return {"is_on": True, "unknown_scene_code": compiled.diy_code}
        if protocol_model(compiled.model) == "H617A":
            return {"is_on": True, "diy_code": compiled.diy_code}
        if compiled.diy_code in {H6199_PALETTE_DIY_APPLY_CODE, H6199_WORKSHOP_APPLY_CODE}:
            return {"is_on": True, "unknown_scene_code": compiled.diy_code}
        return None
    if isinstance(compiled, CompiledMusicProfile):
        expectations: dict[str, Any] = {
            "is_on": True,
            "music_mode": compiled.mode,
        }
        if compiled.model == "H6199":
            expectations.update(
                {
                    "music_sensitivity": compiled.sensitivity,
                    "music_color": compiled.colour,
                }
            )
            if compiled.mode == "rhythm":
                expectations["music_calm"] = compiled.calm
        return expectations
    if isinstance(compiled, CompiledVideoProfile):
        red, blue = WHITE_BALANCE_POSITIONS[compiled.white_balance_position - 1]
        left, top, right, bottom = compiled.relative_brightness
        return {
            "is_on": True,
            "video_mode": compiled.mode,
            "video_full_screen": compiled.full_screen,
            "video_saturation": compiled.saturation,
            "video_sound_effects": compiled.sound_effects,
            "video_sound_effects_softness": compiled.sound_effects_softness,
            "white_balance_red": red,
            "white_balance_blue": blue,
            "relative_brightness": left if len(set(compiled.relative_brightness)) == 1 else None,
            "relative_brightness_left": left,
            "relative_brightness_top": top,
            "relative_brightness_right": right,
            "relative_brightness_bottom": bottom,
            "blank_screen": compiled.blank_screen,
        }
    return None


def _confirmed_confidence(
    coordinator: Any,
    request: _PreviewRequest,
    compiled: CompiledApplication | None,
) -> ObservationConfidence:
    if not coordinator.profile.supports_color_mode_readback and (
        request.scene is not None or isinstance(compiled, CompiledEffect)
    ):
        return ObservationConfidence.WRITE_COMPLETED
    if request.scene is not None or isinstance(compiled, CompiledEffect):
        return ObservationConfidence.ACTIVATION_MATCH
    if isinstance(compiled, CompiledMusicProfile) and protocol_model(compiled.model) == "H617A":
        return ObservationConfidence.MODE_MATCH
    return ObservationConfidence.SETTINGS_MATCH
