from __future__ import annotations

import os
import sys
from importlib import import_module
from importlib.abc import MetaPathFinder
from pathlib import Path
from typing import Any

_LOCAL_MIRROR_PREFIX = "custom_components.ha_govee_led_ble.generated_protocol"
_CASES = (
    ("h6139_wire_write", "H6139WireWrite", "330502ffffff01ffae547f"),
    ("h6139_status_reply", "H6139StatusReply", "aa050e30327f"),
    ("h6181_command_ack", "H6181CommandAck", "a102007f"),
    ("h60b0_status_query", "H60b0StatusQuery", "aa42000000000000000000000000000000000000"),
)

_GENERATED_DIR = os.environ.get("KAITAI_GENERATED_DIR")
if not _GENERATED_DIR:
    raise RuntimeError("KAITAI_GENERATED_DIR is required")

_GENERATED_PATH = Path(_GENERATED_DIR).resolve()
if not _GENERATED_PATH.is_dir():
    raise RuntimeError(f"KAITAI_GENERATED_DIR is not a directory: {_GENERATED_PATH}")


class _LocalMirrorBlocker(MetaPathFinder):
    def find_spec(
        self,
        fullname: str,
        path: Any = None,
        target: Any = None,
    ) -> None:
        if fullname == _LOCAL_MIRROR_PREFIX or fullname.startswith(f"{_LOCAL_MIRROR_PREFIX}."):
            raise ImportError(f"independently generated parser attempted to import local mirror: {fullname}")
        return None


def _xor_checksum(data: bytes) -> int:
    checksum = 0
    for value in data:
        checksum ^= value
    return checksum


def _check_all_generated_parsers_import_without_the_local_mirror() -> None:
    modules = sorted(path.stem for path in _GENERATED_PATH.glob("*.py") if path.name != "__init__.py")
    assert modules
    for module in modules:
        import_module(module)


def _check_independently_generated_parser_consumes_representative_frame(
    module: str,
    class_name: str,
    payload: str,
) -> None:
    content = bytes.fromhex(payload)
    if len(content) < 20:
        content += bytes(19 - len(content))
        content += bytes((_xor_checksum(content),))

    parsed = getattr(import_module(module), class_name).from_bytes(content)
    parsed._read()
    assert parsed._io.is_eof()


def main() -> None:
    sys.path.insert(0, str(_GENERATED_PATH))
    sys.meta_path.insert(0, _LocalMirrorBlocker())
    _check_all_generated_parsers_import_without_the_local_mirror()
    for case in _CASES:
        _check_independently_generated_parser_consumes_representative_frame(*case)


if __name__ == "__main__":
    main()
