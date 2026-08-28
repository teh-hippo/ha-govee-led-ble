"""Coordinator-owned Effect Studio deployment transactions."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import replace
from uuid import UUID, uuid4

from .const import MUSIC_MODE_SLUGS
from .control_arbiter import ControlIntent, async_control_intent
from .coordinator import GoveeBLECoordinator
from .effect_active_workspace import (
    ActiveEffectWorkspace,
    ActiveEffectWorkspaceRepository,
)
from .effect_catalogue import (
    H617A_TYPE04_APPLY_CODE,
    H617A_WORKSHOP_APPLY_CODE,
    H6199_PALETTE_DIY_APPLY_CODE,
    H6199_WORKSHOP_APPLY_CODE,
)
from .effect_compiler import (
    ActivationMode,
    CompiledApplication,
    CompiledEffect,
    CompiledMusicProfile,
    CompiledVideoProfile,
    compile_application,
)
from .effect_deployments import (
    DeploymentPhase,
    DeploymentRecord,
    EffectDeploymentRepository,
    ObservationConfidence,
    PriorControlState,
)
from .effect_domain import (
    EffectContent,
    LibraryItem,
    MultiEffect,
    MusicProfile,
    PaintedEffect,
    PaletteDiyEffect,
    SingleEffect,
    VideoProfile,
    WorkshopEffect,
)
from .effect_identity import ActiveEffectHint, EffectDeviceCache, ObservedDeviceState
from .effect_protocol_decoder import (
    UnsupportedA3EffectError,
    decode_a3_effect_frames,
)
from .generated_protocol_adapter import build_power
from .h6199_calibration import WHITE_BALANCE_POSITIONS
from .native_profile_controls import (
    apply_active_video_mode,
    apply_blank_screen,
    apply_relative_brightness,
    apply_white_balance,
)

ACTIVATION_ATTEMPTS = 2
VERIFICATION_ATTEMPTS = 2

_LOGGER = logging.getLogger(__name__)


async def async_apply_compiled_profile(
    coordinator: GoveeBLECoordinator,
    compiled: CompiledMusicProfile | CompiledVideoProfile,
    *,
    writer: Callable[[bytes], Awaitable[None]] | None = None,
    verify: bool = True,
    progress: Callable[[int], Awaitable[None]] | None = None,
) -> None:
    if isinstance(compiled, CompiledMusicProfile):
        coordinator.install_music_profile_state(
            mode=compiled.mode,
            sensitivity=compiled.sensitivity,
            colour=compiled.colour,
            calm=compiled.calm,
            parameters=compiled.parameters,
        )
        if writer is None:
            await coordinator.async_select_music_slug(
                compiled.mode,
                include_parameters=False,
            )
        else:
            await coordinator.async_select_music_slug(
                compiled.mode,
                include_parameters=False,
                writer=writer,
            )
        if progress is not None:
            await progress(1)
        if compiled.progress_total > 1:
            if writer is None:
                await coordinator.async_apply_music_params(MUSIC_MODE_SLUGS[compiled.mode])
            else:
                await coordinator.async_apply_music_params(
                    MUSIC_MODE_SLUGS[compiled.mode],
                    writer=writer,
                )
            if progress is not None:
                await progress(2)
        return

    coordinator.video_mode = compiled.mode
    coordinator.video_full_screen = compiled.full_screen
    coordinator.video_saturation = compiled.saturation
    coordinator.video_sound_effects = compiled.sound_effects
    coordinator.video_sound_effects_softness = compiled.sound_effects_softness
    coordinator.effect = None
    coordinator.music_mode = "off"
    coordinator.diy_code = None
    if writer is None and verify:
        await apply_active_video_mode(coordinator)
    else:
        await apply_active_video_mode(coordinator, writer=writer, verify=verify)
    if progress is not None:
        await progress(1)

    red, blue = WHITE_BALANCE_POSITIONS[compiled.white_balance_position - 1]
    coordinator.white_balance_red = red
    coordinator.white_balance_blue = blue
    if writer is None and verify:
        await apply_white_balance(coordinator)
    else:
        await apply_white_balance(coordinator, writer=writer, verify=verify)
    if progress is not None:
        await progress(2)

    left, top, right, bottom = compiled.relative_brightness
    coordinator.relative_brightness = left if len(set(compiled.relative_brightness)) == 1 else None
    coordinator.relative_brightness_left = left
    coordinator.relative_brightness_top = top
    coordinator.relative_brightness_right = right
    coordinator.relative_brightness_bottom = bottom
    if writer is None and verify:
        await apply_relative_brightness(coordinator)
    else:
        await apply_relative_brightness(coordinator, writer=writer, verify=verify)
    if progress is not None:
        await progress(3)

    coordinator.blank_screen = compiled.blank_screen
    if writer is None and verify:
        await apply_blank_screen(coordinator)
    else:
        await apply_blank_screen(coordinator, writer=writer, verify=verify)
    if progress is not None:
        await progress(4)


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
        resolved_diy_code = resolve_diy_code(item, diy_code)
        compiled = compile_application(item, coordinator.model, diy_code=resolved_diy_code)
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
                signature = observable_signature_for_coordinator(coordinator)
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
            await self._deployments.async_put(record, expected_version=None)
            async with async_control_intent(
                coordinator,
                ControlIntent.APPLY,
            ):
                lock_acquired = True
                try:
                    refreshed = await self._async_prepare_prior_state(coordinator, compiled)
                    self._reconcile_observation(
                        coordinator,
                        config_entry_id=record.config_entry_id,
                        observed_at=record.updated_at,
                        refreshed=refreshed,
                    )
                    prior_state = self._capture_prior_state(coordinator)
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
                            await coordinator.send_command(build_power(True, coordinator.model))
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
                        await coordinator.async_write_effect_sequence(
                            compiled.packets,
                            intent=ControlIntent.APPLY,
                            attempt_started=attempt_started,
                            progress=record_sequence_progress,
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
                    )
                    raise
                except Exception as exc:
                    current = self._deployments.get_optional(record.operation_id) or current
                    await self._async_finish_failure_while_locked_best_effort(
                        coordinator,
                        current,
                        error_code=type(exc).__name__,
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
        activation_packet: bytes,
    ) -> None:
        for attempt in range(ACTIVATION_ATTEMPTS):
            try:
                await coordinator.send_command(activation_packet)
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
        if not coordinator.profile.state_readable:
            return False, ObservationConfidence.UNKNOWN, record
        if not isinstance(compiled, CompiledEffect):
            return await self._async_verify_profile(coordinator, compiled, record)
        if compiled.activation_packet is None:
            raise RuntimeError("compiled activation verification has no activation packet")
        current = record
        for attempt in range(VERIFICATION_ATTEMPTS):
            try:
                refreshed = await coordinator.refresh_state()
            except Exception:
                if attempt + 1 == VERIFICATION_ATTEMPTS:
                    raise
                continue
            if refreshed and _activation_matches(coordinator, record):
                return True, ObservationConfidence.ACTIVATION_MATCH, current
            if refreshed and attempt + 1 < VERIFICATION_ATTEMPTS:
                current = replace(current, phase=DeploymentPhase.ACTIVATING)
                await self._deployments.async_put(current, expected_version=None)
                await self._async_activate(coordinator, compiled.activation_packet)
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
        confidence = _profile_verification_confidence(compiled)
        for attempt in range(VERIFICATION_ATTEMPTS):
            if await _async_refresh_profile(coordinator, compiled):
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
    ) -> DeploymentRecord:
        writes_may_have_started = record.phase in {
            DeploymentPhase.UPLOADING,
            DeploymentPhase.ACTIVATING,
            DeploymentPhase.VERIFYING,
            DeploymentPhase.RECOVERING,
        }
        if not writes_may_have_started:
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
                            if recovering.target_mode == ActivationMode.CUSTOM.value
                            else -1
                            if recovering.target_mode == ActivationMode.SCENE.value
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
            async with async_control_intent(
                coordinator,
                ControlIntent.APPLY,
            ):
                await self._async_finish_failure(
                    coordinator,
                    record,
                    error_code=error_code,
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
    ) -> None:
        try:
            await self._async_finish_failure(
                coordinator,
                record,
                error_code=error_code,
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
        refreshed = await self._async_refresh_for_reconciliation(coordinator)
        if not isinstance(compiled, CompiledVideoProfile):
            return refreshed
        if not refreshed or not await coordinator.refresh_state(
            refresh_display_settings=True,
            refresh_relative_brightness=True,
        ):
            raise RuntimeError("Could not read the current video settings before applying the profile")
        required = (
            coordinator.white_balance_red,
            coordinator.white_balance_blue,
            coordinator.relative_brightness_left,
            coordinator.relative_brightness_top,
            coordinator.relative_brightness_right,
            coordinator.relative_brightness_bottom,
            coordinator.blank_screen,
            coordinator.blank_screen_detection,
            coordinator.blank_screen_low_brightness_duration_seconds,
            coordinator.blank_screen_same_tone_duration_seconds,
        )
        if any(value is None for value in required):
            raise RuntimeError("The current video settings are incomplete")
        return True

    def _capture_prior_state(
        self,
        coordinator: GoveeBLECoordinator,
    ) -> PriorControlState:
        capture = getattr(coordinator, "capture_effect_control_state", None)
        if capture is not None:
            captured = capture()
            if not isinstance(captured, PriorControlState):
                raise TypeError("coordinator returned an invalid prior control state")
            return captured
        return PriorControlState(
            mode=_coordinator_mode(coordinator),
            is_on=getattr(coordinator, "is_on", True),
            brightness_pct=getattr(coordinator, "brightness_pct", 100),
            rgb_color=getattr(coordinator, "rgb_color", (255, 255, 255)),
            color_temp_kelvin=getattr(coordinator, "color_temp_kelvin", None),
            effect=getattr(coordinator, "effect", None),
            diy_code=coordinator.diy_code,
            music_mode=getattr(coordinator, "music_mode", "off"),
            video_mode=getattr(coordinator, "video_mode", "off"),
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
            relative_brightness=getattr(coordinator, "relative_brightness", None),
            relative_brightness_left=getattr(coordinator, "relative_brightness_left", None),
            relative_brightness_top=getattr(coordinator, "relative_brightness_top", None),
            relative_brightness_right=getattr(coordinator, "relative_brightness_right", None),
            relative_brightness_bottom=getattr(coordinator, "relative_brightness_bottom", None),
            blank_screen=getattr(coordinator, "blank_screen", None),
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
        raw_scene_code = getattr(coordinator, "unknown_scene_code", None)
        diy_code = coordinator.diy_code if mode == "custom" else None
        effect = coordinator.effect if mode == "scene" else None
        observable_signature = observable_signature_for_coordinator(coordinator)
        workspace = self._active_workspaces.get(config_entry_id) if self._active_workspaces is not None else None
        workspace_matches = (
            workspace is not None
            and workspace.model == coordinator.model
            and workspace.observable_signature == observable_signature
        )
        if workspace_matches and raw_scene_code is not None:
            mode = "custom"
            diy_code = raw_scene_code
            effect = None
        if raw_scene_code is not None:
            if matched_record is None and not workspace_matches:
                latest = self._deployments.latest_for_diy_code(config_entry_id, raw_scene_code)
                if latest is not None and latest.phase is DeploymentPhase.CONFIRMED:
                    matched_record = latest
            if matched_record is not None and matched_record.target_mode == ActivationMode.CUSTOM.value:
                mode = "custom"
                diy_code = raw_scene_code
        if diy_code is not None and matched_record is None and not workspace_matches:
            latest = self._deployments.latest_for_diy_code(config_entry_id, diy_code)
            if latest is not None and latest.phase is DeploymentPhase.CONFIRMED:
                matched_record = latest
        if effect is not None and matched_record is None and not workspace_matches:
            latest = self._deployments.latest_for_effect(config_entry_id, effect)
            if latest is not None and latest.phase is DeploymentPhase.CONFIRMED:
                matched_record = latest
        if mode in {"music", "video"} and matched_record is None and not workspace_matches:
            latest = self._deployments.latest_for_profile(config_entry_id, mode)
            if latest is not None and latest.phase is DeploymentPhase.CONFIRMED:
                matched_record = latest
        profile_match = matched_record is not None and (
            (matched_record.content_kind == "music_profile" and mode == "music")
            or (matched_record.content_kind == "video_profile" and mode == "video")
        )
        if workspace_matches and matched_record is None:
            assert workspace is not None
            confidence = workspace.confidence
        elif profile_match and matched_record is not None:
            confidence = matched_record.verification_confidence
        elif diy_code is not None or effect is not None:
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
    compiled: CompiledApplication,
) -> EffectContent:
    if not isinstance(compiled, CompiledEffect) or not compiled.upload_packets:
        return source
    try:
        decoded = decode_a3_effect_frames(compiled.upload_packets, compiled.model)
    except UnsupportedA3EffectError:
        return source
    return decoded if type(decoded) is type(source) else source


def observable_signature_for_coordinator(
    coordinator: GoveeBLECoordinator,
) -> str | None:
    unknown_scene_code = coordinator.unknown_scene_code
    if unknown_scene_code is not None:
        return f"custom:{unknown_scene_code}"
    return observable_signature_for_state(
        coordinator,
        mode=_coordinator_mode(coordinator),
        diy_code=coordinator.diy_code,
        effect=coordinator.effect,
    )


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


async def _async_refresh_profile(
    coordinator: GoveeBLECoordinator,
    compiled: CompiledMusicProfile | CompiledVideoProfile,
) -> bool:
    if isinstance(compiled, CompiledMusicProfile):
        if compiled.model == "H617A":
            return await coordinator.refresh_state(
                expected_on=True,
                expected_music_mode=compiled.mode,
            )
        return await coordinator.refresh_state(
            expected_on=True,
            expected_music_mode=compiled.mode,
            expected_music_sensitivity=compiled.sensitivity,
            expected_music_calm=compiled.calm if compiled.mode == "rhythm" else None,
            expected_music_color=compiled.colour,
            expected_music_auto_color=compiled.colour is None,
        )
    red, blue = WHITE_BALANCE_POSITIONS[compiled.white_balance_position - 1]
    return await coordinator.refresh_state(
        expected_on=True,
        expected_video_mode=compiled.mode,
        expected_video_full_screen=compiled.full_screen,
        expected_video_saturation=compiled.saturation,
        expected_video_sound_effects=compiled.sound_effects,
        expected_video_sound_effects_softness=compiled.sound_effects_softness,
        expected_white_balance=(red, blue),
        expected_blank_screen=compiled.blank_screen,
        expected_relative_brightness=compiled.relative_brightness,
    )


def _profile_verification_confidence(
    compiled: CompiledMusicProfile | CompiledVideoProfile,
) -> ObservationConfidence:
    if isinstance(compiled, CompiledMusicProfile) and compiled.model == "H617A":
        return ObservationConfidence.MODE_MATCH
    return ObservationConfidence.SETTINGS_MATCH


def resolve_diy_code(
    item: LibraryItem,
    requested: int | None = None,
) -> int | None:
    content = item.content
    if isinstance(content, MusicProfile | VideoProfile):
        if requested is not None:
            raise ValueError("profiles do not use a DIY code")
        return None
    if isinstance(content, WorkshopEffect):
        if requested is not None:
            expected = H6199_WORKSHOP_APPLY_CODE if content.model == "H6199" else H617A_WORKSHOP_APPLY_CODE
            if requested != expected:
                raise ValueError("Workshop activation slot does not match the evidenced model slot")
        return H6199_WORKSHOP_APPLY_CODE if content.model == "H6199" else H617A_WORKSHOP_APPLY_CODE
    if isinstance(content, PaintedEffect):
        return 800 if requested is None else requested
    if isinstance(content, SingleEffect | MultiEffect):
        return H617A_TYPE04_APPLY_CODE if requested is None else requested
    if isinstance(content, PaletteDiyEffect):
        return H6199_PALETTE_DIY_APPLY_CODE if requested is None else requested
    return None


def _activation_matches(
    coordinator: GoveeBLECoordinator,
    record: DeploymentRecord,
) -> bool:
    if not coordinator.is_on:
        return False
    if record.target_mode == ActivationMode.SCENE.value:
        return record.target_effect is not None and coordinator.effect == record.target_effect
    return coordinator.diy_code == record.diy_code or coordinator.unknown_scene_code == record.diy_code
