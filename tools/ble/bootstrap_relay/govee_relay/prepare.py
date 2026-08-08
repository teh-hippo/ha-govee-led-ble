from __future__ import annotations

import argparse
import json
import platform
import socket
import ssl
import threading
from pathlib import Path
from tempfile import TemporaryDirectory

from .http_wire import build_upstream_request, parse_device_request
from .observer import IsolationManifest
from .tls_profiles import (
    build_device_server_context,
    build_test_client_context,
    generate_test_certificate,
)

FABRICATED_QUERY = b"device=00%3A11%3A22%3A33%3A44%3A55&sku=H6199&wifiHardVersion=0.0.0&wifiSoftVersion=0.0.0"
FABRICATED_REQUEST = (
    b"POST /device/v1/base/config?" + FABRICATED_QUERY + b" HTTP/1.1\r\n"
    b"Accept: */*\r\n"
    b"Host: govee.ai.xaz.lol\r\n"
    b"envId: 0\r\n"
    b"iotVersion: 0\r\n\r\n"
)


def measure_device_tls() -> dict[str, str]:
    hostname = "govee.ai.xaz.lol"
    with TemporaryDirectory() as temporary:
        files = generate_test_certificate(Path(temporary), hostname)
        server_context = build_device_server_context(files)
        client_context = build_test_client_context(files.certificate)
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        measured: dict[str, str] = {}

        def serve() -> None:
            try:
                raw, _address = listener.accept()
                with server_context.wrap_socket(raw, server_side=True) as secure:
                    measured["tls_version"] = secure.version() or ""
                    cipher = secure.cipher()
                    measured["cipher"] = "" if cipher is None else cipher[0]
            finally:
                listener.close()

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        with socket.create_connection(listener.getsockname()) as raw:
            with client_context.wrap_socket(raw, server_hostname=hostname):
                pass
        thread.join(timeout=2)
        if thread.is_alive():
            raise RuntimeError("TLS parity measurement did not complete")
        measured["certificate"] = "RSA-2048"
        return measured


def evidence() -> dict[str, object]:
    parsed = parse_device_request(
        FABRICATED_REQUEST,
        expected_host="govee.ai.xaz.lol",
    )
    upstream = build_upstream_request(parsed, upstream_host="device.govee.com")
    return {
        "runtime": {
            "kind": "measured",
            "value": {
                "python": platform.python_version(),
                "openssl": ssl.OPENSSL_VERSION,
            },
        },
        "device_tls_policy": {
            "kind": "measured",
            "value": measure_device_tls(),
        },
        "fabricated_upstream_request_hex": upstream.hex(),
        "fabricated_upstream_request_ascii": upstream.decode("ascii"),
        "isolation_manifest": json.loads(IsolationManifest().render()),
        "control_fingerprint": {
            "kind": "observed",
            "source": "files/h6199-research/endpoint-events-sanitized.txt",
            "value": {
                "status": 503,
                "attempts": 6,
                "approximate_interval_seconds": 2.1,
                "approximate_total_seconds": 11.6,
            },
        },
        "device_provisioning_or_power_cycle_performed": {
            "kind": "asserted",
            "value": False,
        },
        "production_http_requests_performed": {
            "kind": "asserted",
            "value": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence(), indent=2) + "\n")
    args.output.chmod(0o600)


if __name__ == "__main__":
    main()
