from __future__ import annotations

import json
import socket
import ssl
from pathlib import Path

from govee_relay.orchestrator import RunAComponents
from govee_relay.tls_profiles import (
    build_device_server_context,
    build_test_client_context,
    build_upstream_context,
    generate_test_certificate,
)
from govee_relay.upstream import RawUpstreamClient

from .helpers import read_to_end, start_tls_server
from .test_http_wire import DEVICE_HOST, request
from .test_observer import dns_query
from .test_upstream import UPSTREAM_HOST, loopback_resolver


def test_run_a_components_wire_response_endpoint_to_dns_observer(tmp_path: Path):
    upstream_files = generate_test_certificate(
        tmp_path / "upstream",
        UPSTREAM_HOST,
    )
    upstream_context = build_device_server_context(upstream_files)
    upstream_context.set_ciphers("DEFAULT:@SECLEVEL=1")
    body = b'{"code":200,"data":{"endpoint":"run-123.nonce.invalid"}}'

    def upstream_handler(secure: ssl.SSLSocket) -> None:
        request_bytes = bytearray()
        while not request_bytes.endswith(b"\r\n\r\n"):
            request_bytes.extend(secure.recv(1))
        secure.sendall(
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            + f"Content-Length: {len(body)}\r\n\r\n".encode()
            + body
        )

    upstream_address, upstream_thread = start_tls_server(
        upstream_context,
        upstream_handler,
    )
    upstream = RawUpstreamClient(
        host=UPSTREAM_HOST,
        port=upstream_address[1],
        context=build_upstream_context(ca_file=upstream_files.certificate),
        resolver=loopback_resolver(upstream_address[1]),
        require_public_address=False,
        run_id="run-1",
    )
    device_files = generate_test_certificate(tmp_path / "device", DEVICE_HOST)
    event_path = tmp_path / "events.jsonl"

    with RunAComponents(
        run_id="run-1",
        device_host=DEVICE_HOST,
        device_context=build_device_server_context(device_files),
        upstream=upstream,
        event_path=event_path,
    ) as components:
        client_context = build_test_client_context(device_files.certificate)
        with socket.create_connection(components.relay.address) as raw:
            with client_context.wrap_socket(
                raw,
                server_hostname=DEVICE_HOST,
            ) as secure:
                secure.sendall(request())
                assert read_to_end(secure).endswith(body)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as dns_client:
            dns_client.settimeout(1)
            dns_client.sendto(
                dns_query("run-123.nonce.invalid"),
                components.dns.address,
            )
            dns_client.recvfrom(4096)

    upstream_thread.join(timeout=2)
    event_types = {json.loads(line)["event"] for line in event_path.read_text().splitlines()}
    assert {
        "upstream_prewarmed",
        "tls_accepted",
        "request_shape",
        "upstream_fetched",
        "response_schema",
        "response_relayed",
        "dns_match",
    } <= event_types
    assert "run-123.nonce.invalid" not in event_path.read_text()
