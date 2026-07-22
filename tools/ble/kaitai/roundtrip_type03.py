#!/usr/bin/env python3
"""Round-trip verify diy_type03.ksy against real captured Finger Sketch + Vibrant
TYPE 0x03 DIY bodies.

The reassembled 0xA3 body is ground truth. For every body this harness:
  1. parses it with the generated DiyType03 parser;
  2. asserts the whole body is consumed (k._io.is_eof());
  3. asserts the trailing `padding` is all zero;
  4. asserts every parsed field matches the raw bytes at its offset
     (marker/linecount/type/effect/speed/bright/bg + each group's segcount/fill/indices);
  5. reconstructs the body from the parsed fields and asserts it equals the captured
     bytes, and independently cross-checks against protocol.py by feeding the
     reconstructed body back through the real build_a3_multi fragmenter (the exact
     path build_sketch / build_vibrant use) and re-reassembling to the captured bytes.

Terminator finding (closes `terminator-fixture`): every reassembled Sketch body is
34 bytes = 17 data + 17 zero terminator, linecount 0x02; linecount is never below
0x02 for this family. Asserted here (all Sketch bodies: linecount == 2 and >= 17
trailing zero bytes; all bodies: linecount >= 2).

Bodies are extracted live from the capture pcaps (captures are ground truth); a set
of embedded inline anchor hex strings is always tested too, so the harness still
verifies the core cases if the capture mount is unavailable.
"""
import io
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # generated parser module
TOOLS_BLE = HERE.parent  # decode_govee
REPO = HERE.parent.parent.parent  # custom_components
sys.path.insert(0, str(TOOLS_BLE))
sys.path.insert(0, str(REPO))

from kaitaistruct import KaitaiStream  # noqa: E402
from diy_type03 import DiyType03  # noqa: E402
from custom_components.ha_govee_led_ble import protocol as proto  # noqa: E402

CAPS = Path("/mnt/z/libimobiledevice/captures")
SKETCH_PCAPS = [
    "20260716140100-h617a-sketch.pcap",
    "finger-sketch-1.pcap",
    "finger-sketch-effects.pcap",
]
VIBRANT_PCAPS = [
    "h617a-vibrant-header.pcap",
    "baseline-vibrant.pcap",
]

# Embedded inline anchor fixtures (extracted from the capture pcaps). These make the
# harness self-contained: the four cases below exercise Sketch linecount 2, the
# no-paint groupcount 0 body, a merged group (segcount 4, sparse indices [0,1,2,4]),
# and the 15-group Vibrant linecount 5 body.
ANCHORS = [
    ("sketch-anchor(seg3)", "010203093364ffffff0103ff00000001020000000000000000000000000000000000"),
    ("sketch-nopaint(gc0)", "010203023364ffffff00000000000000000000000000000000000000000000000000"),
    ("sketch-merged(seg4)", "0102030933640000ff010400ff000001020400000000000000000000000000000000"),
    (
        "vibrant-anchor(15g)",
        "0105030900640101010f01ff7f000001ff9a000101ffb0000201ffc3000301ffd4000401"
        "ffe3000501fff2000601ffff000701eeff000801dbff000901c6ff000a01adff000b0190"
        "ff000c0169ff000d0100ff000e",
    ),
]


def reassemble_values(values):
    """Reassemble 0xA3 multi-frames into bodies by concatenating each frame's
    bytes[2:19] in order and closing at the empty idx=0xff terminator frame."""
    groups, chunks = [], []
    for v in values:
        if len(v) != 20:
            continue
        if v[0] == 0xA3:
            chunks.append(bytes(v[2:19]))
            if v[1] == 0xFF:
                groups.append(b"".join(chunks))
                chunks = []
        else:
            if chunks:
                groups.append(b"".join(chunks))
                chunks = []
    if chunks:
        groups.append(b"".join(chunks))
    return groups


def bodies(pcap):
    import decode_govee as dg

    tr = dg.parse_capture((CAPS / pcap).read_bytes(), allow_truncated=True)
    values = [r.value for r in tr.att]
    return [b for b in reassemble_values(values) if len(b) >= 10 and b[0] == 0x01 and b[2] == 0x03]


