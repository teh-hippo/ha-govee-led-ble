#!/usr/bin/env python3
"""Extract likely Govee BLE frames from a btsnoop HCI log.

This is intended for reverse-engineering: capture a phone's btsnoop log while
changing one control in the Govee app, then diff the extracted frames.

We look for ATT writes/notifications that contain a 20-byte Govee frame:
  - byte[0] in {0x33, 0xAA, 0xA3}
  - byte[19] is XOR checksum of bytes[0..18]
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

ATT_CID = 0x0004
ATT_WRITE_REQ = 0x12
ATT_WRITE_CMD = 0x52
ATT_HANDLE_NOTIFY = 0x1B

GOVEE_HEADERS = {0x33, 0xAA, 0xA3}
H4_TYPES = {0x01, 0x02, 0x03, 0x04, 0x05}


def _xor_checksum(data: bytes) -> int:
    checksum = 0
    for b in data:
        checksum ^= b
    return checksum


def _h4_view(data: bytes) -> bytes | None:
    """Return H:4 packet view, skipping the optional 4-byte PHDR if present."""
    if not data:
        return None
    if data[0] in H4_TYPES:
        return data
    if len(data) >= 5 and data[4] in H4_TYPES:
        return data[4:]
    return None


def _iter_btsnoop_records(blob: bytes) -> tuple[int, int, int, bytes]:
    if len(blob) < 16 or blob[:8] != b"btsnoop\0":
        raise ValueError("Not a btsnoop file")
    pos = 16
    while pos + 24 <= len(blob):
        orig_len, incl_len, flags, _drops, ts = struct.unpack_from(">IIIIQ", blob, pos)
        pos += 24
        if incl_len > orig_len or pos + incl_len > len(blob):
            break
        yield flags, ts, incl_len, blob[pos : pos + incl_len]
        pos += incl_len


def _extract_att_frames(data: bytes) -> tuple[int, int, int, bytes] | None:
    """Return (att_opcode, att_handle, att_cid, value) if this is an ATT PDU."""
    h4 = _h4_view(data)
    if not h4 or h4[0] != 0x02:  # ACL data
        return None
    if len(h4) < 1 + 4:
        return None
    _handle_pb_bc, dlen = struct.unpack_from("<HH", h4, 1)
    acl = h4[1 + 4 : 1 + 4 + dlen]
    if len(acl) < 4:
        return None
    l2cap_len, cid = struct.unpack_from("<HH", acl, 0)
    if cid != ATT_CID:
        return None
    att = acl[4 : 4 + l2cap_len]
    if len(att) < 3:
        return None
    opcode = att[0]
    if opcode not in {ATT_WRITE_REQ, ATT_WRITE_CMD, ATT_HANDLE_NOTIFY}:
        return None
    handle = struct.unpack_from("<H", att, 1)[0]
    value = att[3:]
    return opcode, handle, cid, value


def _is_govee_frame(value: bytes) -> bool:
    return len(value) == 20 and value[0] in GOVEE_HEADERS and value[19] == _xor_checksum(value[:19])


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("btsnoop", type=Path, help="Path to btsnoop_hci.log")
    p.add_argument("--handle", type=lambda s: int(s, 0), help="Filter by ATT handle (e.g. 0x0025)")
    args = p.parse_args(argv)

    blob = args.btsnoop.read_bytes()
    t0: int | None = None

    for flags, ts, _incl_len, record in _iter_btsnoop_records(blob):
        if t0 is None:
            t0 = ts
        att = _extract_att_frames(record)
        if att is None:
            continue
        opcode, handle, _cid, value = att
        if args.handle is not None and handle != args.handle:
            continue
        if not _is_govee_frame(value):
            continue
        dt = 0.0 if t0 is None else (ts - t0) / 1_000_000.0
        direction = "rx" if (flags & 0x01) else "tx"
        print(
            f"{dt:9.3f}s {direction} att=0x{opcode:02x} handle=0x{handle:04x} "
            f"govee=0x{value[0]:02x}/0x{value[1]:02x} raw={value.hex()}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
