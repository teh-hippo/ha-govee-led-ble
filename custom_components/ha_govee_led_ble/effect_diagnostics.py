"""Bounded, redacted diagnostics for custom-effect operations."""

from __future__ import annotations

import copy
import math
import re
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from threading import RLock
from typing import Any, Final
from uuid import UUID, uuid4

DIAGNOSTIC_SCHEMA_VERSION: Final = 1
MAX_DIAGNOSTIC_EVENTS: Final = 100
MAX_DIAGNOSTIC_DETAIL_FIELDS: Final = 16
MAX_DIAGNOSTIC_COLLECTION_ITEMS: Final = 16
MAX_DIAGNOSTIC_STRING_LENGTH: Final = 256
MAX_DIAGNOSTIC_DETAIL_DEPTH: Final = 4
MAX_DIAGNOSTIC_PACKET_HASH_BYTES: Final = 4096

_REDACTED: Final = "**REDACTED**"
_TRUNCATED: Final = "**TRUNCATED**"
_CODE_PATTERN: Final = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_BLE_ADDRESS_PATTERN: Final = re.compile(r"(?i)(?<![0-9a-f])(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}(?![0-9a-f])")
_SENSITIVE_KEYS: Final = frozenset(
    {
        "address",
        "api_key",
        "authorization",
        "credential",
        "credentials",
        "password",
        "passphrase",
        "secret",
        "token",
        "unique_id",
    }
)
_DOCUMENT_KEYS: Final = frozenset({"content", "document", "raw_document", "saved_document", "snapshot"})
_PACKET_KEYS: Final = frozenset(
    {
        "activation_packet",
        "body",
        "packet",
        "packet_body",
        "packet_bytes",
        "packets",
        "payload",
        "raw",
        "upload_packets",
    }
)

type DiagnosticValue = str | int | float | bool | None | list["DiagnosticValue"] | dict[str, "DiagnosticValue"]


class DiagnosticStage(StrEnum):
    FRONTEND_APPLY = "frontend_apply"
    API_SERVICE = "api_service"
    COMPILATION = "compilation"
    PACKET_PROGRESS = "packet_progress"
    VERIFICATION = "verification"
    RECOVERY = "recovery"
    EVIDENCE_GAP = "evidence_gap"


class DiagnosticOutcome(StrEnum):
    STARTED = "started"
    PROGRESS = "progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INFORMATIONAL = "informational"


class DiagnosticPresentation(StrEnum):
    STATUS = "status"
    DIAGNOSTIC_ONLY = "diagnostic_only"


@dataclass(frozen=True, slots=True)
class EffectDiagnosticEvent:
    sequence: int
    timestamp: str
    correlation_id: str
    stage: DiagnosticStage
    outcome: DiagnosticOutcome
    code: str
    presentation: DiagnosticPresentation
    config_entry_id: str | None
    operation_id: str | None
    details: dict[str, DiagnosticValue]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
            "stage": self.stage.value,
            "outcome": self.outcome.value,
            "code": self.code,
            "presentation": self.presentation.value,
            "config_entry_id": self.config_entry_id,
            "operation_id": self.operation_id,
            "details": copy.deepcopy(self.details),
        }


