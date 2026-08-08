from __future__ import annotations

import os
import sys
from collections.abc import Iterable
from pathlib import Path


class SecretScanError(RuntimeError):
    """A fabricated secret reached an output channel."""


def scan_text(channel: str, text: str, secrets: Iterable[str]) -> None:
    for secret in secrets:
        if secret and secret in text:
            raise SecretScanError(f"fabricated secret found in {channel}")


def scan_paths(paths: Iterable[Path], secrets: Iterable[str]) -> None:
    secret_list = tuple(secrets)
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        scan_text(
            str(path),
            path.read_text(encoding="utf-8", errors="replace"),
            secret_list,
        )


def scan_process_channels(
    *,
    secrets: Iterable[str],
    traceback_text: str = "",
) -> None:
    secret_list = tuple(secrets)
    scan_text("argv", "\0".join(sys.argv), secret_list)
    scan_text(
        "environment",
        "\0".join(f"{key}={value}" for key, value in os.environ.items()),
        secret_list,
    )
    scan_text("traceback", traceback_text, secret_list)
