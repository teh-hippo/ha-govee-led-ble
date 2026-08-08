from __future__ import annotations

import json
import socket
from pathlib import Path

from govee_relay.events import EventSink
from govee_relay.http_wire import Header, UpstreamResponse
from govee_relay.relay import LoopbackTlsRelay, RelayEngine
from govee_relay.tls_profiles import (
    DEVICE_CIPHER,
    build_device_server_context,
    build_test_client_context,
    generate_test_certificate,
)

from .helpers import read_to_end
from .test_http_wire import DEVICE_HOST, request


def test_loopback_relay_tls_parity_and_single_flight(tmp_path: Path):
    files = generate_test_certificate(tmp_path / "device-cert", DEVICE_HOST)
    events_path = tmp_path / "events.jsonl"
    calls = 0
    body = bytearray(b'{"code":200,"data":{"endpoint":"mqtt.example.invalid","privateKey":"fabricated-secret"}}')
    original_body = bytes(body)

    def fetch(_request):
        nonlocal calls
        calls += 1
        return UpstreamResponse(
            b"HTTP/1.1",
            200,
            b"OK",
            (Header(b"Content-Type", b"application/json"),),
            body,
        )

    with EventSink(events_path) as events:
        engine = RelayEngine(
            run_id="run-1",
            device_host=DEVICE_HOST,
            fetch_upstream=fetch,
            events=events,
        )
        with LoopbackTlsRelay(
            context=build_device_server_context(files),
            engine=engine,
        ) as relay:
            client_context = build_test_client_context(files.certificate)
            replies = []
            for _ in range(6):
                with socket.create_connection(relay.address) as raw:
                    with client_context.wrap_socket(
                        raw,
                        server_hostname=DEVICE_HOST,
                    ) as secure:
                        cipher = secure.cipher()
                        assert cipher is not None
                        assert cipher[0] == DEVICE_CIPHER
                        secure.sendall(request())
                        replies.append(read_to_end(secure))

    assert calls == 1
    assert all(reply.endswith(original_body) for reply in replies)
    rows = [json.loads(line) for line in events_path.read_text().splitlines()]
    assert sum(row["event"] == "response_schema" for row in rows) == 1
    assert sum(row["event"] == "tls_accepted" for row in rows) == 6
    text = events_path.read_text()
    assert "fabricated-secret" not in text
    assert "mqtt.example.invalid" not in text
    assert body == bytearray(b"\x00" * len(body))


def test_proven_503_device_response_parity():
    payload = bytearray(b'{"error":"controlled endpoint"}')
    response = UpstreamResponse(
        b"HTTP/1.0",
        503,
        b"Service Unavailable",
        (Header(b"Content-Type", b"application/json"),),
        payload,
    )
    from govee_relay.http_wire import build_device_response

    rendered = build_device_response(response)
    assert rendered == (
        b"HTTP/1.0 503 Service Unavailable\r\n"
        b"Content-Type: application/json\r\n"
        b"Content-Length: 31\r\n\r\n"
        b'{"error":"controlled endpoint"}'
    )


def test_upstream_failure_closes_device_connection(tmp_path: Path):
    files = generate_test_certificate(tmp_path / "failure-cert", DEVICE_HOST)
    events_path = tmp_path / "events.jsonl"

    def fail(_request):
        raise RuntimeError("synthetic upstream failure")

    with EventSink(events_path) as events:
        engine = RelayEngine(
            run_id="run-failure",
            device_host=DEVICE_HOST,
            fetch_upstream=fail,
            events=events,
        )
        with LoopbackTlsRelay(
            context=build_device_server_context(files),
            engine=engine,
        ) as relay:
            client_context = build_test_client_context(files.certificate)
            with socket.create_connection(relay.address) as raw:
                raw.settimeout(1)
                with client_context.wrap_socket(
                    raw,
                    server_hostname=DEVICE_HOST,
                ) as secure:
                    secure.sendall(request())
                    assert secure.recv(1) == b""

    rows = [json.loads(line) for line in events_path.read_text().splitlines()]
    assert any(row["event"] == "connection_failed" and row["reason"] == "RuntimeError" for row in rows)
