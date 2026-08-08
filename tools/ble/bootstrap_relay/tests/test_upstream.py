from __future__ import annotations

import json
import socket
import ssl
import threading
import time
from pathlib import Path

import pytest

from govee_relay.events import EventSink
from govee_relay.http_wire import (
    Header,
    UpstreamResponse,
    parse_device_request,
)
from govee_relay.tls_profiles import (
    build_device_server_context,
    build_upstream_context,
    generate_test_certificate,
)
from govee_relay.upstream import (
    RawUpstreamClient,
    SingleFlightResponse,
)

from .helpers import start_tls_server
from .test_http_wire import DEVICE_HOST, QUERY, request

UPSTREAM_HOST = "device.govee.com"


def loopback_resolver(port: int):
    return lambda _host, _port: [(socket.AF_INET, ("127.0.0.1", port))]


def test_raw_upstream_request_host_sni_and_bytes(tmp_path: Path):
    files = generate_test_certificate(tmp_path / "upstream", UPSTREAM_HOST)
    server_context = build_device_server_context(files)
    server_context.set_ciphers("DEFAULT:@SECLEVEL=1")
    seen_sni: list[str | None] = []
    seen_request: list[bytes] = []
    server_context.sni_callback = lambda _sock, name, _ctx: seen_sni.append(name)
    response_body = b'{"code":200,"data":{}}'

    def handler(secure: ssl.SSLSocket) -> None:
        payload = bytearray()
        while not payload.endswith(b"\r\n\r\n"):
            payload.extend(secure.recv(1))
        seen_request.append(bytes(payload))
        secure.sendall(
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: application/json\r\n"
            + f"Content-Length: {len(response_body)}\r\n\r\n".encode()
            + response_body
        )

    address, thread = start_tls_server(server_context, handler)
    context = build_upstream_context(ca_file=files.certificate)
    client = RawUpstreamClient(
        host=UPSTREAM_HOST,
        port=address[1],
        context=context,
        resolver=loopback_resolver(address[1]),
        require_public_address=False,
    )
    parsed = parse_device_request(request(), expected_host=DEVICE_HOST)
    client.prewarm()
    response = client.fetch(parsed)
    thread.join(timeout=2)

    assert seen_sni == [UPSTREAM_HOST]
    assert seen_request == [
        b"POST /device/v1/base/config?" + QUERY + b" HTTP/1.1\r\n"
        b"Accept: */*\r\n"
        b"Host: device.govee.com\r\n"
        b"envId: 0\r\n"
        b"iotVersion: 0\r\n\r\n"
    ]
    assert bytes(response.payload) == response_body
    assert client.requests_sent == 1
    assert client.fetch_count == 1


def test_upstream_wrong_hostname_is_rejected(tmp_path: Path):
    files = generate_test_certificate(tmp_path / "wrong-host", "wrong.example")
    server_context = build_device_server_context(files)
    server_context.set_ciphers("DEFAULT:@SECLEVEL=1")
    address, thread = start_tls_server(server_context, lambda _secure: None)
    client = RawUpstreamClient(
        host=UPSTREAM_HOST,
        port=address[1],
        context=build_upstream_context(ca_file=files.certificate),
        resolver=loopback_resolver(address[1]),
        require_public_address=False,
    )
    with pytest.raises(ssl.SSLCertVerificationError):
        client.prewarm()
    thread.join(timeout=2)


def test_single_flight_six_retries_make_one_upstream_call():
    cache = SingleFlightResponse()
    calls = 0
    lock = threading.Lock()
    response = UpstreamResponse(
        b"HTTP/1.1",
        200,
        b"OK",
        (Header(b"Content-Type", b"application/json"),),
        bytearray(b'{"code":200}'),
    )
    results: list[UpstreamResponse] = []

    def fetch() -> UpstreamResponse:
        nonlocal calls
        with lock:
            calls += 1
        time.sleep(0.03)
        return response

    threads = [
        threading.Thread(
            target=lambda: results.append(cache.get("run-1", fetch)),
        )
        for _ in range(6)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=1)

    assert calls == 1
    assert cache.upstream_calls == 1
    assert results == [response] * 6
    cache.clear()
    assert response.payload == bytearray(b"\x00" * len(b'{"code":200}'))
    assert cache.upstream_calls == 1
    with pytest.raises(RuntimeError, match="closed"):
        cache.get("run-1", fetch)


def test_response_cache_cannot_cross_run_ids():
    cache = SingleFlightResponse()
    response = UpstreamResponse(b"HTTP/1.1", 200, b"OK", (), bytearray())
    assert cache.get("run-1", lambda: response) is response
    with pytest.raises(RuntimeError, match="cannot cross"):
        cache.get("run-2", lambda: response)


