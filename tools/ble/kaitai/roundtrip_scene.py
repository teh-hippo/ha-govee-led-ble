#!/usr/bin/env python3
"""Crux experiment: does the record-framing scene_body.ksy consume the real
Aurora scene bodies byte-exact, with the record count + length-prefixed records
landing and only transport zero-padding left over?

Captures are ground truth. Prints the parsed framing so it can be eyeballed,
and asserts: whole body consumed, padding all zero, and the two Slow/Fast
bodies differ only inside record data (the speed step at on-wire 18 & 68).
"""
import io
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from kaitaistruct import KaitaiStream  # noqa: E402
from scene_body import SceneBody  # noqa: E402

fx = json.loads((HERE / "fixtures.json").read_text())
bodies = [b["body"] for b in fx["20260716151500-h617a-scene-speed.pcap"]["a3_bodies"] if b["len"] == 85]
bodies = list(dict.fromkeys(bodies))  # distinct, preserve order


def parse(hx: str):
    raw = bytes.fromhex(hx)
    k = SceneBody(KaitaiStream(io.BytesIO(raw)))
    return raw, k


fails = 0
parsed = []
for i, hx in enumerate(bodies):
    raw, k = parse(hx)
    consumed = k._io.is_eof()
    pad_zero = set(k.padding) <= {0}
    recs = [(r.rec_len, r.body.record_type, r.body.bright_count, r.body.colour_and_rest.hex()) for r in k.records]
    rec_span = 4 + sum(1 + r.rec_len for r in k.records)  # bytes used by prefix+records
    parsed.append((raw, k, rec_span))
    ok = consumed and pad_zero
    fails += 0 if ok else 1
    print(f"body{i}: scene_type={k.scene_type.name} record_count={k.record_count} used={rec_span}B pad={len(k.padding)}B pad0={pad_zero} consumed={consumed}")
    for j, (ln, ty, bc, cr) in enumerate(recs):
        print(f"   rec{j}: len={ln} type={ty} bright_count={bc} colour_rest={cr}")
    print(f"       used={rec_span}B padding={len(k.padding)}B pad_all_zero={pad_zero} consumed_all={consumed}")

# differential: the two bodies must differ only inside record data, not in framing
if len(parsed) >= 2:
    (r0, k0, span0), (r1, k1, span1) = parsed[0], parsed[1]
    diff = [i for i, (a, b) in enumerate(zip(r0, r1)) if a != b]
    in_records = all(4 <= off < span0 for off in diff)
    print(f"\ndiff offsets body0 vs body1: {[(o, hex(r0[o]), hex(r1[o])) for o in diff]}")
    print(f"all diffs inside record data (>=4, <used {span0})? {in_records}")
    print(f"framing bytes (marker/linecount/scene_type/record_count) identical? {r0[:4] == r1[:4]}")
    if not in_records or r0[:4] != r1[:4]:
        fails += 1

print("\nCRUX PASS" if not fails else f"\nCRUX FAIL ({fails})")
sys.exit(1 if fails else 0)
