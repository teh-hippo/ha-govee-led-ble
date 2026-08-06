#!/usr/bin/env python3
"""Decode Govee BLE command/status packets from an iPhone HCI capture.

Reads either container an iPhone HCI capture arrives in, walks
HCI H4 -> ACL -> L2CAP -> ATT, and prints the 20-byte Govee packets carried by
ATT writes (phone -> light) and notifications (light -> phone).

Both containers carry link type 201, DLT_BLUETOOTH_HCI_H4_WITH_PHDR, and the framing
inside is byte-identical: a 4-byte big-endian direction pseudo-header, the HCI H4 type
byte, then the HCI payload. Only the container and the timestamp basis differ, so
everything below `iter_frames` is shared.

Govee packets are 20 bytes: header 0x33 (command), 0xAA (status) or 0xA3
(multi-packet fragment), with byte 19 = XOR of bytes 0..18. That signature is
used to filter Govee traffic out of the phone's other BLE activity.

Usage: uv run python tools/ble/decode_govee.py <capture.pcapng|capture.pcap> [options]
  --all                   also print packets that are not Govee (raw ATT values)
  --source SEL            keep one source; an address, an address tail, or ?conn-0xNN
  --allow-unattributed    proceed past frames whose connection predates the capture
  --all-peers             dump a multi-source capture mixed, on purpose

A phone talks to every light it is paired with, so one capture can hold more than one
model. Reading a second model's frames as this one's is not a rendering mistake, it is a
false protocol finding, so a capture holding more than one Govee source is REFUSED until
it is narrowed with --source. The source summary is printed either way.

A SOURCE IS A CONNECTION, NOT AN ADDRESS. Counting sources by peer address made the guard
fire only on the captures that did not need it. Every frame on a connection the capture
never saw open has no address, so on 2026-08-05 a session holding two ATT connections,
2189 Govee-shaped frames on 0x4e and 2 on 0x56, collapsed into the single bucket "?=2191"
and printed clean. The second connection was a heart-rate wearable whose own framing
happens to pass the 20-byte XOR test, so the frames were not even Govee, and nothing in
the output said so. The ATT connection handle is present on every frame whether or not an
address ever was, so it is what the count keys on now.
"""

import argparse
import struct
import sys
from collections.abc import Iterable, Iterator
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
    connection_epoch: int
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


def _sum8_ok(v: bytes) -> bool:
    return len(v) == 7 and (sum(v[:6]) & 0xFF) == v[6]


def _is_music_stream(v: bytes) -> bool:
    # The phone-microphone music path (music_stream.ksy). A 7-byte a5 02 83 <rgb> frame
    # on the same write handle, checksummed by SUM rather than XOR, which is exactly why
    # it slipped past _is_govee for a whole session and showed up as "(non-govee)".
    return len(v) == 7 and v[:3] == b"\xa5\x02\x83" and _sum8_ok(v)


def _is_govee(v: bytes) -> bool:
    # 0x33 write / 0xAA read / 0xA3 multi-part write are the H617A opcode set. 0xA1 is a
    # second multi-part upload header; on the H6199 it carries Wi-Fi provisioning (a1 11).
    #
    # It was described here as the opcode that family uses "in place of 0xA3" for DIY
    # uploads. That was wrong for the H6199 and is corrected rather than deleted, because the
    # belief is the kind that regrows: captures on 2026-08-04 of the DIY editor and of
    # applying a saved DIY put 27 0xA3 frames on the wire and not one 0xA1. Both headers are
    # live on this model, for different jobs, so neither replaces the other.
    #
    # 0xEE is DEVICE-INITIATED and was missing here, which cost more than it looks. The
    # H6199 reports the outcome of a Wi-Fi association on ee 11, about eleven seconds after
    # the credentials are written, and this allowlist dropped it. A provisioning capture
    # therefore decoded as a write that was acknowledged and never answered, which read as
    # the device ignoring the request when it had in fact replied and said it failed. The
    # frame was in the capture the whole time and only --all would show it.
    #
    # The lesson generalises past this one header: a filter keyed on what we already know
    # about hides exactly the traffic that would teach us something new, so anything
    # 20 bytes long with a valid XOR is now let through on these headers rather than being
    # judged on whether we recognise it.
    #
    # SHAPE IS NOT IDENTITY, and it never was. Twenty bytes with a valid XOR is a 1-in-256
    # accident for any frame whose first byte lands in this set, so a busy connection to
    # something else entirely will contribute a few frames here. Two did, in a capture on
    # 2026-08-05: 76 frames of a length-prefixed transport (magic aa 01, u16le length, u16le
    # flags, CRC-16/MODBUS over that 6-byte header, then length bytes of payload) shared a
    # capture with the light, on an accessory whose other characteristic was a standard
    # Heart Rate Measurement. Two of the 76 XOR'd out and were labelled "reply power=on".
    # Nothing here can fix that, because the collision is genuine. The connection they
    # arrived on is what tells them apart, which is why govee_sources counts connections.
    if _is_music_stream(v):
        return True
    return len(v) == 20 and v[0] in (0x33, 0xAA, 0xA3, 0xA1, 0xEE) and _xor_ok(v)


