"""Translate durable deployment transitions into diagnostic events."""

from __future__ import annotations

from dataclasses import dataclass

from .effect_deployments import (
    DeploymentPhase,
    DeploymentRecord,
    DeploymentSnapshot,
    EffectDeploymentRepository,
    ObservationConfidence,
)
from .effect_diagnostics import DiagnosticOutcome, DiagnosticStage, EffectDiagnosticHistory


@dataclass(frozen=True, slots=True)
class _ObservedTransition:
    phase: DeploymentPhase
    progress_current: int
    progress_total: int
    error_code: str | None
    verification_confidence: ObservationConfidence


class EffectDeploymentDiagnosticBridge:
    """Observe repository commits without coupling diagnostics to the BLE engine."""

    def __init__(
        self,
        repository: EffectDeploymentRepository,
        history: EffectDiagnosticHistory,
        initial_snapshot: DeploymentSnapshot,
    ) -> None:
        self._history = history
        self._observed = {str(record.operation_id): _transition(record) for record in initial_snapshot.records}
        for record in initial_snapshot.records:
            if record.error_code in {"home_assistant_restarted", "home_assistant_restarted_before_write"}:
                self._record(record, None)
        self._unsubscribe = repository.subscribe(self._snapshot_updated)

    def close(self) -> None:
        self._unsubscribe()

    def _snapshot_updated(self, snapshot: DeploymentSnapshot) -> None:
        current_operation_ids = {str(record.operation_id) for record in snapshot.records}
        self._observed = {
            operation_id: transition
            for operation_id, transition in self._observed.items()
            if operation_id in current_operation_ids
        }
        for record in snapshot.records:
            operation_id = str(record.operation_id)
            transition = _transition(record)
            previous = self._observed.get(operation_id)
            if previous == transition:
                continue
            self._record(record, previous)
            self._observed[operation_id] = transition

    def _record(
        self,
        record: DeploymentRecord,
        previous: _ObservedTransition | None,
    ) -> None:
        operation_id = str(record.operation_id)

        def emit(
            stage: DiagnosticStage, outcome: DiagnosticOutcome, code: str, *, coalesce: bool = False, **details: object
        ) -> None:
            self._history.record(
                stage,
                outcome,
                code,
                details=details,
                correlation_id=operation_id,
                config_entry_id=record.config_entry_id,
                operation_id=operation_id,
                coalesce=coalesce,
            )

        phase = record.phase
        if phase in {DeploymentPhase.COMPILING, DeploymentPhase.PENDING}:
            emit(
                DiagnosticStage.COMPILATION,
                DiagnosticOutcome.SUCCEEDED,
                "artifact_compiled",
                artifact_sha256=record.artifact_sha256,
                compiler_version=record.compiler_version,
            )
            if phase is DeploymentPhase.COMPILING:
                for code in record.evidence_codes:
                    emit(
                        DiagnosticStage.EVIDENCE_GAP,
                        DiagnosticOutcome.INFORMATIONAL,
                        code,
                        target_mode=record.target_mode,
                        target_effect=record.target_effect,
                    )
        elif phase is DeploymentPhase.UPLOADING:
            emit(
                DiagnosticStage.PACKET_PROGRESS,
                DiagnosticOutcome.PROGRESS,
                "packet_upload_progress",
                coalesce=True,
                current=record.progress_current,
                total=record.progress_total,
            )
        elif phase is DeploymentPhase.ACTIVATING:
            emit(
                DiagnosticStage.PACKET_PROGRESS,
                DiagnosticOutcome.PROGRESS,
                "activation_started",
                current=record.progress_current,
                total=record.progress_total,
            )
        elif phase is DeploymentPhase.VERIFYING:
            emit(
                DiagnosticStage.VERIFICATION,
                DiagnosticOutcome.STARTED,
                "device_verification_started",
                packets_sent=record.progress_current,
            )
        elif phase is DeploymentPhase.CONFIRMED:
            emit(
                DiagnosticStage.VERIFICATION,
                DiagnosticOutcome.SUCCEEDED,
                "device_verification_succeeded",
                confidence=record.verification_confidence.value,
            )
        elif phase is DeploymentPhase.APPLIED:
            emit(
                DiagnosticStage.EVIDENCE_GAP,
                DiagnosticOutcome.INFORMATIONAL,
                "application_write_completed",
                confidence=record.verification_confidence.value,
                packets_sent=record.progress_current,
                verification="device_readback_unavailable",
            )
        elif phase in {DeploymentPhase.UNKNOWN, DeploymentPhase.UNCERTAIN}:
            emit(
                DiagnosticStage.EVIDENCE_GAP,
                DiagnosticOutcome.INFORMATIONAL,
                "device_state_uncertain",
                confidence=record.verification_confidence.value,
                error_code=record.error_code,
                progress_current=record.progress_current,
                progress_total=record.progress_total,
            )
        elif phase is DeploymentPhase.RECOVERING:
            emit(DiagnosticStage.RECOVERY, DiagnosticOutcome.STARTED, "recovery_started", error_code=record.error_code)
        elif phase is DeploymentPhase.INTERRUPTED:
            emit(
                DiagnosticStage.RECOVERY,
                DiagnosticOutcome.INFORMATIONAL,
                "deployment_interrupted",
                error_code=record.error_code,
                progress_current=record.progress_current,
                progress_total=record.progress_total,
            )
        elif phase is DeploymentPhase.FAILED:
            if previous is not None and previous.phase is DeploymentPhase.RECOVERING:
                emit(
                    DiagnosticStage.RECOVERY,
                    DiagnosticOutcome.SUCCEEDED,
                    "prior_state_recovered",
                    deployment_error_code=record.error_code,
                )
            else:
                emit(
                    DiagnosticStage.RECOVERY,
                    DiagnosticOutcome.FAILED,
                    "deployment_failed",
                    error_code=record.error_code,
                )


def _transition(record: DeploymentRecord) -> _ObservedTransition:
    return _ObservedTransition(
        phase=record.phase,
        progress_current=record.progress_current,
        progress_total=record.progress_total,
        error_code=record.error_code,
        verification_confidence=record.verification_confidence,
    )
