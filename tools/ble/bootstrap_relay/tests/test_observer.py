from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from govee_relay.events import EventSink
from govee_relay.observer import (
    DnsObserver,
    DnsWireError,
    EgressObservation,
    IsolationManifest,
    NtpResponder,
    build_ipv4_response,
    build_nodata_response,
    build_nxdomain_response,
    parse_dns_question_name,
)


def dns_query(name: str) -> bytes:
    labels = b"".join(bytes([len(label)]) + label.encode() for label in name.split("."))
    return b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00" + labels + b"\x00\x00\x01\x00\x01"


def test_dns_observer_extracts_name_and_returns_nxdomain():
    query = dns_query("run-123.nonce.invalid")
    assert parse_dns_question_name(query) == "run-123.nonce.invalid"
    response = build_nxdomain_response(query)
    assert response[:2] == query[:2]
    assert response[2:4] == b"\x81\x83"
    assert response[10:12] == b"\x00\x00"


def test_nxdomain_drops_edns_additional_record():
    query = dns_query("run-123.nonce.invalid")
    query = query[:10] + b"\x00\x01" + query[12:] + b"\x00\x00\x29\x10\x00\x00\x00\x00\x00\x00\x00"
    response = build_nxdomain_response(query)
    assert response[10:12] == b"\x00\x00"
    assert len(response) < len(query)


def test_ipv4_response_returns_one_a_record():
    query = dns_query("govee.ai.xaz.lol")
    response = build_ipv4_response(query, "192.0.2.10")
    assert response[:2] == query[:2]
    assert response[2:4] == b"\x81\x80"
    assert response[6:8] == b"\x00\x01"
    assert response.endswith(b"\xc0\x00\x02\x0a")


def test_known_name_aaaa_returns_nodata_not_nxdomain():
    query = dns_query("govee.ai.xaz.lol")
    aaaa_query = query[:-4] + b"\x00\x1c\x00\x01"
    response = build_ipv4_response(aaaa_query, "192.0.2.10")
    assert response == build_nodata_response(aaaa_query)
    assert response[2:4] == b"\x81\x80"
    assert response[6:8] == b"\x00\x00"


def test_dns_listener_emits_match_without_hostname(tmp_path: Path):
    events_path = tmp_path / "events.jsonl"
    with EventSink(events_path) as events:
        with DnsObserver(
            run_id="run-1",
            expected_hostname="run-123.nonce.invalid",
            events=events,
        ) as observer:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
                client.settimeout(1)
                client.sendto(dns_query("run-123.nonce.invalid"), observer.address)
                response, _address = client.recvfrom(4096)
                assert response[2:4] == b"\x81\x83"
    text = events_path.read_text()
    assert '"event":"dns_match"' in text
    assert "run-123.nonce.invalid" not in text


def test_dns_listener_answers_bootstrap_record(tmp_path: Path):
    events_path = tmp_path / "events.jsonl"
    with EventSink(events_path) as events:
        with DnsObserver(
            run_id="run-1",
            expected_hostname="",
            events=events,
            records={"govee.ai.xaz.lol": "192.0.2.10"},
        ) as observer:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
                client.settimeout(1)
                client.sendto(dns_query("govee.ai.xaz.lol"), observer.address)
                response, _address = client.recvfrom(4096)
    assert response[2:4] == b"\x81\x80"
    assert response.endswith(b"\xc0\x00\x02\x0a")
    assert events_path.read_text() == ""


def test_ntp_responder_returns_server_packet():
    request = bytearray(48)
    request[0] = 0x23
    request[2] = 6
    request[40:48] = b"12345678"
    response = NtpResponder.response(bytes(request))
    assert len(response) == 48
    assert response[0] & 0x07 == 4
    assert response[1] == 2
    assert response[24:32] == b"12345678"


def test_ntp_listener_replies():
    with NtpResponder() as responder:
        request = bytearray(48)
        request[0] = 0x23
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.settimeout(1)
            client.sendto(request, responder.address)
            response, _address = client.recvfrom(512)
    assert len(response) == 48


def test_dns_observer_rejects_compression():
    with pytest.raises(DnsWireError):
        parse_dns_question_name(b"\x00" * 12 + b"\xc0\x0c")


def test_isolation_manifest_is_unapplied_and_bounded():
    manifest = IsolationManifest()
    manifest.validate()
    rendered = json.loads(manifest.render())
    assert rendered["applied"] is False
    assert rendered["deny_other_egress"] is True
    assert rendered["denied_egress_logging"] is False
    assert rendered["ssid_characters"] == 7
    assert rendered["passphrase_characters"] == 8


def test_applied_manifest_is_rejected():
    with pytest.raises(ValueError, match="unapplied"):
        IsolationManifest(applied=True).validate()


def test_egress_observation_is_classified_without_address():
    observation = EgressObservation("unexpected-public", 8883)
    observation.validate()
    assert observation.destination_class == "unexpected-public"
    assert not hasattr(observation, "address")


def test_egress_observation_emits_safe_event(tmp_path: Path):
    path = tmp_path / "events.jsonl"
    with EventSink(path) as events:
        EgressObservation("unexpected-public", 8883).record(
            run_id="run-1",
            events=events,
        )
    text = path.read_text()
    assert '"event":"egress_denied"' in text
    assert "8883" in text


def test_egress_observation_accepts_unavailable_port():
    EgressObservation("unexpected-public", None).validate()
