#!/usr/bin/env python3
"""Decode Govee BLE command/status packets from an idevicebtlogger pcap.

Reads a libpcap file (link type 201, DLT_BLUETOOTH_HCI_H4_WITH_PHDR), walks
HCI H4 -> ACL -> L2CAP -> ATT, and prints the 20-byte Govee packets carried by
ATT writes (phone -> light) and notifications (light -> phone).

Govee packets are 20 bytes: header 0x33 (command), 0xAA (status) or 0xA3
(multi-packet fragment), with byte 19 = XOR of bytes 0..18. That signature is
used to filter Govee traffic out of the phone's other BLE activity.

Usage: uv run python tools/ble/decode_govee.py <capture.pcap> [--all]
  --all   also print packets that are not Govee (raw ATT values)
"""

import struct
import sys

ATT_CID = 0x0004
WRITE_OPCODES = {0x12: "WriteReq", 0x52: "WriteCmd", 0x1D: "Indication", 0x1B: "Notification"}


def _xor_ok(v: bytes) -> bool:
    checksum = 0
    for byte in v[:19]:
        checksum ^= byte
    return len(v) == 20 and checksum == v[19]


def _is_govee(v: bytes) -> bool:
    return len(v) == 20 and v[0] in (0x33, 0xAA, 0xA3) and _xor_ok(v)


# Observed 0xAA query/status types (phone TX = query, light RX = reply).
AA_TYPES = {
    0x01: "power",
    0x04: "groups?",
    0x05: "colormode",
    0x06: "fw-ver",
    0x07: "hw-ver",
    0x0B: "?0b",
    0x11: "?11",
    0x12: "?12",
    0x23: "segcfg",
    0x40: "count?",
    0xA3: "multi",
    0xA5: "segments",
}


def _ascii(b: bytes) -> str:
    return "".join(chr(x) for x in b if 32 <= x < 127)


def _label_aa(v: bytes, direction: str) -> str:
    t = v[1]
    name = AA_TYPES.get(t, f"type={t:#04x}")
    if direction == "TX":
        return f"query {name}"
    data = v[2:19]
    if t in (0x06, 0x07):
        return f"reply {name}={_ascii(data)!r}"
    if t == 0x01:
        return f"reply power={'on' if data[0] else 'off'}"
    if t == 0x05:
        return f"reply colormode {data[0]:#04x} {data[1]:#04x}"
    if t == 0x40:
        return f"reply count? {data[0] * 256 + data[1]}"
    if t == 0x04:
        return f"reply groups? {data[0]}"
    if t == 0xA5:
        segs = " ".join(data[1:13][i : i + 4].hex() for i in range(0, 12, 4))
        return f"reply segments group={data[0]} [{segs}]"
    return f"reply {name} {data.hex()}"


def label(v: bytes, direction: str) -> str:
    """Best-effort human label using the known Govee command map."""
    h = v[0]
    if h == 0xA3:
        return f"multi-frame idx={v[1]:#04x} {v[2:12].hex()}"
    if h == 0xAA:
        return _label_aa(v, direction)
    if h != 0x33:
        return "?"
    action = v[1]
    if direction == "RX":  # device ack/echo of a 0x33 command; payload is a status, not a set value
        names = {0x01: "power", 0x04: "brightness", 0x05: "colour", 0x09: "time/cfg", 0xA9: "calibration"}
        return f"ack {names.get(action, f'action={action:#04x}')}"
    if action == 0x01:
        return f"power {'on' if v[2] else 'off'}"
    if action == 0x04:
        return f"brightness {v[2]}%"
    if action == 0x05:
        mode = v[2]
        modes = {0x15: "static", 0x04: "scene", 0x00: "video", 0x13: "music", 0x0A: "diy"}
        detail = modes.get(mode, f"mode={mode:#04x}")
        if mode == 0x15 and v[3] == 0x01:
            return f"color rgb=({v[4]},{v[5]},{v[6]}) mask={v[12]:02x}{v[13]:02x}"
        if mode == 0x15 and v[3] == 0x02:
            return f"brightness {v[4]}% mask={v[5]:02x}{v[6]:02x}"
        return f"color/{detail} sub={v[3]:#04x} {v[3:13].hex()}"
    if action == 0x09:
        return f"time/cfg {v[2:9].hex()}"
    if action == 0xA9:
        return "dreamview/calibration"
    return f"cmd action={action:#04x} {v[2:13].hex()}"


def _iter_att(data: bytes):
    """Yield (direction, opcode, handle, value) for each ATT PDU in the pcap."""
    magic = struct.unpack("<I", data[0:4])[0]
    endian = ">" if magic == 0xD4C3B2A1 else "<"
    rec = struct.Struct(endian + "IIII")
    off = 24
    while off + 16 <= len(data):
        _, _, incl, _ = rec.unpack(data[off : off + 16])
        off += 16
        pkt = data[off : off + incl]
        off += incl
        if len(pkt) < 5:
            continue
        direction = "RX" if (struct.unpack(">I", pkt[0:4])[0] & 1) else "TX"
        if pkt[4] != 0x02:  # H4 ACL only
            continue
        acl = pkt[5:]
        if len(acl) < 8:
            continue
        l2_len, cid = struct.unpack("<HH", acl[4:8])
        if cid != ATT_CID:
            continue
        att = acl[8 : 8 + l2_len]
        if not att:
            continue
        opcode = att[0]
        if opcode not in WRITE_OPCODES or len(att) < 3:
            continue
        handle = struct.unpack("<H", att[1:3])[0]
        yield direction, opcode, handle, att[3:]


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    show_all = "--all" in sys.argv
    if not args:
        print(__doc__)
        return 2
    data = open(args[0], "rb").read()
    rows = []
    seen: set[bytes] = set()
    total = govee = 0
    for direction, opcode, handle, value in _iter_att(data):
        total += 1
        if _is_govee(value):
            govee += 1
            first = value not in seen
            seen.add(value)
            rows.append((direction, WRITE_OPCODES[opcode], handle, value, label(value, direction), first))
        elif show_all and value:
            rows.append((direction, WRITE_OPCODES[opcode], handle, value, "(non-govee)", True))

    print(f"# {args[0]}")
    print(f"# ATT writes/notifications: {total}   Govee packets: {govee}   unique Govee: {len(seen)}")
    print(f"# {'dir':<3} {'op':<12} {'hdl':<6} {'payload (hex)':<41} label")
    for direction, op, handle, value, lab, first in rows:
        mark = " " if first else "."
        print(f"{mark} {direction:<3} {op:<12} {handle:#06x} {value.hex():<41} {lab}")
    if not show_all:
        print("# ('.' = repeat of an earlier packet; pass --all to include non-Govee ATT values)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
