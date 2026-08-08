from __future__ import annotations

import json
import socket
import ssl
import time
from pathlib import Path

from govee_relay.events import EventSink
from govee_relay.mqtt_probe import (
    MqttClientHelloProbe,
    MqttTlsConnectProbe,
    parse_client_hello,
    parse_mqtt_connect,
)
from govee_relay.tls_profiles import (
    build_device_server_context,
    build_test_client_context,
    generate_test_certificate,
)

HOSTNAME = "run-c.nonce.govee.ai.xaz.lol"


def client_hello(hostname: str = HOSTNAME) -> bytes:
    encoded = hostname.encode()
    server_name = b"\x00" + len(encoded).to_bytes(2, "big") + encoded
    sni_value = len(server_name).to_bytes(2, "big") + server_name
    extensions = b"\x00\x00" + len(sni_value).to_bytes(2, "big") + sni_value
    body = (
        b"\x03\x03"
        + bytes(32)
        + b"\x00"
        + b"\x00\x02\x00\x2f"
        + b"\x01\x00"
        + len(extensions).to_bytes(2, "big")
        + extensions
    )
    handshake = b"\x01" + len(body).to_bytes(3, "big") + body
    return b"\x16\x03\x01" + len(handshake).to_bytes(2, "big") + handshake


def test_parse_client_hello_records_only_safe_metadata():
    metadata = parse_client_hello(client_hello(), expected_sni=HOSTNAME)
    assert metadata == {
        "record_version": "3.1",
        "client_version": "3.3",
        "cipher_count": 1,
        "extension_types": [0],
        "sni_present": True,
        "sni_matched": True,
    }


def test_client_hello_probe_emits_no_hostname(tmp_path: Path):
    event_path = tmp_path / "events.jsonl"
    with EventSink(event_path) as events:
        probe = MqttClientHelloProbe(
            run_id="run-c",
            expected_sni=HOSTNAME,
            events=events,
            host="127.0.0.1",
            port=0,
        )
        probe.start()
        with socket.create_connection(probe.address) as connection:
            connection.sendall(client_hello())
        deadline = time.monotonic() + 1
        while not probe.client_hello_seen.is_set() and time.monotonic() < deadline:
            time.sleep(0.01)
        probe.close()

    row = json.loads(event_path.read_text())
    assert row["event"] == "mqtt_client_hello"
    assert row["sni_matched"] is True
    assert HOSTNAME not in event_path.read_text()


def mqtt_connect(client_id: bytes = b"sensitive-client") -> bytes:
    variable = b"\x00\x04MQTT\x04\x02\x00\x3c" + len(client_id).to_bytes(2, "big") + client_id
    return b"\x10" + bytes([len(variable)]) + variable


def test_parse_mqtt_connect_retains_only_shape():
    assert parse_mqtt_connect(mqtt_connect()) == {
        "protocol_level": 4,
        "remaining_length": 28,
        "clean_session": True,
        "keepalive": 60,
        "client_id_length": 16,
        "username_present": False,
        "password_present": False,
        "will_present": False,
        "will_qos": 0,
        "will_retain": False,
    }


def test_mqtt_tls_probe_records_connect_shape_without_values(tmp_path: Path):
    files = generate_test_certificate(tmp_path / "mqtt-cert", HOSTNAME)
    event_path = tmp_path / "events.jsonl"
    with EventSink(event_path) as events:
        probe = MqttTlsConnectProbe(
            run_id="run-d",
            context=build_device_server_context(files),
            events=events,
            host="127.0.0.1",
            port=0,
        )
        probe.start()
        client_context = build_test_client_context(files.certificate)
        with socket.create_connection(probe.address) as raw:
            with client_context.wrap_socket(raw, server_hostname=HOSTNAME) as secure:
                secure.sendall(mqtt_connect())
                try:
                    secure.recv(1)
                except ssl.SSLError:
                    pass
        deadline = time.monotonic() + 1
        while not probe.completed.is_set() and time.monotonic() < deadline:
            time.sleep(0.01)
        probe.close()

    text = event_path.read_text()
    rows = [json.loads(line) for line in text.splitlines()]
    assert [row["event"] for row in rows] == ["mqtt_tls_accepted", "mqtt_connect_shape"]
    assert rows[1]["client_id_length"] == 16
    assert "sensitive-client" not in text


def test_mqtt_tls_probe_records_safe_certificate_rejection(tmp_path: Path):
    files = generate_test_certificate(tmp_path / "mqtt-cert", HOSTNAME)
    event_path = tmp_path / "events.jsonl"
    with EventSink(event_path) as events:
        probe = MqttTlsConnectProbe(
            run_id="run-d-failure",
            context=build_device_server_context(files),
            events=events,
            host="127.0.0.1",
            port=0,
        )
        probe.start()
        rejecting_context = ssl.create_default_context()
        rejecting_context.minimum_version = ssl.TLSVersion.TLSv1_2
        rejecting_context.maximum_version = ssl.TLSVersion.TLSv1_2
        rejecting_context.set_ciphers("AES256-SHA256:@SECLEVEL=1")
        try:
            with socket.create_connection(probe.address) as raw:
                with rejecting_context.wrap_socket(raw, server_hostname=HOSTNAME):
                    pass
        except ssl.SSLError:
            pass
        deadline = time.monotonic() + 1
        while not probe.completed.is_set() and time.monotonic() < deadline:
            time.sleep(0.01)
        probe.close()

    row = json.loads(event_path.read_text())
    assert row["event"] == "mqtt_tls_failed"
    assert row["reason"] in {"TLSV1_ALERT_UNKNOWN_CA", "ssl_error"}
