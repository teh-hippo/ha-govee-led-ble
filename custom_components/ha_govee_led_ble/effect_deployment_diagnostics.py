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
        if record.phase is DeploymentPhase.COMPILING:
            self._history.record(
                DiagnosticStage.COMPILATION,
                DiagnosticOutcome.SUCCEEDED,
                "artifact_compiled",
                details={
                    "artifact_sha256": record.artifact_sha256,
                    "compiler_version": record.compiler_version,
                },
                correlation_id=operation_id,
                config_entry_id=record.config_entry_id,
                operation_id=operation_id,
            )
            for code in record.evidence_codes:
                self._history.record_evidence_gap(
                    code,
                    details={
                        "target_mode": record.target_mode,
                        "target_effect": record.target_effect,
                    },
                    correlation_id=operation_id,
                    config_entry_id=record.config_entry_id,
                    operation_id=operation_id,
                )
        elif record.phase is DeploymentPhase.PENDING:
            self._history.record(
                DiagnosticStage.COMPILATION,
                DiagnosticOutcome.SUCCEEDED,
                "artifact_compiled",
                details={
                    "artifact_sha256": record.artifact_sha256,
                    "compiler_version": record.compiler_version,
                },
                correlation_id=operation_id,
                config_entry_id=record.config_entry_id,
                operation_id=operation_id,
            )
        elif record.phase is DeploymentPhase.UPLOADING:
            self._history.record(
                DiagnosticStage.PACKET_PROGRESS,
                DiagnosticOutcome.PROGRESS,
                "packet_upload_progress",
                details={
                    "current": record.progress_current,
                    "total": record.progress_total,
                },
                correlation_id=operation_id,
                config_entry_id=record.config_entry_id,
                operation_id=operation_id,
                coalesce=True,
            )
        elif record.phase is DeploymentPhase.ACTIVATING:
            self._history.record(
                DiagnosticStage.PACKET_PROGRESS,
                DiagnosticOutcome.PROGRESS,
                "activation_started",
                details={
                    "current": record.progress_current,
                    "total": record.progress_total,
                },
                correlation_id=operation_id,
                config_entry_id=record.config_entry_id,
                operation_id=operation_id,
            )
        elif record.phase is DeploymentPhase.VERIFYING:
            self._history.record(
                DiagnosticStage.VERIFICATION,
                DiagnosticOutcome.STARTED,
                "device_verification_started",
                details={"packets_sent": record.progress_current},
                correlation_id=operation_id,
                config_entry_id=record.config_entry_id,
                operation_id=operation_id,
            )
        elif record.phase is DeploymentPhase.CONFIRMED:
            self._history.record(
                DiagnosticStage.VERIFICATION,
                DiagnosticOutcome.SUCCEEDED,
                "device_verification_succeeded",
                details={"confidence": record.verification_confidence.value},
                correlation_id=operation_id,
                config_entry_id=record.config_entry_id,
                operation_id=operation_id,
            )
        elif record.phase is DeploymentPhase.APPLIED:
            self._history.record_evidence_gap(
                "application_write_completed",
                details={
                    "confidence": record.verification_confidence.value,
                    "packets_sent": record.progress_current,
                    "verification": "device_readback_unavailable",
                },
                correlation_id=operation_id,
                config_entry_id=record.config_entry_id,
                operation_id=operation_id,
            )
        elif record.phase in {DeploymentPhase.UNKNOWN, DeploymentPhase.UNCERTAIN}:
            self._history.record_evidence_gap(
                "device_state_uncertain",
                details={
                    "confidence": record.verification_confidence.value,
                    "error_code": record.error_code,
                    "progress_current": record.progress_current,
                    "progress_total": record.progress_total,
                },
                correlation_id=operation_id,
                config_entry_id=record.config_entry_id,
                operation_id=operation_id,
            )
        elif record.phase is DeploymentPhase.RECOVERING:
            self._history.record(
                DiagnosticStage.RECOVERY,
                DiagnosticOutcome.STARTED,
                "recovery_started",
                details={"error_code": record.error_code},
                correlation_id=operation_id,
                config_entry_id=record.config_entry_id,
                operation_id=operation_id,
            )
        elif record.phase is DeploymentPhase.INTERRUPTED:
            self._history.record(
                DiagnosticStage.RECOVERY,
                DiagnosticOutcome.INFORMATIONAL,
                "deployment_interrupted",
                details={
                    "error_code": record.error_code,
                    "progress_current": record.progress_current,
                    "progress_total": record.progress_total,
                },
                correlation_id=operation_id,
                config_entry_id=record.config_entry_id,
                operation_id=operation_id,
            )
        elif record.phase is DeploymentPhase.FAILED:
            if previous is not None and previous.phase is DeploymentPhase.RECOVERING:
                self._history.record(
                    DiagnosticStage.RECOVERY,
                    DiagnosticOutcome.SUCCEEDED,
                    "prior_state_recovered",
                    details={"deployment_error_code": record.error_code},
                    correlation_id=operation_id,
                    config_entry_id=record.config_entry_id,
                    operation_id=operation_id,
                )
            else:
                self._history.record(
                    DiagnosticStage.RECOVERY,
                    DiagnosticOutcome.FAILED,
                    "deployment_failed",
                    details={"error_code": record.error_code},
                    correlation_id=operation_id,
                    config_entry_id=record.config_entry_id,
                    operation_id=operation_id,
                )


def _transition(record: DeploymentRecord) -> _ObservedTransition:
    return _ObservedTransition(
        phase=record.phase,
        progress_current=record.progress_current,
        progress_total=record.progress_total,
        error_code=record.error_code,
        verification_confidence=record.verification_confidence,
    )