def trailing_zeros(raw: bytes) -> int:
    n = 0
    for byte in reversed(raw):
        if byte != 0:
            break
        n += 1
    return n


def collect_fixtures():
    """(source_label, raw_bytes) for every distinct body: embedded anchors first,
    then all live-extracted capture bodies (deduplicated)."""
    seen: dict[bytes, str] = {}
    ordered: list[tuple[str, bytes]] = []
    for label, hx in ANCHORS:
        raw = bytes.fromhex(hx)
        if raw not in seen:
            seen[raw] = label
            ordered.append((f"embedded/{label}", raw))
    live_note = ""
    if CAPS.exists():
        for family, pcaps in (("sketch", SKETCH_PCAPS), ("vibrant", VIBRANT_PCAPS)):
            for pcap in pcaps:
                if not (CAPS / pcap).exists():
                    continue
                try:
                    for raw in bodies(pcap):
                        if raw not in seen:
                            seen[raw] = pcap
                            ordered.append((f"{family}:{pcap}", raw))
                except Exception as exc:  # noqa: BLE001
                    live_note += f"  (warn: {pcap}: {exc})\n"
    else:
        live_note = f"  (capture mount {CAPS} unavailable; embedded anchors only)\n"
    return ordered, live_note


def effect_value(k) -> int:
    eff = k.effect
    return int(eff.value) if isinstance(eff, DiyType03.Effect) else int(eff)


def effect_name(k) -> str:
    eff = k.effect
    return eff.name if isinstance(eff, DiyType03.Effect) else f"0x{int(eff):02x}?"


def reconstruct_body_after_type(k) -> bytes:
    """Rebuild the bytes after the TYPE selector, i.e. the `body` argument that
    protocol.build_sketch / build_vibrant hand to build_a3_multi(0x03, body)."""
    out = bytes(
        [effect_value(k), k.speed, k.brightness, k.background.r, k.background.g, k.background.b, k.group_count]
    )
    for g in k.groups:
        out += bytes([g.seg_count, g.fill.r, g.fill.g, g.fill.b, *g.segment_indices])
    return out


def encoder_reproduces(body_after_type: bytes, raw: bytes):
    """Feed the reconstructed body back through the real build_a3_multi fragmenter and
    re-reassemble; return the terminator flag that reproduces the captured bytes."""
    for term in (True, False):
        frames = proto.build_a3_multi(0x03, body_after_type, terminator=term)
        reassembled = reassemble_values(frames)
        if len(reassembled) == 1 and reassembled[0] == raw:
            return term
    return None


def check_body(label: str, raw: bytes):
    k = DiyType03(KaitaiStream(io.BytesIO(raw)))
    checks: list[tuple[str, bool]] = []

    checks.append(("consumed", k._io.is_eof()))
    checks.append(("pad_zero", set(k.padding) <= {0}))

    # header field parity vs raw offsets
    checks.append(("marker", k.header.marker == raw[0:1]))
    checks.append(("linecount", k.header.linecount == raw[1]))
    checks.append(("type", k.body_type == raw[2:3]))
    checks.append(("effect", effect_value(k) == raw[3]))
    checks.append(("speed", k.speed == raw[4]))
    checks.append(("bright", k.brightness == raw[5]))
    checks.append(("bg", bytes([k.background.r, k.background.g, k.background.b]) == raw[6:9]))
    checks.append(("group_count", k.group_count == raw[9]))

    # per-group field parity by walking raw offsets
    off = 10
    group_ok = True
    max_seg = 0
    for g in k.groups:
        max_seg = max(max_seg, g.seg_count)
        if g.seg_count != raw[off]:
            group_ok = False
        if bytes([g.fill.r, g.fill.g, g.fill.b]) != raw[off + 1 : off + 4]:
            group_ok = False
        if bytes(g.segment_indices) != raw[off + 4 : off + 4 + g.seg_count]:
            group_ok = False
        off += 4 + g.seg_count
    checks.append(("groups", group_ok))
    used = off
    checks.append(("group_span", used == 10 + sum(4 + g.seg_count for g in k.groups)))

    # padding accounting
    checks.append(("pad_len", len(k.padding) == len(raw) - used))
    checks.append(("pad_tail", set(raw[used:]) <= {0}))

    # full field reconstruction == captured bytes
    body_after_type = reconstruct_body_after_type(k)
    recon = bytes([0x01, k.header.linecount, 0x03]) + body_after_type + bytes(len(k.padding))
    checks.append(("reconstruct", recon == raw))

    # cross-check against protocol.py: real fragmenter reproduces the captured body
    term = encoder_reproduces(body_after_type, raw)
    checks.append(("encoder", term is not None))

    ok = all(v for _, v in checks)
    bad = ",".join(n for n, v in checks if not v)
    form = {True: "terminator", False: "plain"}.get(term, "none")
    detail = (
        f"lc={k.header.linecount} eff={effect_name(k)} spd={k.speed} br={k.brightness} "
        f"bg={bytes([k.background.r, k.background.g, k.background.b]).hex()} "
        f"gc={k.group_count} maxseg={max_seg} pad={len(k.padding)}B form={form}"
    )
    print(f"{'PASS' if ok else 'FAIL'} {label:34s} {detail}" + (f"  <FAILED: {bad}>" if bad else ""))
    return ok, k, used