class EffectDiagnosticHistory:
    """Keep recent operation events without retaining user or wire content."""

    def __init__(
        self,
        *,
        maximum_events: int = MAX_DIAGNOSTIC_EVENTS,
        include_packet_details: bool = False,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not 1 <= maximum_events <= MAX_DIAGNOSTIC_EVENTS:
            raise ValueError(f"maximum_events must be from 1 to {MAX_DIAGNOSTIC_EVENTS}")
        self._maximum_events = maximum_events
        self._include_packet_details = include_packet_details
        self._clock = clock or _utcnow
        self._events: deque[EffectDiagnosticEvent] = deque(maxlen=maximum_events)
        self._sequence = 0
        self._lock = RLock()

    def record(
        self,
        stage: DiagnosticStage,
        outcome: DiagnosticOutcome,
        code: str,
        *,
        correlation_id: str | UUID | None = None,
        config_entry_id: str | None = None,
        operation_id: str | UUID | None = None,
        details: Mapping[str, object] | None = None,
        presentation: DiagnosticPresentation = DiagnosticPresentation.STATUS,
        coalesce: bool = False,
    ) -> str:
        if not _CODE_PATTERN.fullmatch(code):
            raise ValueError("diagnostic code must be lower snake case and at most 64 characters")
        canonical_correlation_id = normalise_correlation_id(correlation_id)
        canonical_operation_id = None if operation_id is None else normalise_correlation_id(operation_id)
        if stage is DiagnosticStage.EVIDENCE_GAP:
            presentation = DiagnosticPresentation.DIAGNOSTIC_ONLY
        safe_details = _sanitise_mapping(details or {}, include_packet_details=self._include_packet_details)
        with self._lock:
            self._sequence += 1
            event = EffectDiagnosticEvent(
                sequence=self._sequence,
                timestamp=_timestamp(self._clock()),
                correlation_id=canonical_correlation_id,
                stage=stage,
                outcome=outcome,
                code=code,
                presentation=presentation,
                config_entry_id=_bounded_identifier(config_entry_id),
                operation_id=canonical_operation_id,
                details=safe_details,
            )
            if coalesce:
                self._events = deque(
                    (
                        current
                        for current in self._events
                        if not (
                            current.correlation_id == canonical_correlation_id
                            and current.stage is stage
                            and current.code == code
                        )
                    ),
                    maxlen=self._maximum_events,
                )
            self._events.append(event)
        return canonical_correlation_id

    def record_evidence_gap(
        self,
        code: str,
        *,
        correlation_id: str | UUID | None = None,
        config_entry_id: str | None = None,
        operation_id: str | UUID | None = None,
        details: Mapping[str, object] | None = None,
    ) -> str:
        return self.record(
            DiagnosticStage.EVIDENCE_GAP,
            DiagnosticOutcome.INFORMATIONAL,
            code,
            correlation_id=correlation_id,
            config_entry_id=config_entry_id,
            operation_id=operation_id,
            details=details,
        )

    def snapshot(self, *, config_entry_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            events = tuple(self._events)
        if config_entry_id is not None:
            events = tuple(event for event in events if event.config_entry_id == config_entry_id)
        return _snapshot(self._maximum_events, self._include_packet_details, events)


def new_correlation_id() -> str:
    return str(uuid4())


def normalise_correlation_id(value: str | UUID | None) -> str:
    if value is None:
        return new_correlation_id()
    try:
        return str(UUID(str(value)))
    except ValueError as exc:
        raise ValueError("correlation ID must be a UUID") from exc


def empty_effect_diagnostic_snapshot() -> dict[str, Any]:
    return _snapshot(MAX_DIAGNOSTIC_EVENTS, False, ())


def _snapshot(
    maximum_events: int,
    include_packet_details: bool,
    events: Sequence[EffectDiagnosticEvent],
) -> dict[str, Any]:
    return {
        "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
        "limits": {
            "event_count": maximum_events,
            "detail_fields": MAX_DIAGNOSTIC_DETAIL_FIELDS,
            "collection_items": MAX_DIAGNOSTIC_COLLECTION_ITEMS,
            "string_length": MAX_DIAGNOSTIC_STRING_LENGTH,
            "detail_depth": MAX_DIAGNOSTIC_DETAIL_DEPTH,
            "packet_hash_bytes": MAX_DIAGNOSTIC_PACKET_HASH_BYTES,
            "packet_detail": "hashed" if include_packet_details else "omitted",
        },
        "events": [event.to_dict() for event in events],
    }


def _sanitise_mapping(
    value: Mapping[str, object],
    *,
    include_packet_details: bool,
    depth: int = 0,
) -> dict[str, DiagnosticValue]:
    if depth >= MAX_DIAGNOSTIC_DETAIL_DEPTH:
        return {"truncated": _TRUNCATED}
    items = sorted(((str(key), item) for key, item in value.items()), key=lambda item: item[0])
    truncated = max(0, len(items) - (MAX_DIAGNOSTIC_DETAIL_FIELDS - 1))
    if truncated:
        items = items[: MAX_DIAGNOSTIC_DETAIL_FIELDS - 1]
    result: dict[str, DiagnosticValue] = {}
    for index, (key, item) in enumerate(items):
        safe_key = key if _CODE_PATTERN.fullmatch(key) and not _BLE_ADDRESS_PATTERN.search(key) else f"field_{index}"
        result[safe_key] = _sanitise_value(
            item,
            key=key,
            include_packet_details=include_packet_details,
            depth=depth + 1,
        )
    if truncated:
        result["truncated_fields"] = truncated
    return result


def _sanitise_value(
    value: object,
    *,
    key: str,
    include_packet_details: bool,
    depth: int,
) -> DiagnosticValue:
    normalised_key = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
    key_parts = frozenset(normalised_key.split("_"))
    if normalised_key in _DOCUMENT_KEYS or normalised_key in _SENSITIVE_KEYS or key_parts.intersection(_SENSITIVE_KEYS):
        return _REDACTED
    if normalised_key in _PACKET_KEYS:
        return _packet_value_metadata(value, include_packet_details=include_packet_details)
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else _REDACTED
    if isinstance(value, str):
        if _BLE_ADDRESS_PATTERN.search(value):
            return _REDACTED
        return (
            value
            if len(value) <= MAX_DIAGNOSTIC_STRING_LENGTH
            else f"{value[: MAX_DIAGNOSTIC_STRING_LENGTH - len(_TRUNCATED)]}{_TRUNCATED}"
        )
    if isinstance(value, bytes | bytearray | memoryview):
        return _packet_metadata(value, include_packet_details=include_packet_details)
    if isinstance(value, Mapping):
        return _sanitise_mapping(value, include_packet_details=include_packet_details, depth=depth)
    if isinstance(value, Sequence):
        if depth >= MAX_DIAGNOSTIC_DETAIL_DEPTH:
            return [_TRUNCATED]
        values = list(value[:MAX_DIAGNOSTIC_COLLECTION_ITEMS])
        result = [
            _sanitise_value(
                item,
                key=key,
                include_packet_details=include_packet_details,
                depth=depth + 1,
            )
            for item in values
        ]
        if len(value) > MAX_DIAGNOSTIC_COLLECTION_ITEMS:
            result[-1] = _TRUNCATED
        return result
    return f"<{type(value).__name__}>"


def _packet_metadata(
    value: str | bytes | bytearray | memoryview,
    *,
    include_packet_details: bool,
) -> dict[str, DiagnosticValue]:
    body = value.encode() if isinstance(value, str) else bytes(value)
    metadata: dict[str, DiagnosticValue] = {"byte_length": len(body)}
    if include_packet_details:
        sample = body[:MAX_DIAGNOSTIC_PACKET_HASH_BYTES]
        if len(sample) == len(body):
            metadata["sha256"] = sha256(sample).hexdigest()
        else:
            metadata["sample_bytes"] = len(sample)
            metadata["sample_sha256"] = sha256(sample).hexdigest()
            metadata["truncated"] = True
    else:
        metadata["detail"] = "omitted"
    return metadata


def _packet_value_metadata(
    value: object,
    *,
    include_packet_details: bool,
) -> dict[str, DiagnosticValue]:
    if isinstance(value, str | bytes | bytearray | memoryview):
        return _packet_metadata(value, include_packet_details=include_packet_details)
    if isinstance(value, Sequence):
        sample = value[:MAX_DIAGNOSTIC_PACKET_HASH_BYTES]
        if all(isinstance(item, int) and not isinstance(item, bool) and 0 <= item <= 0xFF for item in sample):
            metadata = _packet_metadata(bytes(sample), include_packet_details=include_packet_details)
            metadata["byte_length"] = len(value)
            if len(value) > MAX_DIAGNOSTIC_PACKET_HASH_BYTES:
                if include_packet_details:
                    metadata["sample_bytes"] = len(sample)
                    metadata["sample_sha256"] = metadata.pop("sha256")
                metadata["truncated"] = True
            return metadata
        return {
            "detail": "hashed_items" if include_packet_details else "omitted",
            "item_count": len(value),
        }
    return {"detail": "omitted"}


def _bounded_identifier(value: str | None) -> str | None:
    if value is None:
        return None
    if _BLE_ADDRESS_PATTERN.search(value):
        return _REDACTED
    return value[:MAX_DIAGNOSTIC_STRING_LENGTH]


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _utcnow() -> datetime:
    return datetime.now(UTC)
