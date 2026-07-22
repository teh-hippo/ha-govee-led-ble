#!/usr/bin/env python3
"""Round-trip verify music_body.ksy against real captured H617A music wire bytes.

Two structures, extracted from real captures (captures are ground truth); most
fixtures are from 20260716120000-h617a-music-walkthrough.pcap, with a few count=7
and Day & Night variants from h617a-s7.pcap / music-surface.pcap. Embedded inline:

  * the reassembled 0xA3 command-0x41 per-mode movement-parameter BODY
    (parsed by the MusicBody root type), and
  * the full 20-byte ``33 05 13`` music mode-set FRAME
    (parsed by MusicBody.ModeSetFrame).

For each 0x41 body: parse with the generated parser, assert the whole body is
consumed, the transport padding is all zero, and the marker/command/mode/count +
palette + opaque per-mode tail region round-trip byte-exact.

For each mode-set frame: validate the XOR checksum host-side (Kaitai cannot fold),
parse, assert full consumption + field parity, and cross-check that the shipped
protocol.build_music_mode_with_color reproduces the frame byte-exact.

Prints PASS/FAIL per fixture and exits non-zero on any failure.
"""

import io
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # generated parser module
REPO = HERE.parent.parent.parent
sys.path.insert(0, str(REPO))

from kaitaistruct import KaitaiStream  # noqa: E402
from music_body import MusicBody  # noqa: E402

from custom_components.ha_govee_led_ble import protocol as proto  # noqa: E402

# --- Structure 2: reassembled 0xA3 command-0x41 per-mode movement bodies ----------------------
# (name, body hex). Layout: 01 <frag> 41 <mode> <count> <RGB x count> <tail> <zero pad>.
BODIES = [
    ("separation_a", "0102413205ff7f00ff0000ffff000000ff00ff000200610000000000000000000000"),
    ("separation_b", "0102413205ff7f00ff0000ffff000000ff00ff0002015e0000000000000000000000"),
    (
        "hopping",
        "0103413307ff0000ff7f00ffff0000ff000000ff00ffff8b00ffff000031620103020600000000000000000000000000000000",
    ),
    ("piano_keys", "0102413407ff0000ff7f00ffff0000ff000000ff00ffff8b00ff00090a0404000000"),
    ("fountain", "0102413507ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0101035000000000"),
    ("day_and_night", "0102413707ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0201000000000000"),
    ("bloom", "0102413007ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0a14000000000000"),
    ("shiny_calm", "0102413105ff0000ff7f00ffff0000ff000000ff14460a0000000000000000000000"),
    ("shiny_dynamic", "0102413105ff0000ff7f00ffff0000ff000000ff05640a0000000000000000000000"),
    # count=7 variants prove the tail is RELATIVE to palette end: same tail after a 7-colour palette.
    ("shiny_count7", "0102413107ff0000ff7f00ffff0000ff000000ff00ffff8b00ff05640a0000000000"),
    ("separation_count7", "0102413207ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0300610000000000"),
    # day_and_night with a non-zero third tail byte (+2): proves the region is 3 bytes, not 2.
    ("day_and_night_b", "0102413707ff0000ff7f00ffff0000ff000000ff00ffff8b00ff022c010000000000"),
]

# Per-mode opaque tail length in bytes (relative, counted from the end of the palette).
# Independently asserted against the grammar's computed tail_len. Set to the largest parameter
# block observed for each mode across ALL available captures (a single capture can leave trailing
# params zero and under-count: Day & Night is 3, though it looks like 2 in the walkthrough alone).
TAIL_LEN = {0x30: 2, 0x31: 3, 0x32: 3, 0x33: 9, 0x34: 5, 0x35: 4, 0x37: 3}

# --- Structure 1: full 20-byte 33 05 13 music mode-set frames ---------------------------------
# (name, frame hex). Layout: 33 05 13 <mode> <sens> <style> <count> <RGB x count> <pad> <xor>.
FRAMES = [
    ("rhythm_c1_8b00ff", "330513036300018b00ff00000000000000000030"),
    ("rhythm_c1_ff0000", "33051303630001ff0000000000000000000000bb"),
    ("rhythm_c1_0000ff", "330513036300010000ff000000000000000000bb"),
    ("rhythm_c0_dynamic", "3305130363000000000000000000000000000045"),
    ("rhythm_c0_calm", "3305130363010000000000000000000000000044"),
    ("rhythm_sens0", "3305130300000100e6d200000000000000000013"),
    ("rhythm_sens47", "330513032f000100e6d20000000000000000003c"),
    ("energetic_c1", "3305130563000100e6d200000000000000000076"),
    ("spectrum_c0", "330513040e00000000000000000000000000002f"),
    ("rolling_c0", "330513060e00000000000000000000000000002d"),
    ("separation_c0", "3305133263000000000000000000000000000074"),
    ("hopping_c0", "3305133363000000000000000000000000000075"),
    ("piano_keys_c0", "3305133463000000000000000000000000000072"),
    ("fountain_c0", "3305133563000000000000000000000000000073"),
    ("day_and_night_c0", "3305133763000000000000000000000000000071"),
    ("bloom_c0_calm", "3305133063010000000000000000000000000077"),
    ("shiny_c0_calm", "3305133163010000000000000000000000000076"),
    ("shiny_c0_dynamic", "3305133163000000000000000000000000000077"),
]


def xor(frame: bytes) -> int:
    c = 0
    for b in frame[:19]:
        c ^= b
    return c