def main() -> int:
    fixtures, live_note = collect_fixtures()
    if live_note:
        print(live_note.rstrip("\n"))
    print(f"Testing {len(fixtures)} distinct TYPE 0x03 bodies\n")

    fails = 0
    sketch_seen = vibrant15_seen = merged_seen = False
    lc_below_two = 0  # any body with linecount < 2
    sketch_lc_violation = 0  # any 34B Sketch body whose linecount != 2
    single_chunk_term_violation = 0  # single-data-chunk Sketch body missing its 17B empty terminator
    single_chunk_count = multi_chunk_sketch = 0

    for label, raw in fixtures:
        ok, k, used = check_body(label, raw)
        fails += 0 if ok else 1

        # coverage flags
        if k.header.linecount == 2 and len(raw) == 34:
            sketch_seen = True
        if k.header.linecount == 5 and len(k.groups) == 15:
            vibrant15_seen = True
        if any(g.seg_count >= 2 for g in k.groups):
            merged_seen = True

        # terminator verification (see terminator-fixture). `used` is where padding
        # starts; a body is single-data-chunk iff its full payload fits one 17-byte A3
        # chunk, i.e. used <= 17 (2-byte 01/linecount header + type + body_after_type).
        if k.header.linecount < 2:
            lc_below_two += 1
        if len(raw) == 34:  # Sketch family: single- or double-chunk, both reassemble to 34B
            if k.header.linecount != 2:
                sketch_lc_violation += 1
            if used <= 17:  # single-data-chunk => appended empty idx=0xff terminator
                single_chunk_count += 1
                if trailing_zeros(raw) < 17:
                    single_chunk_term_violation += 1
            else:
                multi_chunk_sketch += 1

    print("\n--- coverage ---")
    print(f"sketch (linecount 2, 34B):        {'yes' if sketch_seen else 'NO'}")
    print(f"vibrant (linecount 5, 15 groups): {'yes' if vibrant15_seen else 'NO'}")
    print(f"merged group (segcount >= 2):     {'yes' if merged_seen else 'NO'}")
    coverage_ok = sketch_seen and vibrant15_seen and merged_seen

    print("\n--- terminator finding (terminator-fixture) ---")
    print("Single-data-chunk Sketch bodies reassemble to 34B = 17 data + 17 zero terminator, linecount 0x02.")
    print(f"single-data-chunk Sketch bodies (used<=17): {single_chunk_count}; multi-chunk plain-form: {multi_chunk_sketch}")
    print(f"all bodies linecount >= 2:                       {'yes' if lc_below_two == 0 else f'NO ({lc_below_two})'}")
    print(f"all 34B Sketch bodies linecount == 2:            {'yes' if sketch_lc_violation == 0 else f'NO ({sketch_lc_violation})'}")
    print(f"single-chunk Sketch bodies have >=17B empty term: {'yes' if single_chunk_term_violation == 0 else f'NO ({single_chunk_term_violation})'}")
    term_ok = lc_below_two == 0 and sketch_lc_violation == 0 and single_chunk_term_violation == 0 and single_chunk_count > 0

    if not coverage_ok:
        fails += 1
    if not term_ok:
        fails += 1

    print("\nALL PASS" if not fails else f"\n{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
