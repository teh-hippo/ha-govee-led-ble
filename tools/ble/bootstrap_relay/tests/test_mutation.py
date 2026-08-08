from __future__ import annotations

import json
from pathlib import Path

import pytest

from govee_relay.events import EventSink
from govee_relay.http_wire import Header, UpstreamResponse
from govee_relay.mutation import mutate_mqtt_address
from govee_relay.relay import RelayEngine

from .test_http_wire import DEVICE_HOST, request

ORIGINAL_HOST = "mqtt.production.example"
NONCE_HOST = "run-b.nonce.govee.ai.xaz.lol"


def payload() -> bytearray:
    return bytearray(b'{"status":200, "mqttAddress" : "mqtt.production.example","mqttPort":8883,"topic":"unchanged"}')


def test_mqtt_address_mutation_changes_only_one_json_string_token():
    body = payload()
    original = bytes(body)
    mutation = mutate_mqtt_address(
        body,
        content_type="application/json",
        content_encoding="",
        replacement_hostname=NONCE_HOST,
    )

    assert body == original.replace(
        json.dumps(ORIGINAL_HOST).encode(),
        json.dumps(NONCE_HOST).encode(),
    )
    assert mutation.field == "mqttAddress"
    assert mutation.original_length == len(ORIGINAL_HOST)
    assert mutation.replacement_length == len(NONCE_HOST)
    assert mutation.expected_hostnames == (NONCE_HOST,)
    assert mutation.mqtt_port == 8883


def test_mqtt_address_mutation_rejects_ambiguous_or_encoded_responses():
    duplicate = bytearray(b'{"mqttAddress":"mqtt.production.example","nested":{"mqttAddress":"mqtt.other.example"}}')
    with pytest.raises(ValueError, match="exactly one"):
        mutate_mqtt_address(
            duplicate,
            content_type="application/json",
            content_encoding="",
            replacement_hostname=NONCE_HOST,
        )
    with pytest.raises(ValueError, match="identity"):
        mutate_mqtt_address(
            payload(),
            content_type="application/json",
            content_encoding="gzip",
            replacement_hostname=NONCE_HOST,
        )
    with pytest.raises(ValueError, match="prepared probe port"):
        mutate_mqtt_address(
            payload(),
            content_type="application/json",
            content_encoding="",
            replacement_hostname=NONCE_HOST,
            expected_mqtt_port=1883,
        )


def test_relay_mutation_event_contains_no_endpoint_values(tmp_path: Path):
    events_path = tmp_path / "events.jsonl"
    body = payload()
    candidates: list[tuple[str, ...]] = []

    def fetch(_request):
        return UpstreamResponse(
            b"HTTP/1.1",
            200,
            b"OK",
            (Header(b"Content-Type", b"application/json"),),
            body,
        )

    with EventSink(events_path) as events:
        engine = RelayEngine(
            run_id="run-b",
            device_host=DEVICE_HOST,
            fetch_upstream=fetch,
            events=events,
            on_endpoint_candidates=candidates.append,
            response_mutator=lambda value, content_type, content_encoding: mutate_mqtt_address(
                value,
                content_type=content_type,
                content_encoding=content_encoding,
                replacement_hostname=NONCE_HOST,
            ),
        )
        rendered = engine.handle(request())
        engine.close()

    assert NONCE_HOST.encode() in rendered
    assert b'"mqttPort":8883,"topic":"unchanged"' in rendered
    assert candidates == [(NONCE_HOST,)]
    text = events_path.read_text()
    assert '"event":"response_mutated"' in text
    assert ORIGINAL_HOST not in text
    assert NONCE_HOST not in text
    assert body == bytearray(b"\x00" * len(body))
