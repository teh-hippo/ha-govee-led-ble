from __future__ import annotations

import socket
from pathlib import Path

import pytest

from govee_relay.tls_profiles import (
    DEVICE_CIPHER,
    build_device_server_context,
    build_test_client_context,
    certificate_is_rsa,
    generate_test_certificate,
)

from .helpers import start_tls_server

HOSTNAME = "govee.ai.xaz.lol"


def test_h6199_cipher_parity(tmp_path: Path):
    files = generate_test_certificate(tmp_path / "rsa", HOSTNAME)
    server_context = build_device_server_context(files)
    client_context = build_test_client_context(files.certificate)
    negotiated: list[tuple[str, str]] = []

    def record_negotiated(secure):
        cipher = secure.cipher()
        assert cipher is not None
        negotiated.append((secure.version() or "", cipher[0]))

    address, thread = start_tls_server(
        server_context,
        record_negotiated,
    )
    with socket.create_connection(address) as raw:
        with client_context.wrap_socket(raw, server_hostname=HOSTNAME) as secure:
            assert secure.version() == "TLSv1.2"
            cipher = secure.cipher()
            assert cipher is not None
            assert cipher[0] == DEVICE_CIPHER
    thread.join(timeout=2)

    assert negotiated == [("TLSv1.2", DEVICE_CIPHER)]
    assert certificate_is_rsa(files.certificate)


def test_device_context_rejects_ecdsa_certificate(tmp_path: Path):
    files = generate_test_certificate(
        tmp_path / "ecdsa",
        HOSTNAME,
        algorithm="ecdsa",
    )
    assert not certificate_is_rsa(files.certificate)
    with pytest.raises(ValueError, match="must use RSA"):
        build_device_server_context(files)


def test_certificate_files_are_private(tmp_path: Path):
    files = generate_test_certificate(tmp_path / "permissions", HOSTNAME)
    assert files.certificate.stat().st_mode & 0o777 == 0o600
    assert files.private_key.stat().st_mode & 0o777 == 0o600
    assert files.certificate.parent.stat().st_mode & 0o777 == 0o700
