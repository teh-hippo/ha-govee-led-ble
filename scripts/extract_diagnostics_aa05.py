#!/usr/bin/env python3
"""Extract the most recent rx AA05 payload from HA diagnostics.

This is a small helper for reverse-engineering: download HA diagnostics for a
device (Settings -> Devices & Services -> ... -> Download diagnostics), then run
this script to print the latest `rx aa05...` frame captured in
`coordinator.packet_log`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load_packet_log(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    packet_log = data.get("coordinator", {}).get("packet_log")
    if not isinstance(packet_log, list):
        return []
    return [e for e in packet_log if isinstance(e, dict)]


def _decode_aa05(raw_hex: str) -> str:
    try:
        raw = bytes.fromhex(raw_hex)
    except ValueError:
        return "invalid-hex"
    if len(raw) < 3 or raw[0] != 0xAA or raw[1] != 0x05:
        return "not-aa05"
    payload = raw[2:]
    mode = payload[0] if payload else None
    if mode == 0x00 and len(payload) >= 4:
        extra = payload[4:].hex()
        return f"video full={payload[1]} game={payload[2]} sat={payload[3]} extra={extra}"
    return f"mode=0x{mode:02x} payload={payload.hex()}" if mode is not None else "empty-payload"


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("diagnostics", type=Path, nargs="+", help="HA diagnostics JSON file(s)")
    p.add_argument("--all", action="store_true", help="Print all rx AA05 entries (not just latest)")
    args = p.parse_args(argv)

    for diag_path in args.diagnostics:
        packet_log = _load_packet_log(diag_path)
        aa05 = [
            e
            for e in packet_log
            if e.get("dir") == "rx" and isinstance(raw := e.get("raw"), str) and raw.startswith("aa05")
        ]

        print(diag_path)
        print(f"  rx_aa05_entries={len(aa05)}")
        if not aa05:
            continue

        entries = aa05 if args.all else [aa05[-1]]
        for e in entries:
            raw = str(e.get("raw"))
            ts = e.get("ts")
            print(f"  ts={ts} raw={raw}")
            print(f"  decoded={_decode_aa05(raw)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
