from __future__ import annotations

import json
from pathlib import Path

import pytest

from govee_relay.events import EventSink, EventType
from govee_relay.http_wire import gzip_payload
from govee_relay.redaction import (
    endpoint_candidates,
    extract_response_schema,
    serialised_schema_contains,
)

PRIVATE_KEY = (
    "-----BEGIN PRIVATE KEY-----ABcd0123+/EfGh4567IjKl89MnOpQrStUvWxYzABcd0123+/EfGh4567IjKl89-----END PRIVATE KEY-----"
)
CERTIFICATE = "-----BEGIN CERTIFICATE-----" + "B" * 80 + "-----END CERTIFICATE-----"
ENDPOINT = "mqtt.example.invalid"
DEVICE = "AA:BB:CC:DD:EE:FF"


def response_payload() -> bytearray:
    return bytearray(
        json.dumps(
            {
                "code": 200,
                "data": {
                    "endpoint": ENDPOINT,
                    "certificatePem": CERTIFICATE,
                    "privateKey": PRIVATE_KEY,
                    "device": DEVICE,
                    "topics": {"GA/dynamic/control": "device/topic"},
                    "devices": {DEVICE: {"publishTopic": "device/topic"}},
                },
            }
        ).encode()
    )


def test_json_schema_contains_no_values():
    schema = extract_response_schema(
        response_payload(),
        content_type="application/json",
    )
    rendered = json.dumps(schema.as_event(), sort_keys=True)
    for secret in (PRIVATE_KEY, CERTIFICATE, ENDPOINT, DEVICE, "device/topic"):
        assert secret not in rendered
        assert not serialised_schema_contains(schema, secret)
    endpoint = next(fact for fact in schema.facts if fact.path == "data.endpoint")
    key = next(fact for fact in schema.facts if fact.path == "data.privateKey")
    assert endpoint.string_class == "hostname-like"
    assert endpoint.correlation_sha256 is None
    assert key.correlation_sha256 is not None
    paths = {fact.path for fact in schema.facts}
    assert "data.topics.<key#0>" in paths
    assert "data.devices.<key#0>" in paths
    assert all("GA/dynamic/control" not in path and DEVICE not in path for path in paths)


def test_gzip_json_schema_is_extracted_without_changing_relay_payload():
    encoded = bytearray(gzip_payload(bytes(response_payload())))
    original = bytes(encoded)
    schema = extract_response_schema(
        encoded,
        content_type="application/json",
        content_encoding="gzip",
    )
    assert schema.encoding == "json"
    assert any(fact.path == "data.endpoint" for fact in schema.facts)
    assert bytes(encoded) == original
    assert endpoint_candidates(
        encoded,
        content_type="application/json",
        content_encoding="gzip",
    ) == (ENDPOINT,)


def test_unsupported_content_encoding_is_rejected():
    with pytest.raises(ValueError, match="unsupported content encoding"):
        extract_response_schema(
            response_payload(),
            content_type="application/json",
            content_encoding="br",
        )


def test_non_json_retains_only_shape():
    payload = bytearray(b"\x00fabricated-binary-secret\xff")
    schema = extract_response_schema(
        payload,
        content_type="application/octet-stream",
    )
    assert schema.encoding == "non-json"
    assert schema.body_length == len(payload)
    assert schema.body_sha256
    assert schema.facts == ()


def test_event_file_is_private_and_secret_free(tmp_path: Path):
    path = tmp_path / "events" / "events.jsonl"
    schema = extract_response_schema(
        response_payload(),
        content_type="application/json",
    )
    with EventSink(path) as sink:
        sink.record(EventType.RESPONSE_SCHEMA, schema=schema.as_event())
    text = path.read_text()
    assert path.stat().st_mode & 0o777 == 0o600
    for secret in (PRIVATE_KEY, CERTIFICATE, ENDPOINT, DEVICE, "device/topic"):
        assert secret not in text


def test_event_sink_rejects_raw_bytes_and_unknown_fields(tmp_path: Path):
    path = tmp_path / "events.jsonl"
    with EventSink(path) as sink:
        try:
            sink.record(EventType.STOP, run_id="run-1", reason=b"raw")
        except ValueError as error:
            assert "raw bytes" in str(error)
        else:
            raise AssertionError("raw event bytes were accepted")

        try:
            sink.record(EventType.STOP, run_id="run-1", reason="done", extra=True)
        except ValueError as error:
            assert "unexpected fields" in str(error)
        else:
            raise AssertionError("unknown event fields were accepted")


def test_event_sink_rejects_unsafe_schema_path(tmp_path: Path):
    path = tmp_path / "events.jsonl"
    with EventSink(path) as sink:
        with pytest.raises(ValueError, match="unsafe key segment"):
            sink.record(
                EventType.RESPONSE_SCHEMA,
                run_id="run-1",
                schema={
                    "encoding": "json",
                    "body_length": 1,
                    "facts": [{"path": "data.AA:BB:CC", "value_type": "object"}],
                },
            )