# Observed 0xAA query/status types (phone TX = query, light RX = reply).
AA_TYPES = {
    0x01: "power",
    0x04: "brightness",
    0x05: "colormode",
    0x06: "fw-ver",
    0x07: "hw-ver",
    0x0B: "?0b",
    0x11: "sleep-timer",
    0x12: "wake-timer",
    0x23: "timer",
    0x40: "count-40",
    0xA3: "multi",
    0xA5: "segments",
}


def _ascii(b: bytes) -> str:
    return "".join(chr(x) for x in b if 32 <= x < 127)


def reassemble_a3(frames: Iterable[bytes]) -> bytes:
    """Reassemble ONE 0xA3 transaction, per govee_common::a3_header.

    Concatenate ``bytes[2:19]`` of every frame in arrival order, INCLUDING the 0xff-indexed
    one. The 0xff index does not mean "terminator": in the plain form the last DATA chunk
    carries it, so discarding that frame truncates the body. That is the common case, not an
    edge case: 40 of the 46 A3 transactions in the capture corpus are the plain form.

    Caller must pass exactly one transaction. Segment on index 0x00..0xff first; handing this
    a whole capture window concatenates unrelated bodies.

    Deliberately does NOT cut to ``linecount * 17``. That cut was tried on 2026-07-26 and
    removed: for one complete transaction it is provably a no-op (linecount * 17 equals the
    concatenated length in all 46 corpus transactions), and for anything else it is destructive,
    silently dropping every transaction after the first and mangling duplicates. Use linecount
    as a CHECK on the result, never as a slice.
    """
    return b"".join(frame[2:19] for frame in frames)


def segment_a3(frames: Iterable[bytes]) -> list[list[bytes]]:
    """Split a stream of 0xA3 frames into individual transactions.

    Both framing forms described in govee_common::a3_header end on the frame whose index byte
    is 0xFF, in the terminator form as an appended all-zero frame and in the plain form as the
    last data chunk, so that byte closes a transaction under either. A restart to index 0x00
    also closes one, so a capture that lost the tail of an upload yields two transactions
    rather than one fused body.
    """
    transactions: list[list[bytes]] = []
    current: list[bytes] = []
    for frame in frames:
        if current and frame[1] == 0x00:
            transactions.append(current)
            current = []
        current.append(frame)
        if frame[1] == 0xFF:
            transactions.append(current)
            current = []
    if current:
        transactions.append(current)
    return transactions


def a3_body_is_complete(body: bytes) -> bool:
    """Check a reassembled body against its own linecount, per govee_common::a3_header.

    linecount is a CHECK, never a slice. A body that fails this is truncated or fused, and the
    length disagreement it causes downstream invites the wrong conclusion that the grammar is
    broken.
    """
    return len(body) >= 2 and body[0] == 0x01 and len(body) == body[1] * 17


DIRECTIONS = ("TX", "RX")


def _require_direction(direction: str) -> None:
    """Refuse to label a frame without knowing who sent it.

    Two families of Govee frame are byte-identical between the two directions, so a labeller
    that guesses reports state the device never sent. The aa 05 query body is identical to a
    mode 0x00 video reply (see h6199_status_reply::video_state), and an aa reply with an
    all-zero body is identical to its own query frame, which has now bitten on 0xa3 and
    again on 0x01. The old code treated any unrecognised direction as a REPLY, so a typo
    produced phantom state silently rather than failing.
    """
    if direction not in DIRECTIONS:
        raise ValueError(f"direction must be one of {DIRECTIONS}, got {direction!r}")


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
        # status_reply::unit_count_body: the value 15 is corroborated, but neither the
        # u1/u2be split nor what it counts is. Do not print it as a segment count.
        return f"reply count={data[1]}" + (f" reserved={data[0]:#04x}" if data[0] else "")
    if t == 0x04:
        return f"reply brightness={data[0]}%"
    if t == 0xA5:
        segs = " ".join(data[1:13][i : i + 4].hex() for i in range(0, 12, 4))
        return f"reply segments group={data[0]} [{segs}]"
    return f"reply {name} {data.hex()}"


