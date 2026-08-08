from __future__ import annotations

import json
import os
import re
import threading
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


class EventType(StrEnum):
    TLS_ACCEPTED = "tls_accepted"
    REQUEST_SHAPE = "request_shape"
    UPSTREAM_PREWARMED = "upstream_prewarmed"
    UPSTREAM_FETCHED = "upstream_fetched"
    RESPONSE_SCHEMA = "response_schema"
    RESPONSE_MUTATED = "response_mutated"
    RESPONSE_RELAYED = "response_relayed"
    DNS_MATCH = "dns_match"
    MQTT_CLIENT_HELLO = "mqtt_client_hello"
    MQTT_TLS_ACCEPTED = "mqtt_tls_accepted"
    MQTT_TLS_FAILED = "mqtt_tls_failed"
    MQTT_CONNECT_SHAPE = "mqtt_connect_shape"
    EGRESS_DENIED = "egress_denied"
    CONNECTION_FAILED = "connection_failed"
    STOP = "stop"


ALLOWED_FIELDS = {
    EventType.TLS_ACCEPTED: frozenset({"run_id", "tls_version", "cipher"}),
    EventType.REQUEST_SHAPE: frozenset({"run_id", "fingerprint"}),
    EventType.UPSTREAM_PREWARMED: frozenset({"run_id", "duration_ms"}),
    EventType.UPSTREAM_FETCHED: frozenset({"run_id", "status", "duration_ms"}),
    EventType.RESPONSE_SCHEMA: frozenset({"run_id", "schema"}),
    EventType.RESPONSE_MUTATED: frozenset({"run_id", "field", "original_length", "replacement_length"}),
    EventType.RESPONSE_RELAYED: frozenset({"run_id", "status", "body_length"}),
    EventType.DNS_MATCH: frozenset({"run_id", "matched"}),
    EventType.MQTT_CLIENT_HELLO: frozenset(
        {
            "run_id",
            "record_version",
            "client_version",
            "cipher_count",
            "extension_types",
            "sni_present",
            "sni_matched",
        }
    ),
    EventType.MQTT_TLS_ACCEPTED: frozenset({"run_id", "tls_version", "cipher"}),
    EventType.MQTT_TLS_FAILED: frozenset({"run_id", "reason"}),
    EventType.MQTT_CONNECT_SHAPE: frozenset(
        {
            "run_id",
            "protocol_level",
            "remaining_length",
            "clean_session",
            "keepalive",
            "client_id_length",
            "username_present",
            "password_present",
            "will_present",
            "will_qos",
            "will_retain",
        }
    ),
    EventType.EGRESS_DENIED: frozenset({"run_id", "destination_class", "port"}),
    EventType.CONNECTION_FAILED: frozenset({"run_id", "reason"}),
    EventType.STOP: frozenset({"run_id", "reason"}),
}
SAFE_PATH_SEGMENT = re.compile(r"^(?:[A-Za-z_][A-Za-z0-9_]{0,31}|<key#[0-9]+>)(?:\[[0-9]+\])?$")


def _contains_binary(value: Any) -> bool:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return True
    if isinstance(value, dict):
        return any(_contains_binary(key) or _contains_binary(child) for key, child in value.items())
    if isinstance(value, (list, tuple, set)):
        return any(_contains_binary(child) for child in value)
    return False


def _validate_schema_paths(fields: dict[str, Any]) -> None:
    schema = fields.get("schema")
    if not isinstance(schema, dict):
        raise ValueError("response schema event must be a mapping")
    facts = schema.get("facts")
    if not isinstance(facts, list):
        raise ValueError("response schema facts must be a list")
    for fact in facts:
        if not isinstance(fact, dict) or not isinstance(fact.get("path"), str):
            raise ValueError("response schema fact has no safe path")
        path = fact["path"]
        if path and any(not SAFE_PATH_SEGMENT.fullmatch(segment) for segment in path.split(".")):
            raise ValueError("response schema path contains an unsafe key segment")


class EventSink:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            0o600,
        )
        os.chmod(path, 0o600)
        self._handle = os.fdopen(descriptor, "a", encoding="utf-8")
        self._lock = threading.Lock()

    def record(self, event: EventType, **fields: Any) -> None:
        unexpected = frozenset(fields) - ALLOWED_FIELDS[event]
        if unexpected:
            raise ValueError(f"unexpected fields for {event}: {sorted(unexpected)}")
        if _contains_binary(fields):
            raise ValueError("structured events must never contain raw bytes")
        if event is EventType.RESPONSE_SCHEMA:
            _validate_schema_paths(fields)
        row = {
            "at": datetime.now(UTC).isoformat(),
            "event": event,
            **fields,
        }
        rendered = json.dumps(row, sort_keys=True, separators=(",", ":"))
        with self._lock:
            self._handle.write(rendered + "\n")
            self._handle.flush()

    def close(self) -> None:
        with self._lock:
            if not self._handle.closed:
                self._handle.close()

    def __enter__(self) -> EventSink:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
