from __future__ import annotations

import json
import socket
import ssl
import threading
import time
from pathlib import Path

import pytest

from govee_relay.live import UPSTREAM_HOST, LiveConfig, assert_swap_disabled, preflight, run_live, swap_total_kib
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
from .test_upstream import loopback_resolver


def test_swap_guard_reads_meminfo(tmp_path: Path):
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal: 1000 kB\nSwapTotal: 0 kB\n")
    assert swap_total_kib(meminfo) == 0
    assert_swap_disabled(meminfo)
    meminfo.write_text("MemTotal: 1000 kB\nSwapTotal: 1024 kB\n")
    with pytest.raises(RuntimeError, match="swap"):
        assert_swap_disabled(meminfo)


def test_live_config_rejects_unsafe_run_id(tmp_path: Path):
    config = LiveConfig(
        run_id="../unsafe",
        device_host="govee.ai.xaz.lol",
        relay_ip="192.0.2.10",
        work_dir=tmp_path,
        event_path=tmp_path / "events.jsonl",
        state_path=tmp_path / "state.json",
    )
    with pytest.raises(ValueError, match="run ID"):
        config.validate()


def test_live_config_requires_derived_nonce_and_dns_stop(tmp_path: Path):
    with pytest.raises(ValueError, match="derived"):
        LiveConfig(
            run_id="run-b",
            device_host="govee.ai.xaz.lol",
            relay_ip="192.0.2.10",
            work_dir=tmp_path,
            event_path=tmp_path / "events.jsonl",
            state_path=tmp_path / "state.json",
            mqtt_address_nonce="wrong.nonce.example",
            stop_on_dns_match=True,
        ).validate()
    with pytest.raises(ValueError, match="nonce DNS or ClientHello"):
        LiveConfig(
            run_id="run-b",
            device_host="govee.ai.xaz.lol",
            relay_ip="192.0.2.10",
            work_dir=tmp_path,
            event_path=tmp_path / "events.jsonl",
            state_path=tmp_path / "state.json",
            mqtt_address_nonce="run-b.nonce.govee.ai.xaz.lol",
        ).validate()
    with pytest.raises(ValueError, match="probe port"):
        LiveConfig(
            run_id="run-d",
            device_host="govee.ai.xaz.lol",
            relay_ip="192.0.2.10",
            work_dir=tmp_path,
            event_path=tmp_path / "events.jsonl",
            state_path=tmp_path / "state.json",
            mqtt_address_nonce="run-d.nonce.govee.ai.xaz.lol",
            capture_mqtt_connect=True,
        ).validate()


def test_preflight_builds_exact_device_tls_without_production(tmp_path: Path):
    result = preflight(
        device_host="govee.ai.xaz.lol",
        work_dir=tmp_path,
        production_tls=False,
    )
    rendered = json.dumps(result)
    assert '"cipher": "AES256-SHA256"' in rendered
    assert '"certificate": "RSA-2048"' in rendered
    assert result["production_tls_prewarm"] is False
    assert not (tmp_path / "preflight-certificate").exists()


def test_live_runner_rehearses_relay_dns_ntp_and_cleanup(tmp_path: Path):
    upstream_files = generate_test_certificate(tmp_path / "upstream", UPSTREAM_HOST)
    upstream_context = build_device_server_context(upstream_files)
    upstream_context.set_ciphers("DEFAULT:@SECLEVEL=1")
    body = b'{"code":200,"data":{"endpoint":"run-123.nonce.invalid"}}'

    def upstream_handler(secure: ssl.SSLSocket) -> None:
        head = bytearray()
        while not head.endswith(b"\r\n\r\n"):
            head.extend(secure.recv(1))
        secure.sendall(
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            + f"Content-Length: {len(body)}\r\n\r\n".encode()
            + body
        )

    upstream_address, upstream_thread = start_tls_server(upstream_context, upstream_handler)

    def upstream_factory(_config: LiveConfig) -> RawUpstreamClient:
        return RawUpstreamClient(
            host=UPSTREAM_HOST,
            port=upstream_address[1],
            context=build_upstream_context(ca_file=upstream_files.certificate),
            resolver=loopback_resolver(upstream_address[1]),
            require_public_address=False,
        )

    work_dir = tmp_path / "live"
    state_path = work_dir / "state.json"
    event_path = work_dir / "events.jsonl"
    config = LiveConfig(
        run_id="run-1",
        device_host=DEVICE_HOST,
        relay_ip="192.0.2.10",
        work_dir=work_dir,
        event_path=event_path,
        state_path=state_path,
        relay_host="127.0.0.1",
        relay_port=0,
        dns_host="127.0.0.1",
        dns_port=0,
        ntp_host="127.0.0.1",
        ntp_port=0,
        deadline_seconds=1.5,
        prewarm_refresh_seconds=1,
        stop_on_dns_match=True,
    )
    errors: list[BaseException] = []

    def runner() -> None:
        try:
            run_live(
                config,
                no_swap_check=lambda: None,
                upstream_factory=upstream_factory,
                install_signal_handlers=False,
            )
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=runner)
    thread.start()
    deadline = time.monotonic() + 1
    while not state_path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    state = json.loads(state_path.read_text())
    certificate = work_dir / "certificate-run-1" / "certificate.pem"
    with socket.create_connection(tuple(state["relay_address"])) as raw:
        with build_test_client_context(certificate).wrap_socket(raw, server_hostname=DEVICE_HOST) as secure:
            secure.sendall(request())
            assert read_to_end(secure).endswith(body)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as dns_client:
        dns_client.settimeout(1)
        dns_client.sendto(dns_query(DEVICE_HOST), tuple(state["dns_address"]))
        answer, _address = dns_client.recvfrom(4096)
        assert answer[2:4] == b"\x81\x80"

    ntp_request = bytearray(48)
    ntp_request[0] = 0x23
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as ntp_client:
        ntp_client.settimeout(1)
        ntp_client.sendto(ntp_request, tuple(state["ntp_address"]))
        ntp_response, _address = ntp_client.recvfrom(512)
        assert len(ntp_response) == 48
        assert ntp_response[0] & 0x07 == 4
        assert ntp_response[24:32] == ntp_request[40:48]

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as dns_client:
        dns_client.settimeout(1)
        dns_client.sendto(dns_query("run-123.nonce.invalid"), tuple(state["dns_address"]))
        nxdomain, _address = dns_client.recvfrom(4096)
        assert nxdomain[2:4] == b"\x81\x83"

    thread.join(timeout=3)
    upstream_thread.join(timeout=2)
    assert errors == []
    assert not thread.is_alive()
    assert not state_path.exists()
    assert not (work_dir / "certificate-run-1").exists()
    events = event_path.read_text()
    assert '"event":"response_relayed"' in events
    assert '"event":"dns_match"' in events
    assert '"reason":"dns_match"' in events
    assert "run-123.nonce.invalid" not in events
