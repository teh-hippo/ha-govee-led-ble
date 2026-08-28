"""Bounded diagnostic contract for Effect Studio deployment operations."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

from custom_components.ha_govee_led_ble.effect_deployment_diagnostics import EffectDeploymentDiagnosticBridge
from custom_components.ha_govee_led_ble.effect_deployments import (
    DeploymentPhase,
    DeploymentRecord,
    EffectDeploymentRepository,
    ObservationConfidence,
)
from custom_components.ha_govee_led_ble.effect_diagnostics import (
    MAX_DIAGNOSTIC_COLLECTION_ITEMS,
    MAX_DIAGNOSTIC_DETAIL_FIELDS,
    MAX_DIAGNOSTIC_EVENTS,
    MAX_DIAGNOSTIC_PACKET_HASH_BYTES,
    MAX_DIAGNOSTIC_STRING_LENGTH,
    DiagnosticOutcome,
    DiagnosticPresentation,
    DiagnosticStage,
    EffectDiagnosticHistory,
)
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem, SingleEffect
from tests.storage_test_double import InMemoryVersionedDocumentStore

CORRELATION_ID = UUID("11111111-2222-4333-8444-555555555555")
TIMESTAMP = datetime(2026, 8, 14, 10, 39, 27, tzinfo=UTC)
REDACTED = "**REDACTED**"


def _history(**kwargs: object) -> EffectDiagnosticHistory:
    return EffectDiagnosticHistory(clock=lambda: TIMESTAMP, **kwargs)


def _record(history: EffectDiagnosticHistory, index: int = 0) -> None:
    history.record(
        DiagnosticStage.API_SERVICE,
        DiagnosticOutcome.STARTED,
        "apply_request_received",
        correlation_id=CORRELATION_ID,
        config_entry_id="entry-a",
        details={"index": index},
    )


def _deployment(phase: DeploymentPhase = DeploymentPhase.PENDING) -> DeploymentRecord:
    item = LibraryItem.new("Test", SingleEffect(0, 0, 50, ((255, 0, 0),)))
    return DeploymentRecord(
        operation_id=CORRELATION_ID,
        config_entry_id="entry-a",
        diy_code=800,
        phase=phase,
        compiler_version=1,
        artifact_sha256=sha256(b"artifact").hexdigest(),
        updated_at="2026-08-14T10:39:27Z",
        source_kind="saved_effect",
        selector_label=item.name,
        source_origin_kind=item.origin.kind.value,
        source_content_hash=item.content_hash,
        item_id=item.id,
        item_version=item.version,
    )


def test_diagnostic_contract_redacts_credentials_addresses_documents_and_packets() -> None:
    history = _history()
    history.record(
        DiagnosticStage.FRONTEND_APPLY,
        DiagnosticOutcome.STARTED,
        "apply_requested",
        correlation_id=CORRELATION_ID,
        config_entry_id="AA:BB:CC:DD:EE:FF",
        details={
            "access_token": "top-secret",
            "address_alias": "AA:BB:CC:DD:EE:FF",
            "content": {"name": "saved document"},
            "nested": {"peer": "D0:35:34:12:34:56"},
            "packet": b"\x01\x02credential-body",
            "packet_body": [1, 2, 99, 114, 101, 100, 101, 110, 116, 105, 97, 108],
            "raw": "0102736563726574",
            "D5:36:36:12:34:56": "address used as a field name",
            "safe": "model H617A",
        },
    )

    event = history.snapshot()["events"][0]
    blob = str(event)

    assert event["config_entry_id"] == REDACTED
    assert event["details"]["access_token"] == REDACTED
    assert event["details"]["content"] == REDACTED
    assert event["details"]["nested"]["peer"] == REDACTED
    assert event["details"]["packet"] == {"byte_length": 17, "detail": "omitted"}
    assert event["details"]["packet_body"] == {"byte_length": 12, "detail": "omitted"}
    assert "top-secret" not in blob
    assert "AA:BB:CC:DD:EE:FF" not in blob
    assert "D5:36:36:12:34:56" not in blob
    assert "saved document" not in blob
    assert "0102736563726574" not in blob


def test_opt_in_packet_detail_is_hash_only() -> None:
    history = _history(include_packet_details=True)
    packet = b"\x01\x02credential-body"
    history.record(
        DiagnosticStage.PACKET_PROGRESS,
        DiagnosticOutcome.PROGRESS,
        "packet_upload_progress",
        correlation_id=CORRELATION_ID,
        details={"packet": packet},
    )

    packet_detail = history.snapshot()["events"][0]["details"]["packet"]

    assert packet_detail == {
        "byte_length": len(packet),
        "sha256": sha256(packet).hexdigest(),
    }
    assert packet.hex() not in str(packet_detail)


def test_packet_hashing_work_is_bounded() -> None:
    history = _history(include_packet_details=True)
    packet = b"x" * (MAX_DIAGNOSTIC_PACKET_HASH_BYTES + 100)
    history.record(
        DiagnosticStage.PACKET_PROGRESS,
        DiagnosticOutcome.PROGRESS,
        "packet_upload_progress",
        correlation_id=CORRELATION_ID,
        details={"packet": packet},
    )

    packet_detail = history.snapshot()["events"][0]["details"]["packet"]

    assert packet_detail["byte_length"] == len(packet)
    assert packet_detail["sample_bytes"] == MAX_DIAGNOSTIC_PACKET_HASH_BYTES
    assert packet_detail["sample_sha256"] == sha256(packet[:MAX_DIAGNOSTIC_PACKET_HASH_BYTES]).hexdigest()
    assert packet_detail["truncated"] is True
    assert "sha256" not in packet_detail


def test_diagnostic_history_and_detail_values_are_bounded() -> None:
    history = _history()
    for index in range(MAX_DIAGNOSTIC_EVENTS + 5):
        _record(history, index)
    history.record(
        DiagnosticStage.COMPILATION,
        DiagnosticOutcome.FAILED,
        "compile_failed",
        correlation_id=CORRELATION_ID,
        details={
            **{f"z_field_{index:02d}": index for index in range(MAX_DIAGNOSTIC_DETAIL_FIELDS + 4)},
            "a_items": list(range(MAX_DIAGNOSTIC_COLLECTION_ITEMS + 10)),
            "b_text": "x" * (MAX_DIAGNOSTIC_STRING_LENGTH + 50),
        },
    )

    snapshot = history.snapshot()
    event = snapshot["events"][-1]

    assert len(snapshot["events"]) == MAX_DIAGNOSTIC_EVENTS
    assert snapshot["events"][0]["sequence"] == 7
    assert len(event["details"]) == MAX_DIAGNOSTIC_DETAIL_FIELDS
    assert event["details"]["truncated_fields"] == 7
    assert len(event["details"]["a_items"]) == MAX_DIAGNOSTIC_COLLECTION_ITEMS
    assert len(event["details"]["b_text"]) == MAX_DIAGNOSTIC_STRING_LENGTH


def test_progress_coalescing_preserves_other_stages() -> None:
    history = _history()
    history.record(
        DiagnosticStage.COMPILATION,
        DiagnosticOutcome.SUCCEEDED,
        "artifact_compiled",
        correlation_id=CORRELATION_ID,
    )
    for index in range(20):
        history.record(
            DiagnosticStage.PACKET_PROGRESS,
            DiagnosticOutcome.PROGRESS,
            "packet_upload_progress",
            correlation_id=CORRELATION_ID,
            details={"current": index, "total": 20},
            coalesce=True,
        )

    events = history.snapshot()["events"]

    assert len(events) == 2
    assert events[-1]["details"] == {"current": 19, "total": 20}


def test_schema_and_evidence_gap_presentation_are_stable() -> None:
    history = _history()
    history.record_evidence_gap(
        "unsupported_capability",
        correlation_id=CORRELATION_ID,
        config_entry_id="entry-a",
        details={"capability": "workshop"},
    )

    snapshot = history.snapshot()
    event = snapshot["events"][0]

    assert set(snapshot) == {"schema_version", "limits", "events"}
    assert snapshot["schema_version"] == 1
    assert snapshot["limits"] == {
        "event_count": MAX_DIAGNOSTIC_EVENTS,
        "detail_fields": MAX_DIAGNOSTIC_DETAIL_FIELDS,
        "collection_items": MAX_DIAGNOSTIC_COLLECTION_ITEMS,
        "string_length": MAX_DIAGNOSTIC_STRING_LENGTH,
        "detail_depth": 4,
        "packet_hash_bytes": MAX_DIAGNOSTIC_PACKET_HASH_BYTES,
        "packet_detail": "omitted",
    }
    assert set(event) == {
        "sequence",
        "timestamp",
        "correlation_id",
        "stage",
        "outcome",
        "code",
        "presentation",
        "config_entry_id",
        "operation_id",
        "details",
    }
    assert event["timestamp"] == "2026-08-14T10:39:27.000Z"
    assert event["stage"] == "evidence_gap"
    assert event["outcome"] == "informational"
    assert event["presentation"] == DiagnosticPresentation.DIAGNOSTIC_ONLY.value


def test_snapshot_cannot_mutate_retained_nested_details() -> None:
    history = _history()
    history.record(
        DiagnosticStage.COMPILATION,
        DiagnosticOutcome.SUCCEEDED,
        "artifact_compiled",
        correlation_id=CORRELATION_ID,
        details={"nested": {"compiler_version": 1}},
    )

    first = history.snapshot()
    first["events"][0]["details"]["nested"]["compiler_version"] = 999

    assert history.snapshot()["events"][0]["details"]["nested"]["compiler_version"] == 1


async def test_deployment_bridge_records_bounded_transition_summary() -> None:
    repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
    initial = await repository.async_load()
    history = _history()
    bridge = EffectDeploymentDiagnosticBridge(repository, history, initial)
    pending = _deployment()

    await repository.async_put(
        replace(pending, phase=DeploymentPhase.COMPILING),
        expected_version=None,
    )
    await repository.async_put(pending, expected_version=None)
    for current in range(4):
        await repository.async_put(
            replace(
                pending,
                phase=DeploymentPhase.UPLOADING,
                progress_current=current,
                progress_total=3,
            ),
            expected_version=None,
        )
    await repository.async_put(
        replace(
            pending,
            phase=DeploymentPhase.ACTIVATING,
            progress_current=3,
            progress_total=3,
        ),
        expected_version=None,
    )
    await repository.async_put(
        replace(
            pending,
            phase=DeploymentPhase.VERIFYING,
            progress_current=3,
            progress_total=3,
        ),
        expected_version=None,
    )
    await repository.async_put(
        replace(
            pending,
            phase=DeploymentPhase.RECOVERING,
            progress_current=3,
            progress_total=3,
            error_code="device_state_unconfirmed",
        ),
        expected_version=None,
    )
    await repository.async_put(
        replace(
            pending,
            phase=DeploymentPhase.UNCERTAIN,
            progress_current=3,
            progress_total=3,
            error_code="device_state_unconfirmed",
        ),
        expected_version=None,
    )

    events = history.snapshot(config_entry_id="entry-a")["events"]
    bridge.close()

    assert [event["stage"] for event in events] == [
        "compilation",
        "compilation",
        "packet_progress",
        "packet_progress",
        "verification",
        "recovery",
        "evidence_gap",
    ]
    assert events[2]["details"] == {"current": 3, "total": 3}
    assert events[-1]["presentation"] == "diagnostic_only"


async def test_scene_compiler_evidence_is_diagnostic_only() -> None:
    repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
    initial = await repository.async_load()
    history = _history()
    bridge = EffectDeploymentDiagnosticBridge(repository, history, initial)
    scene = replace(
        _deployment(DeploymentPhase.COMPILING),
        target_mode="scene",
        target_effect="forest",
        evidence_codes=(
            "scene_payload_readback_unavailable",
            "layered_field_semantics_uncalibrated",
        ),
    )

    await repository.async_put(scene, expected_version=None)
    events = history.snapshot(config_entry_id="entry-a")["events"]
    bridge.close()

    assert [event["code"] for event in events] == [
        "artifact_compiled",
        "scene_payload_readback_unavailable",
        "layered_field_semantics_uncalibrated",
    ]
    assert all(event["presentation"] == "diagnostic_only" for event in events[1:])


async def test_upload_only_application_emits_bounded_evidence_gap() -> None:
    repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
    initial = await repository.async_load()
    history = _history()
    bridge = EffectDeploymentDiagnosticBridge(repository, history, initial)

    await repository.async_put(
        replace(
            _deployment(),
            diy_code=None,
            phase=DeploymentPhase.APPLIED,
            progress_current=2,
            progress_total=2,
            verification_confidence=ObservationConfidence.WRITE_COMPLETED,
        ),
        expected_version=None,
    )

    event = history.snapshot(config_entry_id="entry-a")["events"][0]
    bridge.close()

    assert event["stage"] == "evidence_gap"
    assert event["code"] == "application_write_completed"
    assert event["details"] == {
        "confidence": "write_completed",
        "packets_sent": 2,
        "verification": "device_readback_unavailable",
    }