def _segment_mask(pair: bytes) -> str:
    """Render a command_write::segment_mask, which is u2le, NOT the raw byte order.

    Printing the two bytes in wire order reads like a big-endian value and silently
    transposes the bitmap: an all-segments 0x7fff shows up as 0xff7f, which looks like
    a 15-bit map that skips bit 7 and uses bit 15. That misreading was made and caught
    on 2026-07-27; render the value the spec defines and list the segments outright so
    it cannot happen from decoder output again.
    """
    bits = int.from_bytes(pair, "little")
    if bits == 0x7FFF:
        return "0x7fff(all)"
    segments = [str(i + 1) for i in range(15) if bits & (1 << i)]
    return f"0x{bits:04x}(seg {','.join(segments) if segments else '-'})"


def _label_display_setting(v: bytes) -> str:
    """Render a 33 a9 write on its selector (h6199_command_write::display_setting_body).

    The register is a selector, a payload length and a payload, not a flat body, and two
    unrelated settings ride it. One label for the whole register printed a blank-screen toggle
    as if it were white balance, which is the same misreading the simulator made and which reads
    as a setting nobody touched rather than as an unknown frame.
    """
    setting, length = v[2], v[3]
    payload = v[4 : 4 + length]
    if setting == 0x00 and length >= 3:
        # The two gains, not a position: the app's strip picks a table index and writes the pair
        # it names, so the quantity the user set is not in the frame.
        return f"white balance manual={payload[0]} gains=({payload[1]},{payload[2]})"
    if setting == 0x0A and length >= 1:
        return f"blank screen {'on' if payload[0] else 'off'} tail={payload[1:].hex()}"
    return f"display setting={setting:#04x} {payload.hex()}"


def _is_wifi_credential_frame(v: bytes) -> bool:
    """An 0xA1 multi-part upload carrying sub-opcode 0x11, the Wi-Fi credential push.

    CONFIRMED ON WIRE 2026-08-04 against a fabricated network: the reassembled body is
    [ssid_len][ssid][pw_len][password][runMode][tzHours][iotVersion][tzMinutes] followed by
    a two-byte big-endian length and the cloud endpoint. The SSID and passphrase are plain
    UTF-8, so these frames are a network password in clear.
    """
    return len(v) >= 2 and v[0] == 0xA1 and v[1] == 0x11


def _is_device_mac_frame(v: bytes) -> bool:
    """An 0xAA reply on domain 0x14, which answers with the device's Wi-Fi MAC.

    CONFIRMED ON WIRE 2026-08-04: opening the app's Wi-Fi settings queries aa 14 and the
    device answers with six bytes of MAC. That is hardware identity for a specific unit, of
    the same kind as the phone UDID the identity guard exists for, and it is why the private
    issue tracking this work omits domain 0x14 from the corpus.

    Redacted for the same reason as the credential frames rather than a different one: a
    routine decode should not be able to put a permanent hardware identifier into a
    terminal, a transcript, or a pasted excerpt.
    """
    return len(v) >= 2 and v[0] == 0xAA and v[1] == 0x14


def secret_reason(v: bytes) -> str | None:
    """Why this frame's payload is withheld, or None when it is safe to print.

    ONE PREDICATE FOR EVERY COLUMN. The first version of this guard redacted the label and
    left the raw hex printing the passphrase one column to its left, so the decision about
    what may be shown has exactly one home and every renderer asks it.
    """
    if _is_wifi_credential_frame(v):
        return "wifi credentials"
    if _is_device_mac_frame(v):
        return "device mac"
    return None


def render_payload(v: bytes, *, show_secrets: bool = False) -> str:
    """The payload column, with credentials and hardware identity withheld by default."""
    reason = None if show_secrets else secret_reason(v)
    if reason is not None:
        return v[:2].hex() + f" <{reason} withheld>"
    return v.hex()


