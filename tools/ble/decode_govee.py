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
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

ATT_CID = 0x0004
WRITE_OPCODES = {0x12: "WriteReq", 0x52: "WriteCmd", 0x1D: "Indication", 0x1B: "Notification"}


@dataclass(frozen=True)
class ConnectionEvent:
    timestamp: datetime
    connection_handle: int
    address: str | None
    connected: bool


@dataclass(frozen=True)
class AttRecord:
    timestamp: datetime
    direction: str
    connection_handle: int
    address: str | None
    opcode: int
    attribute_handle: int
    value: bytes


@dataclass(frozen=True)
class CaptureTrace:
    connections: tuple[ConnectionEvent, ...]
    att: tuple[AttRecord, ...]


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
    0x23: "timer",
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


def _pcap_layout(data: bytes) -> tuple[str, int]:
    if len(data) < 24:
        raise ValueError("pcap header is truncated")
    layouts = {
        b"\xd4\xc3\xb2\xa1": ("<", 1_000_000),
        b"\xa1\xb2\xc3\xd4": (">", 1_000_000),
        b"\x4d\x3c\xb2\xa1": ("<", 1_000_000_000),
        b"\xa1\xb2\x3c\x4d": (">", 1_000_000_000),
    }
    try:
        endian, timestamp_scale = layouts[data[:4]]
    except KeyError as exc:
        raise ValueError("unsupported pcap byte order or timestamp format") from exc
    if struct.unpack(f"{endian}I", data[20:24])[0] != 201:
        raise ValueError("pcap is not DLT_BLUETOOTH_HCI_H4_WITH_PHDR")
    return endian, timestamp_scale


def _format_address(raw: bytes) -> str:
    return ":".join(f"{part:02X}" for part in reversed(raw))


def _connection_event(timestamp: datetime, h4: bytes) -> ConnectionEvent | None:
    if len(h4) < 3 or h4[0] != 0x04:
        return None
    event_code = h4[1]
    params = h4[3 : 3 + h4[2]]
    if event_code == 0x3E and len(params) >= 12 and params[0] in (0x01, 0x0A, 0x29):
        if params[1] != 0:
            return None
        return ConnectionEvent(
            timestamp=timestamp,
            connection_handle=struct.unpack("<H", params[2:4])[0] & 0x0FFF,
            address=_format_address(params[6:12]),
            connected=True,
        )
    if event_code == 0x05 and len(params) >= 4 and params[0] == 0:
        return ConnectionEvent(
            timestamp=timestamp,
            connection_handle=struct.unpack("<H", params[1:3])[0] & 0x0FFF,
            address=None,
            connected=False,
        )
    return None


def parse_capture(data: bytes, *, allow_truncated: bool = False) -> CaptureTrace:
    """Parse connection lifecycle and attributed ATT records from an iPhone HCI pcap."""
    endian, timestamp_scale = _pcap_layout(data)
    rec = struct.Struct(f"{endian}IIII")
    off = 24
    active_connections: dict[int, str] = {}
    connection_events: list[ConnectionEvent] = []
    att_records: list[AttRecord] = []
    while off < len(data):
        if off + 16 > len(data):
            if allow_truncated:
                break
            raise ValueError("pcap record header is truncated")
        seconds, fraction, incl, _ = rec.unpack(data[off : off + 16])
        off += 16
        if off + incl > len(data):
            if allow_truncated:
                break
            raise ValueError("pcap record payload is truncated")
        pkt = data[off : off + incl]
        off += incl
        if len(pkt) < 5:
            continue
        timestamp = datetime.fromtimestamp(seconds + fraction / timestamp_scale, UTC)
        direction = "RX" if (struct.unpack(">I", pkt[0:4])[0] & 1) else "TX"
        h4 = pkt[4:]
        if event := _connection_event(timestamp, h4):
            if event.connected and event.address is not None:
                active_connections[event.connection_handle] = event.address
            else:
                active_connections.pop(event.connection_handle, None)
            connection_events.append(event)
            continue
        if h4[0] != 0x02:  # H4 ACL only
            continue
        acl = h4[1:]
        if len(acl) < 8:
            continue
        connection_handle = struct.unpack("<H", acl[0:2])[0] & 0x0FFF
        l2_len, cid = struct.unpack("<HH", acl[4:8])
        if cid != ATT_CID:
            continue
        att = acl[8 : 8 + l2_len]
        if not att:
            continue
        opcode = att[0]
        if opcode not in WRITE_OPCODES or len(att) < 3:
            continue
        att_records.append(
            AttRecord(
                timestamp=timestamp,
                direction=direction,
                connection_handle=connection_handle,
                address=active_connections.get(connection_handle),
                opcode=opcode,
                attribute_handle=struct.unpack("<H", att[1:3])[0],
                value=att[3:],
            )
        )
    return CaptureTrace(tuple(connection_events), tuple(att_records))


def active_connections_at(trace: CaptureTrace, timestamp: datetime) -> dict[int, str]:
    active: dict[int, str] = {}
    for event in trace.connections:
        if event.timestamp > timestamp:
            break
        if event.connected and event.address is not None:
            active[event.connection_handle] = event.address
        else:
            active.pop(event.connection_handle, None)
    return active


def _iter_att(data: bytes) -> Iterator[tuple[str, int, int, bytes]]:
    """Yield the legacy (direction, opcode, attribute handle, value) ATT tuples."""
    for record in parse_capture(data).att:
        yield record.direction, record.opcode, record.attribute_handle, record.value


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
    for record in parse_capture(data).att:
        direction = record.direction
        opcode = record.opcode
        handle = record.attribute_handle
        value = record.value
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
