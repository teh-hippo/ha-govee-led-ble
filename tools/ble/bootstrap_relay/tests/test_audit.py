from __future__ import annotations

from pathlib import Path

import pytest

from govee_relay.audit import (
    SecretScanError,
    scan_paths,
    scan_process_channels,
    scan_text,
)

SECRET = "fabricated-secret-for-audit"  # noqa: S105 - deliberate fake leak detector


def test_secret_scanner_accepts_clean_channels(tmp_path: Path):
    clean = tmp_path / "clean.txt"
    clean.write_text("only redacted facts")
    scan_text("log", "redacted", [SECRET])
    scan_paths([clean], [SECRET])
    scan_process_channels(secrets=[SECRET], traceback_text="safe traceback")


def test_secret_scanner_rejects_file_and_traceback(tmp_path: Path):
    leaked = tmp_path / "leaked.txt"
    leaked.write_text(SECRET)
    with pytest.raises(SecretScanError, match="leaked.txt"):
        scan_paths([leaked], [SECRET])
    with pytest.raises(SecretScanError, match="traceback"):
        scan_process_channels(secrets=[SECRET], traceback_text=SECRET)