def check_body(name: str, hx: str) -> tuple[bool, str, int]:
    raw = bytes.fromhex(hx)
    k = MusicBody(KaitaiStream(io.BytesIO(raw)))
    mode_val = int(k.mode)
    count = k.count
    palette_end = 5 + 3 * count
    exp_tail_len = TAIL_LEN[mode_val]
    cap_tail = raw[palette_end : palette_end + exp_tail_len]
    cap_pad = raw[palette_end + exp_tail_len :]
    palette_bytes = b"".join(bytes([c.r, c.g, c.b]) for c in k.palette)
    raw_tail = k._raw_tail
    rebuilt = bytes([0x01, k.header.linecount, 0x41, mode_val, count]) + palette_bytes + raw_tail + bytes(k.padding)
    checks = [
        ("consumed", k._io.is_eof()),
        ("marker", k.header.marker == b"\x01"),
        ("command", k.command == b"\x41"),
        ("mode", mode_val == raw[3]),
        ("count", count == raw[4]),
        ("palette", palette_bytes == raw[5:palette_end]),
        ("tail_len", len(raw_tail) == exp_tail_len),
        ("tail_bytes", raw_tail == cap_tail),
        ("padding_zero", set(k.padding) <= {0}),
        ("padding_bytes", bytes(k.padding) == cap_pad),
        ("roundtrip", rebuilt == raw),
    ]
    # per-mode decoded tail field spot-checks (offsets relative to palette end)
    t = k.tail
    if mode_val == 0x30:  # bloom
        checks.append(("bloom", t.style_companion == cap_tail[1]))
    elif mode_val == 0x31:  # shiny
        checks.append(("shiny", bytes(t.style_companion) == cap_tail[:2]))
    elif mode_val == 0x32:  # separation
        checks.append(("sep", (t.point, t.gradient, t.companion) == tuple(cap_tail[:3])))
    elif mode_val == 0x33:  # hopping
        checks.append(
            ("hop", (t.background.r, t.background.g, t.background.b, t.rel_brightness) == tuple(cap_tail[:4]))
        )
    elif mode_val == 0x34:  # piano_keys
        checks.append(("piano", (t.gradient, t.key_count, t.derived_half) == (cap_tail[0], cap_tail[1], cap_tail[4])))
    elif mode_val == 0x35:  # fountain
        checks.append(("fountain", (t.direction_lo, t.direction_hi) == (cap_tail[0], cap_tail[2])))
    elif mode_val == 0x37:  # day_and_night
        checks.append(("dn", (t.segment_count, t.speed, t.gradient) == tuple(cap_tail[:3])))
    ok = all(v for _, v in checks)
    bad = ",".join(n for n, v in checks if not v)
    detail = (
        f"mode={k.mode.name}({mode_val:#04x}) count={count} palette={palette_bytes.hex()} "
        f"tail={raw_tail.hex()} pad={len(k.padding)}B"
    )
    return ok, f"{name:14s} {detail}" + (f"  <FAILED: {bad}>" if bad else ""), mode_val


def check_frame(name: str, hx: str) -> tuple[bool, str, int]:
    raw = bytes.fromhex(hx)
    checks = [("xor", xor(raw) == raw[19])]
    k = MusicBody.ModeSetFrame(KaitaiStream(io.BytesIO(raw)))
    mode_val = int(k.mode)
    sens = k.sensitivity
    style_val = int(k.style)
    count = k.count
    colors = [bytes([c.r, c.g, c.b]) for c in k.colors]
    checks += [
        ("consumed", k._io.is_eof()),
        ("mode", mode_val == raw[3]),
        ("sens", sens == raw[4]),
        ("style", style_val == raw[5]),
        ("count", count == raw[6]),
        ("padding_zero", set(k.padding) <= {0}),
    ]
    if count >= 1:
        checks.append(("rgb", colors[0] == raw[7:10]))
    color = tuple(raw[7:10]) if count >= 1 else None
    if count <= 1:  # build_music_mode_with_color emits at most one manual colour
        rep = proto.build_music_mode_with_color(mode_val, sens, color, calm=bool(style_val))
        checks.append(("build_reproduces", rep == raw))
    ok = all(v for _, v in checks)
    bad = ",".join(n for n, v in checks if not v)
    detail = (
        f"mode={k.mode.name}({mode_val:#04x}) sens={sens} style={style_val:#04x} count={count} "
        f"rgb={colors[0].hex() if count >= 1 else None}"
    )
    return ok, f"{name:18s} {detail}" + (f"  <FAILED: {bad}>" if bad else ""), mode_val


def main() -> int:
    fails = 0
    body_modes: set[int] = set()
    frame_modes: set[int] = set()

    print("=== Structure 2: reassembled 0xA3 command-0x41 per-mode movement BODIES ===")
    body_pass = 0
    for name, hx in BODIES:
        ok, line, mode_val = check_body(name, hx)
        fails += 0 if ok else 1
        body_pass += 1 if ok else 0
        body_modes.add(mode_val)
        print(f"{'PASS' if ok else 'FAIL'} {line}")

    print("\n=== Structure 1: full 20-byte 33 05 13 music mode-set FRAMES ===")
    frame_pass = 0
    for name, hx in FRAMES:
        ok, line, mode_val = check_frame(name, hx)
        fails += 0 if ok else 1
        frame_pass += 1 if ok else 0
        frame_modes.add(mode_val)
        print(f"{'PASS' if ok else 'FAIL'} {line}")

    names = {v: k for k, v in proto.MUSIC_MODE_SLUGS.items()}
    print(
        f"\n0x41 bodies round-tripped byte-exact: {body_pass}/{len(BODIES)} "
        f"across modes: {', '.join(sorted(names.get(m, hex(m)) for m in body_modes))}"
    )
    print(
        f"33 05 13 frames round-tripped byte-exact: {frame_pass}/{len(FRAMES)} "
        f"across modes: {', '.join(sorted(names.get(m, hex(m)) for m in frame_modes))}"
    )
    print("\nALL PASS" if not fails else f"\n{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