def test_cache_close_cannot_wake_a_second_fetch():
    cache = SingleFlightResponse()
    started = threading.Event()
    release = threading.Event()
    calls = 0
    errors: list[BaseException] = []

    def fetch() -> UpstreamResponse:
        nonlocal calls
        calls += 1
        started.set()
        release.wait(timeout=1)
        return UpstreamResponse(b"HTTP/1.1", 200, b"OK", (), bytearray(b"x"))

    def worker() -> None:
        try:
            cache.get("run-1", fetch)
        except BaseException as error:
            errors.append(error)

    first = threading.Thread(target=worker)
    second = threading.Thread(target=worker)
    first.start()
    started.wait(timeout=1)
    second.start()
    cache.clear()
    release.set()
    first.join(timeout=1)
    second.join(timeout=1)

    assert calls == 1
    assert len(errors) == 2
    assert all("closed" in str(error) for error in errors)


def test_upstream_events_are_produced(tmp_path: Path):
    files = generate_test_certificate(tmp_path / "events-upstream", UPSTREAM_HOST)
    server_context = build_device_server_context(files)
    server_context.set_ciphers("DEFAULT:@SECLEVEL=1")
    body = b"{}"

    def handler(secure: ssl.SSLSocket) -> None:
        payload = bytearray()
        while not payload.endswith(b"\r\n\r\n"):
            payload.extend(secure.recv(1))
        secure.sendall(
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            + f"Content-Length: {len(body)}\r\n\r\n".encode()
            + body
        )

    address, thread = start_tls_server(server_context, handler)
    event_path = tmp_path / "events.jsonl"
    with EventSink(event_path) as events:
        client = RawUpstreamClient(
            host=UPSTREAM_HOST,
            port=address[1],
            context=build_upstream_context(ca_file=files.certificate),
            resolver=loopback_resolver(address[1]),
            require_public_address=False,
            run_id="run-1",
            events=events,
        )
        client.prewarm()
        client.fetch(parse_device_request(request(), expected_host=DEVICE_HOST))
    thread.join(timeout=2)
    event_types = {json.loads(line)["event"] for line in event_path.read_text().splitlines()}
    assert {"upstream_prewarmed", "upstream_fetched"} <= event_types


def test_prewarm_can_be_replaced_before_any_request(tmp_path: Path):
    first_files = generate_test_certificate(tmp_path / "first", UPSTREAM_HOST)
    second_files = generate_test_certificate(tmp_path / "second", UPSTREAM_HOST)
    first_context = build_device_server_context(first_files)
    second_context = build_device_server_context(second_files)
    first_context.set_ciphers("DEFAULT:@SECLEVEL=1")
    second_context.set_ciphers("DEFAULT:@SECLEVEL=1")
    first_address, first_thread = start_tls_server(first_context, lambda _secure: None)
    body = b"{}"

    def second_handler(secure: ssl.SSLSocket) -> None:
        secure.recv(8192)
        secure.sendall(
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            + f"Content-Length: {len(body)}\r\n\r\n".encode()
            + body
        )

    second_address, second_thread = start_tls_server(
        second_context,
        second_handler,
    )
    bundle = tmp_path / "ca-bundle.pem"
    bundle.write_bytes(first_files.certificate.read_bytes() + second_files.certificate.read_bytes())
    current_port = [first_address[1]]
    client = RawUpstreamClient(
        host=UPSTREAM_HOST,
        port=first_address[1],
        context=build_upstream_context(ca_file=bundle),
        resolver=lambda _host, _port: [(socket.AF_INET, ("127.0.0.1", current_port[0]))],
        require_public_address=False,
    )
    client.prewarm()
    first_thread.join(timeout=2)
    current_port[0] = second_address[1]
    client.port = second_address[1]
    client.prewarm(replace=True)
    response = client.fetch(parse_device_request(request(), expected_host=DEVICE_HOST))
    second_thread.join(timeout=2)
    assert bytes(response.payload) == body


def test_fetch_has_wall_clock_deadline(tmp_path: Path):
    files = generate_test_certificate(tmp_path / "deadline", UPSTREAM_HOST)
    server_context = build_device_server_context(files)
    server_context.set_ciphers("DEFAULT:@SECLEVEL=1")

    def handler(secure: ssl.SSLSocket) -> None:
        secure.recv(8192)
        secure.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\n\r\n")
        for byte in b"slow":
            time.sleep(0.04)
            secure.sendall(bytes([byte]))

    address, thread = start_tls_server(server_context, handler)
    client = RawUpstreamClient(
        host=UPSTREAM_HOST,
        port=address[1],
        context=build_upstream_context(ca_file=files.certificate),
        resolver=loopback_resolver(address[1]),
        require_public_address=False,
        timeout_seconds=0.07,
    )
    client.prewarm()
    with pytest.raises((TimeoutError, socket.timeout)):
        client.fetch(parse_device_request(request(), expected_host=DEVICE_HOST))
    thread.join(timeout=2)