def label(v: bytes, direction: str, *, show_secrets: bool = False) -> str:
    """Best-effort human label using the known Govee command map."""
    _require_direction(direction)
    reason = None if show_secrets else secret_reason(v)
    h = v[0]
    if _is_music_stream(v):
        return f"mic-stream rgb=({v[3]},{v[4]},{v[5]})"
    if h == 0xA3:
        return f"multi-frame idx={v[1]:#04x} {v[2:12].hex()}"
    if h == 0xA1:
        # H6127/H6199-family multi-part upload; byte[1] is a sub-opcode, byte[2] the index.
        # The index survives redaction: the fragmentation is the structural part worth
        # reading and none of it is secret.
        if reason is not None:
            return f"multi-frame(a1) sub=0x11 idx={v[2]:#04x} <{reason} withheld>"
        return f"multi-frame(a1) sub={v[1]:#04x} idx={v[2]:#04x} {v[3:12].hex()}"
    if h == 0xEE:
        # Device-initiated Wi-Fi association result, seen 2026-08-04 about eleven seconds
        # after an a1 11 credential write, from both the app and a direct write of the same
        # bytes. Only the failing value has been observed, from a network invented for the
        # test that could not possibly exist, so "not connected" is measured while
        # "connected" is the app's own reading of the same byte carried over. Stated that
        # way round deliberately: a successful association has never been captured here.
        if v[1] == 0x11:
            state = "connected" if v[2] == 0 else "NOT connected"
            return f"wifi-connect result={v[2]:#04x} ({state})"
        return f"device-report type={v[1]:#04x} {v[2:12].hex()}"
    if reason is not None:
        return f"reply type={v[1]:#04x} <{reason} withheld>"
    if h == 0xAA:
        return _label_aa(v, direction)
    if h != 0x33:
        return "?"
    action = v[1]
    if direction == "RX":  # device ack/echo of a 0x33 command; payload is a status, not a set value
        names = {
            0x01: "power",
            0x04: "brightness",
            0x05: "colour",
            0x09: "time/cfg",
            0xA9: "display setting",
            0xAE: "relative brightness",
        }
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
            kelvin = int.from_bytes(v[7:9], "big")
            if kelvin:
                return f"colortemp {kelvin}K preview=({v[9]},{v[10]},{v[11]}) mask={_segment_mask(v[12:14])}"
            return f"color rgb=({v[4]},{v[5]},{v[6]}) mask={_segment_mask(v[12:14])}"
        if mode == 0x15 and v[3] == 0x02:
            return f"brightness {v[4]}% mask={_segment_mask(v[5:7])}"
        if mode == 0x15 and v[3] == 0x03:
            # command_write::static_brightness_all: one 0..100 percent per segment,
            # index i = segment i+1, no mask. Rendering it as a bare hex run hid it
            # for as long as we had captures containing it.
            percents = list(v[4:19])
            shown = ",".join(f"s{i + 1}={p}" for i, p in enumerate(percents) if p != 100)
            return f"seg brightness all ({shown or 'all 100%'})"
        if mode == 0x04:
            # status_reply::cm_scene.scene_id is u2le. Falling through to the generic
            # "sub=v[3]" line below renders its LOW BYTE as if it were a selector, so
            # scene 1173 reads as sub=0x95. Same misreading class as the segment mask.
            return f"scene id={int.from_bytes(v[3:5], 'little')} {v[3:13].hex()}"
        if mode == 0x0A:
            # govee_common::diy_selector: slot then type_byte, two independent u1 fields.
            return f"diy slot={v[3]:#04x} type={v[4]:#04x} {v[3:13].hex()}"
        if mode == 0x13:
            # h6199_command_write::music_body. Named rather than left to the generic line
            # below, which rendered it "color/music sub=0x03" and read as a colour write.
            names = {0x03: "rhythm", 0x04: "spectrum", 0x05: "energetic", 0x06: "rolling"}
            return f"music {names.get(v[3], f'mode={v[3]:#04x}')} sensitivity={v[4]}"
        return f"color/{detail} sub={v[3]:#04x} {v[3:13].hex()}"
    if action == 0x09:
        return f"time/cfg {v[2:9].hex()}"
    if action == 0xA9:
        return _label_display_setting(v)
    if action == 0xAE:
        # h6199_command_write::relative_brightness_body. The count sits after a head byte, so the
        # head is not it, and WHICH edge each percentage belongs to is not isolated. Printed in
        # wire order and unnamed for that reason: a label reading "top=100" would be a claim the
        # captures do not support.
        return f"relative brightness edges={','.join(str(p) for p in v[4 : 4 + v[3]])}"
    return f"cmd action={action:#04x} {v[2:13].hex()}"


_PCAPNG_SHB = 0x0A0D0D0A
_PCAPNG_IDB = 0x00000001
_PCAPNG_EPB = 0x00000006
_LINKTYPE_BLUETOOTH_HCI_H4_WITH_PHDR = 201

