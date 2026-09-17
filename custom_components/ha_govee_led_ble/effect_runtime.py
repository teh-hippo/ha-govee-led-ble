"""Coordinator-owned Effect Studio deployment transactions."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Any
from uuid import UUID, uuid4

from .const import MUSIC_MODE_SLUGS, ModelProfile, ReadDomain, get_profile
from .control_arbiter import ControlIntent, async_control_intent
from .coordinator import GoveeBLECoordinator
from .effect_active_workspace import (
    ActiveEffectWorkspace,
    ActiveEffectWorkspaceRepository,
)
from .effect_compiler import (
    ActivationMode,
    CompiledApplication,
    CompiledEffect,
    CompiledMusicProfile,
    CompiledVideoProfile,
    compile_application,
    validate_compiled_geometry,
)
from .effect_compiler import resolve_diy_code as resolve_diy_code
from .effect_deployments import (
    DeploymentPhase,
    DeploymentRecord,
    EffectDeploymentRepository,
    ObservationConfidence,
    PriorControlState,
)
from .effect_domain import (
    BuiltinScene,
    EffectContent,
    LayeredEffect,
    LayeredScene,
    LibraryItem,
    PaletteDiyEffect,
    PaletteScene,
    WorkshopEffect,
)
from .effect_identity import ActiveEffectHint, EffectDeviceCache, ObservedDeviceState
from .effect_protocol_decoder import (
    UnsupportedA3EffectError,
    decode_a3_effect_frames,
)
from .generated_protocol_adapter import (
    build_black_border,
    build_blank_screen,
    build_power,
    build_relative_brightness,
    build_white_balance,
)
from .music_commands import prepare_music_profile_writes
from .music_semantics import capture_music_parameters, music_variant
from .native_profile_controls import (
    ProfileWriter,
    _send_video_setting,
    apply_active_video_mode,
    apply_black_border,
    apply_blank_screen,
    apply_relative_brightness,
    apply_white_balance,
    async_require_video_controls,
    prepare_video_mode,
)
from .scenes import canonical_scene_key, resolve_scene_identity, scene_code_is_ambiguous
from .video_applicability import requested_video_controls, require_video_controls, require_video_mode

ACTIVATION_ATTEMPTS = 2
VERIFICATION_ATTEMPTS = 2

_LOGGER = logging.getLogger(__name__)


async def async_apply_compiled_profile(
    coordinator: GoveeBLECoordinator,
    compiled: CompiledMusicProfile | CompiledVideoProfile,
    *,
    writer: ProfileWriter | None = None,
    verify: bool = True,
    progress: Callable[[int], Awaitable[None]] | None = None,
) -> None:
    if isinstance(compiled, CompiledMusicProfile):
        if coordinator.model != compiled.model:
            raise ValueError("music profile target does not match coordinator")
        validate_compiled_geometry(compiled, coordinator.profile)
        writes = prepare_music_profile_writes(
            compiled.model,
            compiled.mode,
            compiled.sensitivity,
            compiled.colour,
            compiled.calm,
            compiled.parameters,
            profile=coordinator.profile,
            palette=compiled.palette,
        )
        if tuple(packet for packet, _ in writes) != compiled.packets:
            raise ValueError("Music request changed since compilation; refresh and retry")

        await coordinator.async_write_music_sequence(
            writes,
            mode_code=MUSIC_MODE_SLUGS[compiled.mode],
            physical_ic_count=compiled.physical_ic_count,
            intent=ControlIntent.APPLY,
            writer=writer,
        )
        if progress is not None:
            await progress(1)
            if len(writes) > 2:
                await progress(2)
        return

    profile = coordinator.profile
    await async_require_video_controls(coordinator, requested_video_controls(compiled))
    require_video_mode(coordinator.profile, coordinator)
    underlying_writer = writer
    requested_controls = requested_video_controls(compiled)

    async def guarded_writer(
        packet: bytes,
        *,
        write_guard: Callable[[], None] | None = None,
        state_values: Mapping[str, Any] | None = None,
        expected_values: Mapping[str, Any] | None = None,
    ) -> None:
        await _send_video_setting(
            coordinator,
            packet,
            requested_controls,
            writer=underlying_writer,
            write_guard=write_guard,
            state_values=state_values,
            expected_values=expected_values,
        )

    writer = guarded_writer
    omitted_mode_fields = tuple(
        field
        for field, supported in (
            ("full_screen", profile.supports_video_capture_region),
            ("saturation", profile.supports_video_saturation),
            ("sound_effects", profile.supports_video_sound_effects),
            ("sound_effects_softness", profile.supports_video_sound_effects),
        )
        if supported and getattr(compiled, field) is None
    )
    if omitted_mode_fields:
        baselines = {
            f"video_{field}": coordinator._field_revisions.get(f"video_{field}", 0) for field in omitted_mode_fields
        }
        if not await coordinator.refresh_state() or any(
            coordinator._field_revisions.get(field, 0) <= baseline for field, baseline in baselines.items()
        ):
            raise ValueError("Cannot preserve omitted video settings without fresh readback")
        await async_require_video_controls(coordinator, requested_video_controls(compiled))
    if compiled.blank_screen is not None and compiled.blank_screen_policy is None:
        baselines = {
            field: coordinator._field_revisions.get(field, 0)
            for field in (
                "blank_screen_detection",
                "blank_screen_low_brightness_duration_seconds",
                "blank_screen_same_tone_duration_seconds",
            )
        }
        # Preparation must fail before even the mode/power write. The shared
        # toggle writer refreshes again and guards its own physical boundary.
        if not await coordinator.refresh_state(refresh_display_settings=frozenset({"blank_screen"})) or any(
            coordinator._field_revisions.get(field, 0) <= revision for field, revision in baselines.items()
        ):
            raise ValueError("Blank-screen policy state has not been read freshly; refresh the device first")
    # Validate every packet before changing state or sending the first command.
    mode_values = {
        field: getattr(compiled, field)
        for field in ("full_screen", "saturation", "sound_effects", "sound_effects_softness")
        if getattr(compiled, field) is not None
    }
    prepare_video_mode(coordinator, mode=compiled.mode, requested_values=mode_values)
    if compiled.white_balance_wire is not None:
        build_white_balance(
            compiled.white_balance_wire[0],
            compiled.white_balance_wire[1] if len(compiled.white_balance_wire) == 2 else None,
            coordinator.model,
        )
    if compiled.relative_brightness is not None:
        values = compiled.relative_brightness
        build_relative_brightness(
            values[0],
            values[1],
            values[2],
            values[3],
            coordinator.model,
            values[4] if len(values) == 6 else None,
            values[5] if len(values) == 6 else None,
        )
    if compiled.blank_screen is not None:
        detection, low_duration, same_duration = (
            compiled.blank_screen_policy
            if compiled.blank_screen_policy is not None
            else (
                coordinator.blank_screen_detection,
                coordinator.blank_screen_low_brightness_duration_seconds,
                coordinator.blank_screen_same_tone_duration_seconds,
            )
        )
        if detection is None or low_duration is None or same_duration is None:
            raise ValueError("Blank-screen policy state has not been read; refresh the device first")
        build_blank_screen(compiled.blank_screen, coordinator.model, detection, low_duration, same_duration)
    if compiled.black_border is not None:
        build_black_border(compiled.black_border, coordinator.model)
    await apply_active_video_mode(
        coordinator,
        mode=compiled.mode,
        requested_values=mode_values,
        writer=writer,
        verify=verify,
    )
    completed = 1
    if progress is not None:
        await progress(completed)

    if compiled.white_balance_wire is not None:
        await apply_white_balance(coordinator, compiled.white_balance_wire, writer=writer, verify=verify)
        completed += 1
        if progress is not None:
            await progress(completed)

    if compiled.relative_brightness is not None:
        await apply_relative_brightness(coordinator, compiled.relative_brightness, writer=writer, verify=verify)
        completed += 1
        if progress is not None:
            await progress(completed)

    if compiled.blank_screen is not None:
        policy_options: dict[str, Any] = (
            {"policy": compiled.blank_screen_policy} if compiled.blank_screen_policy is not None else {}
        )
        await apply_blank_screen(
            coordinator,
            compiled.blank_screen,
            writer=writer,
            verify=verify,
            **policy_options,
        )
        completed += 1
        if progress is not None:
            await progress(completed)

    if compiled.black_border is not None:
        await apply_black_border(coordinator, compiled.black_border, writer=writer, verify=verify)
        completed += 1
        if progress is not None:
            await progress(completed)


class EffectDeploymentEngine:
    """Apply immutable definitions through one coordinator transaction."""

    def __init__(
        self,
        deployments: EffectDeploymentRepository,
        device_cache: EffectDeviceCache | None = None,
        active_workspaces: ActiveEffectWorkspaceRepository | None = None,
    ) -> None:
        self._deployments = deployments
        self._device_cache = device_cache
        self._active_workspaces = active_workspaces
        self._operation_locks_guard = asyncio.Lock()
        self._operation_locks: dict[UUID, asyncio.Lock] = {}
        self._operation_lock_users: dict[UUID, int] = {}

    async def _apply_library_item(
        self,
        coordinator: GoveeBLECoordinator,
        item: LibraryItem,
        *,
        config_entry_id: str,
        updated_at: str,
        diy_code: int | None,
        operation_id: UUID | None,
        source_kind: str,
    ) -> tuple[CompiledApplication, DeploymentRecord]:
        resolved_diy_code = resolve_diy_code(item, diy_code, model=coordinator.model)
        compiled = compile_application(item, coordinator.model, diy_code=resolved_diy_code, profile=coordinator.profile)
        if isinstance(compiled, CompiledVideoProfile):
            await async_require_video_controls(
                coordinator, requested_video_controls(compiled), intent=ControlIntent.APPLY
            )
            require_video_mode(coordinator.profile, coordinator)
        record = self._new_record(
            compiled,
            config_entry_id=config_entry_id,
            updated_at=updated_at,
            operation_id=operation_id,
            source_item=item,
            source_kind=source_kind,
        )
        result = await self._async_apply(coordinator, compiled, record)
        return compiled, result

    async def async_apply_saved(
        self,
        coordinator: GoveeBLECoordinator,
        item: LibraryItem,
        *,
        config_entry_id: str,
        updated_at: str,
        diy_code: int | None = None,
        operation_id: UUID | None = None,
    ) -> DeploymentRecord:
        _compiled, result = await self._apply_library_item(
            coordinator,
            item,
            config_entry_id=config_entry_id,
            updated_at=updated_at,
            diy_code=diy_code,
            operation_id=operation_id,
            source_kind="saved_effect",
        )
        if result.phase is DeploymentPhase.CONFIRMED:
            if self._active_workspaces is not None:
                self._active_workspaces.clear(config_entry_id)
            self._publish_coordinator_state(coordinator)
        return result

    async def async_apply_snapshot(
        self,
        coordinator: GoveeBLECoordinator,
        item: LibraryItem,
        *,
        config_entry_id: str,
        updated_at: str,
        diy_code: int | None = None,
        operation_id: UUID | None = None,
    ) -> DeploymentRecord:
        compiled, result = await self._apply_library_item(
            coordinator,
            item,
            config_entry_id=config_entry_id,
            updated_at=updated_at,
            diy_code=diy_code,
            operation_id=operation_id,
            source_kind="snapshot",
        )
        if result.phase is DeploymentPhase.CONFIRMED:
            if self._active_workspaces is not None:
                signature = observable_signature_for_compiled(compiled)
                if signature is not None:
                    self._active_workspaces.set(
                        ActiveEffectWorkspace(
                            config_entry_id=config_entry_id,
                            model=coordinator.model,
                            selector_label=item.name,
                            content=_active_workspace_content(
                                item.content,
                                compiled,
                            ),
                            origin=item.origin,
                            observable_signature=signature,
                            updated_at=updated_at,
                            generation=self._active_workspaces.next_generation(),
                            confidence=result.verification_confidence,
                        )
                    )
            self._publish_coordinator_state(coordinator)
        return result

    async def async_reconcile(
        self,
        coordinator: GoveeBLECoordinator,
        *,
        config_entry_id: str,
        observed_at: str,
    ) -> ObservedDeviceState:
        async with async_control_intent(
            coordinator,
            ControlIntent.BACKGROUND,
        ):
            refreshed = await self._async_refresh_for_reconciliation(coordinator)
            return self.reconcile_current(
                coordinator,
                config_entry_id=config_entry_id,
                observed_at=observed_at,
                refreshed=refreshed,
            )

    def reconcile_current(
        self,
        coordinator: GoveeBLECoordinator,
        *,
        config_entry_id: str,
        observed_at: str,
        refreshed: bool,
        matched_record: DeploymentRecord | None = None,
    ) -> ObservedDeviceState:
        return self._reconcile_observation(
            coordinator,
            config_entry_id=config_entry_id,
            observed_at=observed_at,
            refreshed=refreshed,
            matched_record=matched_record,
        )

    def _new_record(
        self,
        compiled: CompiledApplication,
        *,
        config_entry_id: str,
        updated_at: str,
        operation_id: UUID | None,
        source_item: LibraryItem,
        source_kind: str,
    ) -> DeploymentRecord:
        if isinstance(compiled, CompiledEffect):
            target_mode = compiled.activation_mode.value
            target_effect = compiled.expected_effect
            evidence_codes = compiled.evidence_codes
        else:
            target_mode = "music" if isinstance(compiled, CompiledMusicProfile) else "video"
            target_effect = None
            evidence_codes = ()
        return DeploymentRecord(
            operation_id=operation_id or uuid4(),
            config_entry_id=config_entry_id,
            diy_code=compiled.diy_code,
            content_kind=compiled.content_kind,
            phase=DeploymentPhase.COMPILING,
            compiler_version=compiled.compiler_version,
            artifact_sha256=compiled.artifact_sha256,
            updated_at=updated_at,
            target_mode=target_mode,
            target_effect=target_effect,
            target_model=compiled.model,
            observable_signature=observable_signature_for_compiled(compiled),
            evidence_codes=evidence_codes,
            source_kind=source_kind,
            selector_label=source_item.name,
            source_origin_kind=source_item.origin.kind.value,
            source_origin_id=source_item.origin.source_id,
            source_content_hash=source_item.content_hash,
            item_id=source_item.id if source_kind == "saved_effect" else None,
            item_version=source_item.version if source_kind == "saved_effect" else None,
            progress_total=compiled.progress_total,
        )

    async def _async_apply(
        self,
        coordinator: GoveeBLECoordinator,
        compiled: CompiledApplication,
        record: DeploymentRecord,
    ) -> DeploymentRecord:
        async with self._operation_lock(record.operation_id):
            return await self._async_apply_serialised(coordinator, compiled, record)

    async def _async_apply_serialised(
        self,
        coordinator: GoveeBLECoordinator,
        compiled: CompiledApplication,
        record: DeploymentRecord,
    ) -> DeploymentRecord:
        if existing := self._deployments.get_optional(record.operation_id):
            if (
                existing.config_entry_id == record.config_entry_id
                and existing.artifact_sha256 == record.artifact_sha256
                and existing.phase in {DeploymentPhase.CONFIRMED, DeploymentPhase.APPLIED}
            ):
                return existing
            raise RuntimeError(
                f"deployment operation {record.operation_id} already exists in phase {existing.phase.value}"
            )
        current = record
        lock_acquired = False
        try:
            async with async_control_intent(
                coordinator,
                ControlIntent.APPLY,
            ):
                lock_acquired = True
                # APPLY excludes other control owners; queries never increment this counter.
                write_baseline = getattr(coordinator, "control_write_attempts", None)

                def writes_attempted() -> bool | None:
                    if type(write_baseline) is not int:
                        return None
                    return coordinator.control_write_attempts != write_baseline

                try:
                    # Admit APPLY before persistence yields, so later previews remain newer.
                    await self._deployments.async_put(record, expected_version=None)
                    if isinstance(compiled, CompiledVideoProfile):
                        require_video_mode(coordinator.profile, coordinator)
                        require_video_controls(coordinator.profile, coordinator, requested_video_controls(compiled))
                    refreshed = await self._async_prepare_prior_state(coordinator, compiled)
                    validate_compiled_geometry(compiled, coordinator.profile)
                    self._reconcile_observation(
                        coordinator,
                        config_entry_id=record.config_entry_id,
                        observed_at=record.updated_at,
                        refreshed=refreshed,
                    )
                    prior_state = self._capture_prior_state(
                        coordinator,
                        config_entry_id=current.config_entry_id,
                    )
                    if isinstance(compiled, CompiledVideoProfile):
                        prior_state = replace(
                            prior_state,
                            video_restore_controls=tuple(
                                sorted(
                                    requested_video_controls(compiled)
                                    | ({"blank_screen_policy"} if compiled.blank_screen_policy is not None else set())
                                )
                            ),
                        )
                    else:
                        prior_state = replace(prior_state, video_restore_controls=())
                    next_record = replace(current, prior_state=prior_state)
                    await self._deployments.async_put(next_record, expected_version=None)
                    current = next_record

                    next_record = replace(current, phase=DeploymentPhase.UPLOADING)
                    await self._deployments.async_put(next_record, expected_version=None)
                    current = next_record
                    if isinstance(compiled, CompiledEffect):
                        if compiled.activation_packet is None:
                            raise RuntimeError("compiled activation verification has no activation packet")
                        if not coordinator.is_on:
                            await coordinator.send_command(
                                build_power(True, coordinator.model),
                                write_guard=lambda: validate_compiled_geometry(compiled, coordinator.profile),
                            )
                            coordinator.is_on = True
                        upload_count = len(compiled.upload_packets)

                        async def attempt_started(attempt: int) -> None:
                            nonlocal current
                            if attempt == 1:
                                return
                            current = replace(
                                current,
                                phase=(DeploymentPhase.UPLOADING if upload_count else DeploymentPhase.ACTIVATING),
                                progress_current=0,
                            )
                            await self._deployments.async_put(
                                current,
                                expected_version=None,
                                durable=False,
                            )

                        async def record_sequence_progress(index: int) -> None:
                            nonlocal current
                            phase = DeploymentPhase.ACTIVATING if index >= upload_count else DeploymentPhase.UPLOADING
                            current = replace(
                                current,
                                phase=phase,
                                progress_current=index,
                            )
                            await self._deployments.async_put(
                                current,
                                expected_version=None,
                                durable=False,
                            )

                        if upload_count == 0:
                            current = replace(current, phase=DeploymentPhase.ACTIVATING)
                            await self._deployments.async_put(current, expected_version=None)
                        ack_options: dict[str, Any] = {}
                        if "native_diy_positive_ack_required" in compiled.evidence_codes:
                            ack_options = {"require_upload_ack": True, "upload_ack_index": upload_count - 1}
                        await coordinator.async_write_effect_sequence(
                            compiled.packets,
                            intent=ControlIntent.APPLY,
                            attempt_started=attempt_started,
                            progress=record_sequence_progress,
                            write_guard=lambda: validate_compiled_geometry(compiled, coordinator.profile),
                            **ack_options,
                        )
                    else:
                        current = await self._async_apply_profile(coordinator, compiled, current)

                    next_record = replace(current, phase=DeploymentPhase.VERIFYING)
                    await self._deployments.async_put(next_record, expected_version=None)
                    current = next_record
                    confirmed, confidence, current = await self._async_verify(
                        coordinator,
                        compiled,
                        current,
                    )
                    if not confirmed:
                        return await self._async_finish_failure(
                            coordinator,
                            current,
                            error_code="device_state_unconfirmed",
                            writes_attempted=writes_attempted(),
                        )
                    completed = replace(
                        current,
                        phase=DeploymentPhase.CONFIRMED,
                        error_code=None,
                        verification_confidence=confidence,
                    )
                    await self._deployments.async_put(completed, expected_version=None)
                    self._reconcile_observation(
                        coordinator,
                        config_entry_id=record.config_entry_id,
                        observed_at=record.updated_at,
                        refreshed=True,
                        matched_record=completed,
                    )
                    return completed
                except asyncio.CancelledError:
                    current = self._deployments.get_optional(record.operation_id) or current
                    await self._async_finish_failure_while_locked_best_effort(
                        coordinator,
                        current,
                        error_code="operation_cancelled",
                        writes_attempted=writes_attempted(),
                    )
                    raise
                except Exception as exc:
                    current = self._deployments.get_optional(record.operation_id) or current
                    await self._async_finish_failure_while_locked_best_effort(
                        coordinator,
                        current,
                        error_code=type(exc).__name__,
                        writes_attempted=writes_attempted(),
                    )
                    raise
        except asyncio.CancelledError:
            if not lock_acquired:
                await self._async_finish_failure_best_effort(
                    coordinator,
                    current,
                    error_code="operation_cancelled",
                )
            raise
        except Exception as exc:
            if not lock_acquired:
                await self._async_finish_failure_best_effort(
                    coordinator,
                    current,
                    error_code=type(exc).__name__,
                )
            raise

    @asynccontextmanager
    async def _operation_lock(self, operation_id: UUID) -> AsyncIterator[None]:
        async with self._operation_locks_guard:
            lock = self._operation_locks.setdefault(operation_id, asyncio.Lock())
            self._operation_lock_users[operation_id] = self._operation_lock_users.get(operation_id, 0) + 1
        try:
            async with lock:
                yield
        finally:
            async with self._operation_locks_guard:
                remaining = self._operation_lock_users[operation_id] - 1
                if remaining:
                    self._operation_lock_users[operation_id] = remaining
                else:
                    self._operation_lock_users.pop(operation_id, None)
                    self._operation_locks.pop(operation_id, None)

    async def _async_activate(
        self,
        coordinator: GoveeBLECoordinator,
        compiled: CompiledEffect,
    ) -> None:
        for attempt in range(ACTIVATION_ATTEMPTS):
            try:
                assert compiled.activation_packet is not None
                await coordinator.send_command(
                    compiled.activation_packet,
                    write_guard=lambda: validate_compiled_geometry(compiled, coordinator.profile),
                )
                return
            except Exception:
                if attempt + 1 == ACTIVATION_ATTEMPTS:
                    raise

    async def _async_apply_profile(
        self,
        coordinator: GoveeBLECoordinator,
        compiled: CompiledMusicProfile | CompiledVideoProfile,
        record: DeploymentRecord,
    ) -> DeploymentRecord:
        current = record

        async def record_progress(progress_current: int) -> None:
            nonlocal current
            current = await self._record_profile_progress(current, progress_current)

        await async_apply_compiled_profile(
            coordinator,
            compiled,
            progress=record_progress,
        )
        return current

    async def _record_profile_progress(
        self,
        record: DeploymentRecord,
        progress_current: int,
    ) -> DeploymentRecord:
        current = replace(record, progress_current=progress_current)
        await self._deployments.async_put(
            current,
            expected_version=None,
            durable=False,
        )
        return current

    async def _async_verify(
        self,
        coordinator: GoveeBLECoordinator,
        compiled: CompiledApplication,
        record: DeploymentRecord,
    ) -> tuple[bool, ObservationConfidence, DeploymentRecord]:
        expectations, confidence = compiled_observation(compiled, profile=coordinator.profile)
        if expectations is None:
            return False, ObservationConfidence.UNKNOWN, record
        if not isinstance(compiled, CompiledEffect):
            return await self._async_verify_profile(coordinator, compiled, record)
        if compiled.activation_packet is None:
            raise RuntimeError("compiled activation verification has no activation packet")
        current = record
        for attempt in range(VERIFICATION_ATTEMPTS):
            # Suppressed or missing readback does not spend an activation retry.
            refreshed = None
            for observation in range(VERIFICATION_ATTEMPTS):
                try:
                    refreshed = await coordinator.async_observe_effect(expectations, timeout=4.0)
                except Exception:
                    if observation + 1 == VERIFICATION_ATTEMPTS:
                        raise
                    continue
                if refreshed is not None:
                    break
            if refreshed is True:
                return True, confidence, current
            if refreshed is not False or attempt + 1 == VERIFICATION_ATTEMPTS:
                break
            current = replace(current, phase=DeploymentPhase.ACTIVATING)
            await self._deployments.async_put(current, expected_version=None)
            await self._async_activate(coordinator, compiled)
            current = replace(current, phase=DeploymentPhase.VERIFYING)
            await self._deployments.async_put(current, expected_version=None)
        return False, ObservationConfidence.UNKNOWN, current

    async def _async_verify_profile(
        self,
        coordinator: GoveeBLECoordinator,
        compiled: CompiledMusicProfile | CompiledVideoProfile,
        record: DeploymentRecord,
    ) -> tuple[bool, ObservationConfidence, DeploymentRecord]:
        current = record
        expectations, confidence = compiled_observation(compiled, profile=coordinator.profile)
        if expectations is None:
            return False, ObservationConfidence.UNKNOWN, current
        for attempt in range(VERIFICATION_ATTEMPTS):
            if await coordinator.async_observe_effect(expectations, timeout=4.0) is True:
                return True, confidence, current
            if attempt + 1 < VERIFICATION_ATTEMPTS:
                current = replace(
                    current,
                    phase=DeploymentPhase.UPLOADING,
                    progress_current=0,
                )
                await self._deployments.async_put(current, expected_version=None)
                current = await self._async_apply_profile(coordinator, compiled, current)
                current = replace(current, phase=DeploymentPhase.VERIFYING)
                await self._deployments.async_put(current, expected_version=None)
        return False, ObservationConfidence.UNKNOWN, current

    async def _async_finish_failure(
        self,
        coordinator: GoveeBLECoordinator,
        record: DeploymentRecord,
        *,
        error_code: str,
        writes_attempted: bool | None = None,
    ) -> DeploymentRecord:
        writes_may_have_started = record.phase in {
            DeploymentPhase.UPLOADING,
            DeploymentPhase.ACTIVATING,
            DeploymentPhase.VERIFYING,
            DeploymentPhase.RECOVERING,
        }
        if writes_attempted is False or not writes_may_have_started:
            failed = replace(
                record,
                phase=DeploymentPhase.FAILED,
                error_code=error_code,
                verification_confidence=ObservationConfidence.UNKNOWN,
            )
            await self._deployments.async_put(failed, expected_version=None)
            self._publish_coordinator_state(coordinator)
            return failed

        recovering = replace(
            record,
            phase=DeploymentPhase.RECOVERING,
            error_code=error_code,
            verification_confidence=ObservationConfidence.UNKNOWN,
        )
        await self._deployments.async_put(recovering, expected_version=None)
        recovered = False
        if recovering.prior_state is not None:
            restore = getattr(coordinator, "async_restore_effect_control_state", None)
            if restore is not None:
                try:
                    recovered = await restore(
                        recovering.prior_state,
                        overwritten_diy_code=(
                            recovering.diy_code
                            if _record_signature(recovering, coordinator.model) == f"custom:{recovering.diy_code}"
                            else -1
                            if recovering.target_mode in {ActivationMode.SCENE.value, ActivationMode.CUSTOM.value}
                            else None
                        ),
                    )
                except Exception:
                    _LOGGER.exception(
                        "Failed to recover the prior state after Effect Studio deployment %s",
                        recovering.operation_id,
                    )
        final = replace(
            recovering,
            phase=DeploymentPhase.FAILED if recovered else DeploymentPhase.UNCERTAIN,
        )
        await self._deployments.async_put(final, expected_version=None)
        self._reconcile_observation(
            coordinator,
            config_entry_id=record.config_entry_id,
            observed_at=record.updated_at,
            refreshed=recovered,
        )
        self._publish_coordinator_state(coordinator)
        return final

    @staticmethod
    def _publish_coordinator_state(coordinator: GoveeBLECoordinator) -> None:
        publish = getattr(coordinator, "async_set_updated_data", None)
        if publish is not None:
            publish(getattr(coordinator, "data", None) or {})

    async def _async_finish_failure_best_effort(
        self,
        coordinator: GoveeBLECoordinator,
        record: DeploymentRecord,
        *,
        error_code: str,
    ) -> None:
        try:
            # Ownership was never acquired: persist failure without admitting new control.
            await self._async_finish_failure(
                coordinator,
                record,
                error_code=error_code,
                writes_attempted=False,
            )
        except Exception:
            _LOGGER.exception(
                "Failed to persist the terminal state for Effect Studio deployment %s",
                record.operation_id,
            )

    async def _async_finish_failure_while_locked_best_effort(
        self,
        coordinator: GoveeBLECoordinator,
        record: DeploymentRecord,
        *,
        error_code: str,
        writes_attempted: bool | None = None,
    ) -> None:
        try:
            await self._async_finish_failure(
                coordinator,
                record,
                error_code=error_code,
                writes_attempted=writes_attempted,
            )
        except Exception:
            _LOGGER.exception(
                "Failed to persist the terminal state for Effect Studio deployment %s",
                record.operation_id,
            )

    async def _async_refresh_for_reconciliation(
        self,
        coordinator: GoveeBLECoordinator,
    ) -> bool:
        if not coordinator.profile.state_readable:
            return False
        try:
            return await coordinator.refresh_state()
        except Exception:
            _LOGGER.debug(
                "Could not refresh %s before Effect Studio reconciliation",
                getattr(coordinator, "address", coordinator.model),
                exc_info=True,
            )
            return False

    async def _async_prepare_prior_state(
        self,
        coordinator: GoveeBLECoordinator,
        compiled: CompiledApplication,
    ) -> bool:
        profile = coordinator.profile
        refreshed = False
        if profile.state_readable:
            revisions = getattr(coordinator, "_field_revisions", {})
            baselines = {
                field: revisions.get(field, 0)
                for field, readable in (
                    ("is_on", profile.can_read(ReadDomain.POWER)),
                    ("brightness_pct", profile.can_read(ReadDomain.BRIGHTNESS)),
                    ("color_mode", profile.supports_color_mode_readback),
                )
                if readable and hasattr(coordinator, "_field_revisions")
            }
            refreshed = (
                await coordinator.refresh_state(
                    refresh_all=True,
                    required_domains=profile.read_domains
                    & {ReadDomain.POWER, ReadDomain.BRIGHTNESS, ReadDomain.COLOUR_MODE, ReadDomain.MODE},
                )
                is True
            )
            if not refreshed or any(
                coordinator._field_revisions.get(field, 0) <= baseline for field, baseline in baselines.items()
            ):
                raise RuntimeError("Could not read the current power, mode and brightness before applying the effect")
            if (
                profile.supports_segments
                and profile.can_read(ReadDomain.SEGMENTS)
                and _coordinator_mode(coordinator) in {"colour", "off"}
                and await coordinator.async_refresh_segments() is not True
            ):
                raise RuntimeError("Could not read the current segment layout before applying the effect")
        if not isinstance(compiled, CompiledVideoProfile):
            return refreshed
        profile = coordinator.profile
        refresh_display_settings = frozenset(
            setting
            for setting, requested in (
                ("white_balance", compiled.white_balance_wire is not None),
                ("blank_screen", compiled.blank_screen is not None),
                ("black_border", compiled.black_border is not None),
            )
            if requested
        )
        refresh_relative_brightness = compiled.relative_brightness is not None
        if not refresh_display_settings and not refresh_relative_brightness:
            return refreshed
        if not refreshed or not await coordinator.refresh_state(
            refresh_display_settings=refresh_display_settings,
            refresh_relative_brightness=refresh_relative_brightness,
        ):
            raise RuntimeError("Could not read the current video settings before applying the profile")
        required: list[object | None] = []
        if compiled.black_border is not None:
            required.append(coordinator.black_border)
        if compiled.white_balance_wire is not None:
            required.extend(
                (coordinator.white_balance_scalar,)
                if profile.video_white_balance_representation == "scalar"
                else (
                    coordinator.white_balance_flag,
                    coordinator.white_balance_red,
                    coordinator.white_balance_blue,
                    coordinator.white_balance_default_flag,
                    coordinator.white_balance_default_red,
                    coordinator.white_balance_default_blue,
                )
            )
        if compiled.relative_brightness is not None:
            required.extend(
                getattr(coordinator, f"relative_brightness_{zone}") for zone in profile.video_brightness_zones
            )
        if compiled.blank_screen is not None:
            required.extend(
                (
                    coordinator.blank_screen,
                    coordinator.blank_screen_detection,
                    coordinator.blank_screen_low_brightness_duration_seconds,
                    coordinator.blank_screen_same_tone_duration_seconds,
                )
            )
        if any(value is None for value in required):
            raise RuntimeError("The current video settings are incomplete")
        if (
            compiled.white_balance_wire is not None
            and profile.video_white_balance_representation == "position"
            and coordinator.white_balance_flag not in (0, 1)
        ):
            raise RuntimeError("The current white-balance mode cannot be safely restored")
        return True

    def _capture_prior_state(
        self,
        coordinator: GoveeBLECoordinator,
        *,
        config_entry_id: str,
    ) -> PriorControlState:
        capture = getattr(coordinator, "capture_effect_control_state", None)
        if capture is not None:
            captured = capture()
            if not isinstance(captured, PriorControlState):
                raise TypeError("coordinator returned an invalid prior control state")
            observed = self._device_cache.get(config_entry_id) if self._device_cache is not None else None
            if captured.scene_code is not None and observed is not None and observed.matched_operation_id is not None:
                matched = self._deployments.get_optional(observed.matched_operation_id)
                if (
                    matched is not None
                    and matched.target_mode == ActivationMode.SCENE.value
                    and matched.diy_code == captured.scene_code
                ):
                    captured = replace(captured, effect=matched.target_effect)
            return captured
        return PriorControlState(
            mode=_coordinator_mode(coordinator),
            is_on=getattr(coordinator, "is_on", True),
            brightness_pct=getattr(coordinator, "brightness_pct", 100),
            rgb_color=getattr(coordinator, "rgb_color", (255, 255, 255)),
            color_temp_kelvin=getattr(coordinator, "color_temp_kelvin", None),
            segment_colors=tuple(coordinator.segment_colors)
            if getattr(coordinator, "segment_state_source", None) == "observed"
            else None,
            segment_brightness=tuple(coordinator.segment_brightness)
            if getattr(coordinator, "segment_state_source", None) == "observed"
            else None,
            effect=getattr(coordinator, "effect", None),
            scene_code=getattr(coordinator, "scene_code", None),
            diy_code=coordinator.diy_code,
            music_mode=getattr(coordinator, "music_mode", "off"),
            music_model=coordinator.model,
            music_palette=getattr(coordinator, "music_palette", None),
            music_body=getattr(coordinator, "music_body", None),
            music_parameters=capture_music_parameters(
                coordinator,
                coordinator.profile,
                getattr(coordinator, "music_mode", "off"),
            ),
            video_mode=getattr(coordinator, "video_mode", "off"),
            video_parameters=getattr(coordinator, "video_parameters", None),
            music_sensitivity=getattr(coordinator, "music_sensitivity", 100),
            music_calm=getattr(coordinator, "music_calm", False),
            music_color=getattr(coordinator, "music_color", None),
            music_separation_point=getattr(coordinator, "music_separation_point", 1),
            music_separation_gradient=getattr(coordinator, "music_separation_gradient", True),
            music_hopping_brightness=getattr(coordinator, "music_hopping_brightness", 50),
            music_piano_key_count=getattr(coordinator, "music_piano_key_count", 15),
            music_fountain_direction=getattr(coordinator, "music_fountain_direction", "clockwise"),
            music_daynight_segments=getattr(coordinator, "music_daynight_segments", 1),
            music_daynight_speed=getattr(coordinator, "music_daynight_speed", 10),
            music_daynight_gradient=getattr(coordinator, "music_daynight_gradient", False),
            video_full_screen=getattr(coordinator, "video_full_screen", True),
            video_saturation=getattr(coordinator, "video_saturation", 100),
            video_sound_effects=getattr(coordinator, "video_sound_effects", False),
            video_sound_effects_softness=getattr(coordinator, "video_sound_effects_softness", 100),
            white_balance_red=getattr(coordinator, "white_balance_red", None),
            white_balance_blue=getattr(coordinator, "white_balance_blue", None),
            white_balance_flag=getattr(coordinator, "white_balance_flag", None),
            white_balance_default_flag=getattr(coordinator, "white_balance_default_flag", None),
            white_balance_default_red=getattr(coordinator, "white_balance_default_red", None),
            white_balance_default_blue=getattr(coordinator, "white_balance_default_blue", None),
            white_balance_scalar=getattr(coordinator, "white_balance_scalar", None),
            relative_brightness=getattr(coordinator, "relative_brightness", None),
            relative_brightness_left=getattr(coordinator, "relative_brightness_left", None),
            relative_brightness_top=getattr(coordinator, "relative_brightness_top", None),
            relative_brightness_right=getattr(coordinator, "relative_brightness_right", None),
            relative_brightness_bottom=getattr(coordinator, "relative_brightness_bottom", None),
            relative_brightness_strip_left=getattr(coordinator, "relative_brightness_strip_left", None),
            relative_brightness_strip_right=getattr(coordinator, "relative_brightness_strip_right", None),
            blank_screen=getattr(coordinator, "blank_screen", None),
            black_border=getattr(coordinator, "black_border", None),
            blank_screen_detection=getattr(coordinator, "blank_screen_detection", None),
            blank_screen_low_brightness_duration_seconds=getattr(
                coordinator,
                "blank_screen_low_brightness_duration_seconds",
                None,
            ),
            blank_screen_same_tone_duration_seconds=getattr(
                coordinator,
                "blank_screen_same_tone_duration_seconds",
                None,
            ),
        )

    def _reconcile_observation(
        self,
        coordinator: GoveeBLECoordinator,
        *,
        config_entry_id: str,
        observed_at: str,
        refreshed: bool,
        matched_record: DeploymentRecord | None = None,
    ) -> ObservedDeviceState:
        mode = _coordinator_mode(coordinator)
        previous = self._device_cache.get(config_entry_id) if self._device_cache is not None else None
        scene_code = getattr(coordinator, "scene_code", None)
        diy_code = coordinator.diy_code if mode == "custom" else None
        effect = coordinator.effect if mode == "scene" else None
        observable_signature = observable_signature_for_coordinator(coordinator)
        observable_signatures = observable_signatures_for_coordinator(coordinator)
        workspace = self._active_workspaces.get(config_entry_id) if self._active_workspaces is not None else None
        workspace_matches = active_workspace_matches(coordinator, workspace)
        if (
            workspace_matches
            and workspace is not None
            and isinstance(workspace.content, WorkshopEffect | PaletteDiyEffect)
            and scene_code is not None
            and workspace.observable_signature == f"scene-code:{scene_code}"
        ):
            mode, diy_code, effect = "custom", scene_code, None
        verified_now = matched_record is not None
        if matched_record is None and not workspace_matches:
            latest = max(
                (
                    record
                    for record in self._deployments.snapshot().records
                    if record.config_entry_id == config_entry_id
                    and _record_signature(record, coordinator.model) in observable_signatures
                ),
                key=lambda record: record.updated_at,
                default=None,
            )
            if latest is not None and latest.phase is DeploymentPhase.CONFIRMED:
                if latest.target_mode in {"music", "video"} or _activation_matches(coordinator, latest):
                    matched_record = latest
        if matched_record is not None and matched_record.target_mode == ActivationMode.SCENE.value:
            observable_signature = f"scene-code:{scene_code}" if scene_code is not None else observable_signature
            if (
                workspace is not None
                and workspace.model == coordinator.model
                and observable_signature is not None
                and matched_record.target_effect is not None
                and workspace.observable_signature
                in {
                    observable_signature,
                    f"scene:{matched_record.target_effect}",
                }
            ):
                migrated_workspace = replace(workspace, observable_signature=observable_signature)
                workspace_matches = active_workspace_matches(coordinator, migrated_workspace)
                if (
                    workspace_matches
                    and self._active_workspaces is not None
                    and workspace.observable_signature != observable_signature
                ):
                    workspace = migrated_workspace
                    self._active_workspaces.set(workspace)
        if matched_record is not None:
            observable_signature = _record_signature(matched_record, coordinator.model)
            if matched_record.target_mode == ActivationMode.CUSTOM.value:
                mode, diy_code, effect = "custom", matched_record.diy_code, None
        profile_match = matched_record is not None and (
            (matched_record.content_kind == "music_profile" and mode == "music")
            or (matched_record.content_kind == "video_profile" and mode == "video")
        )
        if workspace_matches and matched_record is None:
            assert workspace is not None
            confidence = (
                ObservationConfidence.MODE_MATCH
                if mode in {"music", "video"} and workspace.confidence is ObservationConfidence.SETTINGS_MATCH
                else workspace.confidence
            )
        elif profile_match and matched_record is not None:
            confidence = matched_record.verification_confidence if verified_now else ObservationConfidence.MODE_MATCH
        elif diy_code is not None or effect is not None or scene_code is not None:
            confidence = (
                ObservationConfidence.ACTIVATION_MATCH if matched_record is not None else ObservationConfidence.UNKNOWN
            )
        elif mode in {"music", "video"}:
            confidence = ObservationConfidence.UNKNOWN
        elif refreshed:
            confidence = ObservationConfidence.EXACT_SESSION
        else:
            confidence = ObservationConfidence.UNKNOWN
        active_effect = (
            ActiveEffectHint.from_record(
                matched_record,
                observable_signature=observable_signature,
                confidence=confidence,
            )
            if matched_record is not None
            and observable_signature is not None
            and confidence
            in {
                ObservationConfidence.ACTIVATION_MATCH,
                ObservationConfidence.SETTINGS_MATCH,
                ObservationConfidence.MODE_MATCH,
            }
            else None
        )
        if (
            active_effect is None
            and not workspace_matches
            and observable_signature is not None
            and previous is not None
            and previous.active_effect is not None
            and previous.active_effect.observable_signature == observable_signature
        ):
            confidence = ObservationConfidence.UNKNOWN
            active_effect = replace(previous.active_effect, confidence=confidence)
        state = ObservedDeviceState(
            config_entry_id=config_entry_id,
            mode=mode,
            observed_at=observed_at,
            confidence=confidence,
            diy_code=diy_code,
            effect=effect,
            native_mode=_native_mode_for_state(coordinator, mode=mode),
            matched_operation_id=(
                matched_record.operation_id
                if matched_record is not None
                and confidence
                in {
                    ObservationConfidence.ACTIVATION_MATCH,
                    ObservationConfidence.SETTINGS_MATCH,
                    ObservationConfidence.MODE_MATCH,
                }
                else None
            ),
            active_effect=active_effect,
        )
        if self._device_cache is not None:
            self._device_cache.set(state)
        return state


def _native_mode_for_state(
    coordinator: GoveeBLECoordinator,
    *,
    mode: str,
) -> str | None:
    if mode == "scene":
        effect = getattr(coordinator, "effect", None)
        return effect if isinstance(effect, str) and effect else None
    if mode == "music":
        music_mode = getattr(coordinator, "music_mode", None)
        return music_mode if isinstance(music_mode, str) and music_mode != "off" else None
    if mode == "video":
        video_mode = getattr(coordinator, "video_mode", None)
        return video_mode if isinstance(video_mode, str) and video_mode != "off" else None
    return None


def observable_signature_for_state(
    coordinator: GoveeBLECoordinator,
    *,
    mode: str,
    diy_code: int | None,
    effect: str | None,
) -> str | None:
    if mode == "custom" and diy_code is not None:
        return f"custom:{diy_code}"
    if mode == "scene" and effect is not None:
        return f"scene:{effect}"
    if mode == "music":
        music_mode = getattr(coordinator, "music_mode", None)
        return f"music:{music_mode}" if isinstance(music_mode, str) and music_mode != "off" else None
    if mode == "video":
        video_mode = getattr(coordinator, "video_mode", None)
        return f"video:{video_mode}" if isinstance(video_mode, str) and video_mode != "off" else None
    return None


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
    if isinstance(source, LayeredEffect) and isinstance(decoded, LayeredEffect):
        return replace(decoded, native_diy=source.native_diy)
    return decoded if type(decoded) is type(source) else source


def active_workspace_matches(
    coordinator: GoveeBLECoordinator,
    workspace: ActiveEffectWorkspace | None,
) -> bool:
    """Match the exact selector without mistaking a shared scene code for content."""
    if (
        workspace is None
        or workspace.model != coordinator.model
        or workspace.observable_signature not in observable_signatures_for_coordinator(coordinator)
    ):
        return False
    content = workspace.content
    identity: tuple[int, int] | None
    if isinstance(content, BuiltinScene | PaletteScene | LayeredScene):
        identity = (content.template.scene_id, content.template.effect_id)
    elif isinstance(content, LayeredEffect):
        if content.native_diy is not None:
            return getattr(coordinator, "scene_code", None) == content.native_diy
        identity = get_profile(workspace.model).advanced_scene_carrier
    else:
        return True
    resolved = None if identity is None else resolve_scene_identity(workspace.model, *identity)
    if resolved is None:
        return False
    key, entry = resolved
    scene_code = getattr(coordinator, "scene_code", None)
    return (scene_code is None or scene_code == entry.code) and (
        not scene_code_is_ambiguous(workspace.model, entry.code)
        or coordinator.effect == canonical_scene_key(workspace.model, key)
    )


def observable_signature_for_coordinator(
    coordinator: GoveeBLECoordinator,
) -> str | None:
    scene_code = getattr(coordinator, "scene_code", None)
    if scene_code is not None:
        return f"scene-code:{scene_code}"
    return observable_signature_for_state(
        coordinator,
        mode=_coordinator_mode(coordinator),
        diy_code=coordinator.diy_code,
        effect=coordinator.effect,
    )


def observable_signatures_for_coordinator(
    coordinator: GoveeBLECoordinator,
) -> frozenset[str]:
    if not coordinator.is_on:
        return frozenset()
    signatures = {
        signature
        for signature in (
            observable_signature_for_coordinator(coordinator),
            (f"scene-code:{coordinator.scene_code}" if getattr(coordinator, "scene_code", None) is not None else None),
            f"scene:{coordinator.effect}"
            if coordinator.effect is not None and getattr(coordinator, "scene_code", None) is None
            else None,
        )
        if signature is not None
    }
    return frozenset(signatures)


def _coordinator_mode(coordinator: GoveeBLECoordinator) -> str:
    mode = getattr(coordinator, "active_mode", None)
    if isinstance(mode, str):
        return mode
    if not getattr(coordinator, "is_on", True):
        return "off"
    if getattr(coordinator, "unknown_scene_code", None) is not None:
        return "scene"
    if coordinator.diy_code is not None:
        return "custom"
    if getattr(coordinator, "effect", None) is not None:
        return "scene"
    if getattr(coordinator, "music_mode", "off") not in (None, "off"):
        return "music"
    if getattr(coordinator, "video_mode", "off") not in (None, "off"):
        return "video"
    return "colour"


def compiled_observation(
    compiled: CompiledApplication,
    *,
    profile: ModelProfile | None = None,
) -> tuple[dict[str, Any] | None, ObservationConfidence]:
    """Fields with evidenced readback, independent of the write grammar."""
    profile = get_profile(compiled.model) if profile is None else profile
    if not profile.can_read(ReadDomain.POWER) or not profile.supports_color_mode_readback:
        return None, ObservationConfidence.UNKNOWN
    expectations: dict[str, Any] = {"is_on": True}
    if isinstance(compiled, CompiledEffect):
        expectations["diy_code" if compiled.selector_kind == "diy" else "scene_code"] = compiled.diy_code
        if (
            compiled.activation_mode is ActivationMode.SCENE
            and compiled.diy_code is not None
            and compiled.expected_effect is not None
            and scene_code_is_ambiguous(compiled.model, compiled.diy_code)
        ):
            expectations["effect"] = canonical_scene_key(compiled.model, compiled.expected_effect)
        return expectations, ObservationConfidence.ACTIVATION_MATCH
    if isinstance(compiled, CompiledMusicProfile):
        expectations["music_mode"] = compiled.mode
        # H617A settings are not confirmed by the shipped readback evidence.
        if profile.status_grammar in {"H6099", "H6199"}:
            expectations["music_sensitivity"] = compiled.sensitivity
            variant = music_variant(profile, MUSIC_MODE_SLUGS[compiled.mode])
            if profile.supports_music_color and (variant is None or variant.supports_fixed_colour):
                expectations["music_color"] = compiled.colour
            if compiled.mode == "rhythm" and variant and variant.supports_style:
                expectations["music_calm"] = compiled.calm
        if len(compiled.packets) > 2:
            return expectations, ObservationConfidence.MODE_MATCH
    else:
        expectations["video_mode"] = compiled.mode
        if profile.video_grammar not in {"H6099", "H6199", "H66A0-video"}:
            return None, ObservationConfidence.UNKNOWN
        complete = True
        for field in ("full_screen", "saturation", "sound_effects", "sound_effects_softness"):
            if (value := getattr(compiled, field)) is not None:
                expectations[f"video_{field}"] = value
        if compiled.white_balance_wire is not None:
            if profile.can_read(ReadDomain.DISPLAY_SETTING):
                fields = (
                    ("white_balance_scalar",)
                    if profile.video_white_balance_representation == "scalar"
                    else ("white_balance_red", "white_balance_blue")
                )
                expectations.update(zip(fields, compiled.white_balance_wire, strict=True))
                if profile.video_white_balance_representation == "position":
                    expectations["white_balance_flag"] = 1
            else:
                complete = False
        if compiled.blank_screen is not None:
            if profile.can_read(ReadDomain.DISPLAY_SETTING):
                expectations["blank_screen"] = compiled.blank_screen
                if compiled.blank_screen_policy is not None:
                    expectations.update(
                        zip(
                            (
                                "blank_screen_detection",
                                "blank_screen_low_brightness_duration_seconds",
                                "blank_screen_same_tone_duration_seconds",
                            ),
                            compiled.blank_screen_policy,
                            strict=True,
                        )
                    )
            else:
                complete = False
        if compiled.black_border is not None:
            if profile.can_read(ReadDomain.DISPLAY_SETTING):
                expectations["black_border"] = compiled.black_border
            else:
                complete = False
        if compiled.relative_brightness is not None:
            if profile.can_read(ReadDomain.RELATIVE_BRIGHTNESS):
                expectations.update(
                    (f"relative_brightness_{zone}", value)
                    for zone, value in zip(profile.video_brightness_zones, compiled.relative_brightness, strict=True)
                )
                expectations["relative_brightness"] = (
                    compiled.relative_brightness[0] if len(set(compiled.relative_brightness)) == 1 else None
                )
            else:
                complete = False
        if not complete:
            return expectations, ObservationConfidence.MODE_MATCH
    confidence = ObservationConfidence.SETTINGS_MATCH if len(expectations) > 2 else ObservationConfidence.MODE_MATCH
    return expectations, confidence


def observable_signature_for_compiled(compiled: CompiledApplication) -> str | None:
    if isinstance(compiled, CompiledEffect):
        if compiled.diy_code is None:
            return None
        domain = "custom" if compiled.selector_kind == "diy" else "scene-code"
        return f"{domain}:{compiled.diy_code}"
    return f"{'music' if isinstance(compiled, CompiledMusicProfile) else 'video'}:{compiled.mode}"


def _record_signature(record: DeploymentRecord, model: str) -> str | None:
    if record.target_model is not None and record.target_model != model:
        return None
    if record.observable_signature is not None:
        return record.observable_signature
    # Old records only identify a selector when their shipped content route is known.
    if record.target_mode == "scene":
        return f"scene-code:{record.diy_code}" if record.diy_code is not None else f"scene:{record.target_effect}"
    if record.target_mode == "custom" and record.diy_code is not None:
        if record.content_kind in {"h617a_painted", "h617a_single", "h617a_multi"} and model in {"H617A", "H617E"}:
            return f"custom:{record.diy_code}"
        if (record.content_kind == "workshop" and model in {"H617A", "H617E", "H6199"}) or (
            record.content_kind == "palette_diy" and model == "H6199"
        ):
            return f"scene-code:{record.diy_code}"
    return None


def _activation_matches(
    coordinator: GoveeBLECoordinator,
    record: DeploymentRecord,
) -> bool:
    if not coordinator.is_on:
        return False
    signature = _record_signature(record, getattr(coordinator, "model", ""))
    if signature is None:
        return False
    if record.target_mode == ActivationMode.SCENE.value:
        scene_code = getattr(coordinator, "scene_code", None)
        if scene_code is not None:
            return _scene_record_matches(coordinator, record, scene_code)
        return record.target_effect is not None and coordinator.effect == record.target_effect
    return signature in observable_signatures_for_coordinator(coordinator)


def _scene_record_matches(
    coordinator: GoveeBLECoordinator,
    record: DeploymentRecord,
    scene_code: int,
) -> bool:
    if record.diy_code != scene_code:
        return False
    if not scene_code_is_ambiguous(coordinator.model, scene_code):
        return True
    return (
        record.target_effect is not None
        and coordinator.effect is not None
        and canonical_scene_key(coordinator.model, record.target_effect) == coordinator.effect
    )
