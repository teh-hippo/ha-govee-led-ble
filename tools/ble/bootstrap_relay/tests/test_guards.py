from __future__ import annotations

import os
import resource
import socket
import ssl
from pathlib import Path

import pytest

from govee_relay.guards import (
    assert_context_has_no_keylog,
    assert_secrets_absent_from_environment,
    core_dumps_disabled,
    harden_process,
)

from .conftest import OfflineEgressError


def test_process_hardening_removes_keylog_and_core_dumps(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setenv("SSLKEYLOGFILE", str(tmp_path / "forbidden-keylog"))
    harden_process()

    assert "SSLKEYLOGFILE" not in os.environ
    assert core_dumps_disabled()
    assert resource.getrlimit(resource.RLIMIT_CORE) == (0, 0)


def test_context_keylog_is_rejected(tmp_path: Path):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.keylog_filename = str(tmp_path / "forbidden-keylog")

    with pytest.raises(RuntimeError, match="key logging"):
        assert_context_has_no_keylog(context)


def test_secret_environment_scan(monkeypatch):
    monkeypatch.setenv("SYNTHETIC_SECRET", "fabricated-private-key-value")
    with pytest.raises(RuntimeError, match="fabricated secret"):
        assert_secrets_absent_from_environment(["fabricated-private-key-value"])


def test_offline_egress_guard_is_active():
    with pytest.raises(OfflineEgressError):
        socket.create_connection(("192.0.2.1", 443), timeout=0.1)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        with pytest.raises(OfflineEgressError):
            client.sendto(b"probe", ("192.0.2.1", 53))