# idevicebtlogger wrote the BTPacketLogger record's device-LOCAL wall clock straight into a
# classic pcap record, where it is read back as UTC. pymobiledevice3 subtracts the device's
# UTC offset when writing pcapng, precisely so the pcapng timestamp is a true instant. Both
# are normalised to a true instant here so that everything downstream compares like with
# like: a naive comparison against wall-clock action marks looked right for years on the old
# container and would be silently a whole UTC offset out on the new one, printing empty
# segments that read as "the app sent nothing" rather than as a broken tool.
_CLASSIC_PCAP_LAYOUTS = {
    b"\xd4\xc3\xb2\xa1": ("<", 1_000_000),
    b"\xa1\xb2\xc3\xd4": (">", 1_000_000),
    b"\x4d\x3c\xb2\xa1": ("<", 1_000_000_000),
    b"\xa1\xb2\x3c\x4d": (">", 1_000_000_000),
}


def _local_wall_clock_to_instant(epoch_seconds: float) -> datetime:
    """Reinterpret a device-local wall clock that was stored as though it were UTC."""
    rendered = datetime.fromtimestamp(epoch_seconds, UTC).replace(tzinfo=None)
    return rendered.astimezone()


def _iter_classic_pcap(data: bytes, *, allow_truncated: bool) -> Iterator[tuple[datetime, bytes]]:
    if len(data) < 24:
        raise ValueError("pcap header is truncated")
    try:
        endian, timestamp_scale = _CLASSIC_PCAP_LAYOUTS[data[:4]]
    except KeyError as exc:
        raise ValueError("unsupported pcap byte order or timestamp format") from exc
    if struct.unpack(f"{endian}I", data[20:24])[0] != _LINKTYPE_BLUETOOTH_HCI_H4_WITH_PHDR:
        raise ValueError("pcap is not DLT_BLUETOOTH_HCI_H4_WITH_PHDR")
    rec = struct.Struct(f"{endian}IIII")
    off = 24
    while off < len(data):
        if off + 16 > len(data):
            if allow_truncated:
                return
            raise ValueError("pcap record header is truncated")
        seconds, fraction, incl, _ = rec.unpack(data[off : off + 16])
        off += 16
        if off + incl > len(data):
            if allow_truncated:
                return
            raise ValueError("pcap record payload is truncated")
        yield _local_wall_clock_to_instant(seconds + fraction / timestamp_scale), data[off : off + incl]
        off += incl


def _pcapng_timestamp_divisor(options: bytes, endian: str) -> int:
    """Read if_tsresol (option 9) from an Interface Description Block's option list.

    The default really is microseconds, but it is written as an option often enough that
    assuming it is how a capture ends up dated to 1970 or to the far future.
    """
    off = 0
    while off + 4 <= len(options):
        code, length = struct.unpack(f"{endian}HH", options[off : off + 4])
        value = options[off + 4 : off + 4 + length]
        off += 4 + length + (-length % 4)
        if code == 0:  # opt_endofopt
            break
        if code == 9 and len(value) == 1:
            resolution = value[0]
            exponent: int = resolution & 0x7F
            # int(...) because mypy widens int ** int to Any: a negative exponent would give
            # a float. The 0x7F mask makes that impossible here.
            return int(2**exponent) if resolution & 0x80 else int(10**exponent)
    return 1_000_000


def _iter_pcapng(data: bytes, *, allow_truncated: bool) -> Iterator[tuple[datetime, bytes]]:
    endian = "<"
    divisors: dict[int, int] = {}
    off = 0
    while off + 8 <= len(data):
        block_type = struct.unpack(f"{endian}I", data[off : off + 4])[0]
        if block_type == _PCAPNG_SHB:
            # A new section restarts interface numbering and may flip byte order.
            if data[off + 8 : off + 12] == b"\x1a\x2b\x3c\x4d":
                endian = ">"
            elif data[off + 8 : off + 12] == b"\x4d\x3c\x2b\x1a":
                endian = "<"
            else:
                raise ValueError("pcapng section header has no recognisable byte-order magic")
            divisors = {}
        block_length = struct.unpack(f"{endian}I", data[off + 4 : off + 8])[0]
        if block_length < 12 or off + block_length > len(data):
            if allow_truncated:
                return
            raise ValueError("pcapng block is truncated")
        body = data[off + 8 : off + block_length - 4]
        if block_type == _PCAPNG_IDB:
            link_type = struct.unpack(f"{endian}H", body[0:2])[0]
            if link_type != _LINKTYPE_BLUETOOTH_HCI_H4_WITH_PHDR:
                raise ValueError("pcapng is not DLT_BLUETOOTH_HCI_H4_WITH_PHDR")
            divisors[len(divisors)] = _pcapng_timestamp_divisor(body[8:], endian)
        elif block_type == _PCAPNG_EPB:
            interface_id, high, low, captured = struct.unpack(f"{endian}IIII", body[0:16])
            divisor = divisors.get(interface_id, 1_000_000)
            timestamp = datetime.fromtimestamp(((high << 32) | low) / divisor, UTC)
            yield timestamp, body[20 : 20 + captured]
        off += block_length


def iter_frames(data: bytes, *, allow_truncated: bool = False) -> Iterator[tuple[datetime, bytes]]:
    """Yield ``(instant, link-type-201 frame)`` from either capture container.

    Classic pcap comes from idevicebtlogger and pcapng from pymobiledevice3's btlogger.
    The frames are byte-identical between them, so dispatching here is the whole of the
    difference and nothing below this point needs to know which tool produced the file.
    """
    if data[:4] == struct.pack("<I", _PCAPNG_SHB):
        yield from _iter_pcapng(data, allow_truncated=allow_truncated)
    else:
        yield from _iter_classic_pcap(data, allow_truncated=allow_truncated)


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
    """Parse connection lifecycle and attributed ATT records from an iPhone HCI capture.

    Each record carries a CONNECTION EPOCH as well as its handle. A handle is only unique
    while its connection is up: the controller hands the same number back out after a
    disconnect, so two devices can own 0x4e in one capture and counting handles alone would
    merge them. An epoch is minted on every captured connect, dropped on the matching
    disconnect, and minted again the first time a frame arrives on a handle with none, which
    is how a connection that predates the capture gets an identity at all.
    """
    active_connections: dict[int, str] = {}
    open_epochs: dict[int, int] = {}
    minted = 0
    connection_events: list[ConnectionEvent] = []
    att_records: list[AttRecord] = []
    for timestamp, pkt in iter_frames(data, allow_truncated=allow_truncated):
        if len(pkt) < 5:
            continue
        direction = "RX" if (struct.unpack(">I", pkt[0:4])[0] & 1) else "TX"
        h4 = pkt[4:]
        if event := _connection_event(timestamp, h4):
            if event.connected:
                minted += 1
                open_epochs[event.connection_handle] = minted
                if event.address is not None:
                    active_connections[event.connection_handle] = event.address
            else:
                active_connections.pop(event.connection_handle, None)
                open_epochs.pop(event.connection_handle, None)
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
        epoch = open_epochs.get(connection_handle)
        if epoch is None:
            minted += 1
            epoch = open_epochs[connection_handle] = minted
        att_records.append(
            AttRecord(
                timestamp=timestamp,
                direction=direction,
                connection_handle=connection_handle,
                connection_epoch=epoch,
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


UNATTRIBUTED_PREFIX = "?conn-"


def is_unattributed(source: str) -> bool:
    """Whether a source key names a connection whose peer this capture never saw."""
    return source.startswith(UNATTRIBUTED_PREFIX)


def source_labels(records: Iterable[AttRecord]) -> dict[int, str]:
    """Name every connection epoch that carries ATT traffic, for use when no address exists.

    The handle is what an operator can line up against Wireshark, so it leads the name. The
    epoch index is appended only when the same handle is opened more than once in this
    capture, because that is the only time the handle alone is ambiguous and a suffix on
    every line would just be noise.

    Computed over ALL records rather than the Govee ones, so a connection's name does not
    change depending on which filter is being looked through.
    """
    order: dict[int, list[int]] = {}
    for record in records:
        epochs = order.setdefault(record.connection_handle, [])
        if record.connection_epoch not in epochs:
            epochs.append(record.connection_epoch)
    labels: dict[int, str] = {}
    for handle, epochs in order.items():
        for index, epoch in enumerate(epochs, 1):
            suffix = f"#{index}" if len(epochs) > 1 else ""
            labels[epoch] = f"{UNATTRIBUTED_PREFIX}{handle:#04x}{suffix}"
    return labels


def source_of(record: AttRecord, labels: dict[int, str]) -> str:
    """The source key of one record: its peer address, or the connection it arrived on."""
    return record.address or labels[record.connection_epoch]


def govee_sources(trace: CaptureTrace) -> dict[str, int]:
    """Count Govee-shaped frames per source, where a source is ONE BLE CONNECTION.

    A phone talks to every light it is paired with, so a capture is only evidence about
    ONE model if it holds one source or is filtered to one. The address is used when the
    capture saw the connection open, because a device that reconnects mid-capture would
    otherwise count twice. Otherwise the connection itself is the source, which is the
    whole point: the address is the field that goes missing, and a count keyed on it
    reports one source for a capture holding several and reports it as silence rather
    than as an error.
    """
    labels = source_labels(trace.att)
    counts: dict[str, int] = {}
    for record in trace.att:
        if _is_govee(record.value):
            key = source_of(record, labels)
            counts[key] = counts.get(key, 0) + 1
    return counts


class SourceSelectionError(Exception):
    """A --source argument that cannot be resolved to exactly one captured source."""


_HANDLE_PREFIXES = ("0X", "HDL", "HANDLE")


def resolve_source(sources: Iterable[str], wanted: str) -> str:
    """Resolve ``wanted`` to one captured source: an address, an address tail, or a connection.

    Suffix matching exists because a Govee light advertises its address tail in its BLE
    local name (``Govee_H6199_3B73``), so the tail is the identifier actually to hand at
    the rig. A capture that never saw its connections open has no address to offer, so the
    printed connection key (``?conn-0x4e``) and the bare handle (``0x4e``) resolve too:
    refusing to select anything at all would leave the operator with a refusal and no way
    past it, which is how an unreadable capture turns back into an unread one.

    Every unresolvable case raises rather than returning nothing: an address that matches
    no source is a typo, and a typo that filtered everything out would read as a device
    that stayed silent, which is the failure this whole filter exists to stop.
    """
    known = list(sources)
    normal = wanted.upper().replace(":", "").replace("-", "").strip("?")
    if normal.startswith(_HANDLE_PREFIXES) or wanted.startswith("?"):
        handle = normal.removeprefix("CONN").removeprefix("HANDLE").removeprefix("HDL")
        connections = {s: s.removeprefix(UNATTRIBUTED_PREFIX).upper() for s in known if is_unattributed(s)}
        exact = [s for s, name in connections.items() if name == handle]
        if len(exact) == 1:
            return exact[0]
        same_handle = [s for s, name in connections.items() if name.partition("#")[0] == handle]
        if len(same_handle) == 1:
            return same_handle[0]
        if not same_handle:
            raise SourceSelectionError(f"no captured source matches {wanted!r}; captured: {_known(known)}")
        raise SourceSelectionError(
            f"{wanted!r} matches {len(same_handle)} connections: {', '.join(same_handle)}; "
            "that handle was opened more than once here, so name the one you mean"
        )
    addressed = [s for s in known if not is_unattributed(s)]
    exact_address = [s for s in addressed if s.replace(":", "") == normal]
    if exact_address:
        return exact_address[0]
    suffix = [s for s in addressed if s.replace(":", "").endswith(normal)]
    if len(suffix) == 1:
        return suffix[0]
    if not suffix:
        raise SourceSelectionError(f"no captured source matches {wanted!r}; captured: {_known(known)}")
    raise SourceSelectionError(f"{wanted!r} matches {len(suffix)} peers: {', '.join(suffix)}")


def _known(sources: Iterable[str]) -> str:
    """List what IS in the capture, connections included.

    Listing only addresses is what turned the failing case into a dead end: an unattributed
    capture answered ``captured: none``, which reads as an empty capture rather than as one
    holding two connections nobody ever named.
    """
    return ", ".join(sources) or "none"


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").strip().splitlines()[0])
    parser.add_argument("capture", help="pcapng or pcap file from govee-capture.sh")
    parser.add_argument("--all", action="store_true", help="also print ATT values that are not Govee")
    parser.add_argument(
        "--source",
        "--peer",
        dest="source",
        help="keep only frames from one source; a BLE address, a unique address tail, or a connection (?conn-0x4e)",
    )
    parser.add_argument(
        "--allow-unattributed",
        action="store_true",
        help="accept frames whose connection this capture never saw open, so no address is known for them",
    )
    parser.add_argument(
        "--all-peers",
        action="store_true",
        help="print a capture holding more than one Govee source without narrowing it first",
    )
    parser.add_argument(
        "--show-secrets",
        action="store_true",
        help="print payloads withheld by default: Wi-Fi credentials (a1 11) and the device Wi-Fi MAC (aa 14)",
    )
    opts = parser.parse_args()

    data = open(opts.capture, "rb").read()
    trace = parse_capture(data)
    sources = govee_sources(trace)
    labels = source_labels(trace.att)
    header = f"# {opts.capture}\n# Govee sources: {_render_sources(sources) or 'none'}"

    # ORDER MATTERS: contamination is reported before incompleteness. A capture holding two
    # sources invalidates every row below it whatever else is true of it, and it is the
    # finding an operator must not be able to walk past while fixing something smaller.
    #
    # A dump the operator forgot to narrow is the trap, not the one they narrowed wrongly.
    # More than one Govee source means every row below could belong to either, and a
    # mixed dump reads exactly like a single device's session. An opt-in filter you can
    # forget protects nothing, so this refuses rather than warns.
    if opts.source is None and len(sources) > 1 and not opts.all_peers:
        print(header)
        print(
            f"error: this capture holds {len(sources)} Govee sources, so nothing read off it is "
            "evidence about one model. Narrow it with --source <address, address tail or connection>, "
            "or pass --all-peers to dump it mixed on purpose.",
            file=sys.stderr,
        )
        return 2

    wanted: str | None = None
    if opts.source is not None:
        try:
            wanted = resolve_source(sources, opts.source)
        except SourceSelectionError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    # --allow-unattributed accepts ONE thing: that some frames belong to a connection this
    # capture never saw open, so no address is known for them. It deliberately does NOT
    # suppress the refusal above. Those are separate claims: this one is about how complete
    # the naming is, that one is about whether two devices are mixed together. Letting it
    # cover both would disarm the guard on exactly the captures that have nothing else left
    # to go on, and govee-capture.sh passes it on every unbound stop, so the fix would be
    # dead at the call site that swallowed the failing session in the first place.
    unattributed = [s for s in sources if is_unattributed(s)]
    if unattributed and not opts.allow_unattributed:
        print(header)
        print(
            f"error: {sum(sources[s] for s in unattributed)} Govee frame(s) on {len(unattributed)} "
            f"connection(s) ({', '.join(unattributed)}) cannot be attributed to a peer, because those "
            "connections were opened before the capture started. Recapture with the app restarted inside "
            "the capture window, or pass --allow-unattributed to read them as frames from a device this "
            "capture never named.",
            file=sys.stderr,
        )
        return 2

    rows = []
    seen: set[bytes] = set()
    total = govee = 0
    for record in trace.att:
        source = source_of(record, labels)
        if wanted is not None and source != wanted:
            continue
        value = record.value
        total += 1
        if _is_govee(value):
            govee += 1
            first = value not in seen
            seen.add(value)
            rows.append(
                (
                    source,
                    record.direction,
                    record.opcode,
                    record.attribute_handle,
                    value,
                    label(value, record.direction, show_secrets=opts.show_secrets),
                    first,
                )
            )
        elif opts.all and value:
            rows.append((source, record.direction, record.opcode, record.attribute_handle, value, "(non-govee)", True))

    print(f"# {opts.capture}")
    print(f"# ATT writes/notifications: {total}   Govee packets: {govee}   unique Govee: {len(seen)}")
    # Always printed, and always before the rows, because "this capture holds two lights"
    # is a fact that invalidates every reading below it and must not have to be noticed.
    print(f"# Govee sources: {_render_sources(sources) or 'none'}")
    if wanted is not None:
        print(f"# filtered to source {wanted}")
    elif len(sources) > 1:
        print("# WARNING: more than one Govee source here; this capture is not evidence about one model")
    if wanted is None or is_unattributed(wanted):
        for source in unattributed if wanted is None else [wanted]:
            print(f"# WARNING: {source} was never named; this capture cannot say which device it was")
    print(f"# {'source':<17} {'dir':<3} {'op':<12} {'hdl':<6} {'payload (hex)':<41} label")
    for source, direction, opcode, handle, value, lab, first in rows:
        mark = " " if first else "."
        print(
            f"{mark} {source:<17} {direction:<3} {WRITE_OPCODES[opcode]:<12} {handle:#06x} "
            f"{render_payload(value, show_secrets=opts.show_secrets):<41} {lab}"
        )
    if not opts.all:
        print("# ('.' = repeat of an earlier packet; pass --all to include non-Govee ATT values)")
    return 0


def _render_sources(sources: dict[str, int]) -> str:
    return "  ".join(f"{source}={count}" for source, count in sorted(sources.items(), key=lambda kv: (-kv[1], kv[0])))


if __name__ == "__main__":
    raise SystemExit(main())
