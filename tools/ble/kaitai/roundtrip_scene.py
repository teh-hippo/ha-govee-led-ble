#!/usr/bin/env python3
"""Crux experiment: does the record-framing scene_body.ksy consume the real
type-2 scene bodies byte-exact, with the record count + length-prefixed records
landing and only transport zero-padding left over?

Captures are ground truth. Prints the parsed framing so it can be eyeballed,
and asserts: whole body consumed, padding all zero; the two Aurora Slow/Fast
bodies differ only inside record data (the speed step at on-wire 18 & 68); and
the Forest body (record_count 3, live 2026-07-22) proves the framing generalises
past Aurora's record_count 2 with the record_type byte varying across records.
"""

import io
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from kaitaistruct import KaitaiStream  # noqa: E402
from scene_body import SceneBody  # noqa: E402

# Inline type-2 scene bodies. Embedded so the harness is self-contained without the
# gitignored fixtures.json or the capture mount.
#  - Aurora Slow vs Fast (scene-speed capture, record_count 2): differ only at on-wire
#    offsets 18 & 68 (the speed step).
#  - Forest (forest-body capture, record_count 3, code 2163, live 2026-07-22): a
#    structurally different type-2 body whose three records carry record_type 1/2/0,
#    proving the framing generalises past Aurora's two same-type records.
AURORA_BODIES = [
    "0105020220000000010201ff320100000000fa320300ff7f007fff2aff000300800000000023000000030201ff1900fa000002fa000400ff007fff00a0cfff007fff1401fa0000ff00000000000000000000000000",
    "0105020220000000010201ff320100000000e8320300ff7f007fff2aff000300800000000023000000030201ff1900fa000002fa000400ff007fff00a0cfff007fff1401f40000ff00000000000000000000000000",
]
FOREST_BODY = "01070203260001000a0201ff1901b40a0a02c8140500ff000000ffffffff0000ff00ff6b140196000000002300020f050201ff1401fb000001fa0a0400fffb00ff4b4747ff00ff1b000000000000001a000000010201ff0501c8141402ee140100ffff0000000000000000000000000000000000000000"
bodies = list(dict.fromkeys(AURORA_BODIES)) + [FOREST_BODY]


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
    print(
        f"body{i}: scene_type={k.scene_type.name} record_count={k.record_count} used={rec_span}B pad={len(k.padding)}B pad0={pad_zero} consumed={consumed}"
    )
    for j, (ln, ty, bc, cr) in enumerate(recs):
        print(f"   rec{j}: len={ln} type={ty} bright_count={bc} colour_rest={cr}")
    print(f"       used={rec_span}B padding={len(k.padding)}B pad_all_zero={pad_zero} consumed_all={consumed}")

# differential: the two bodies must differ only inside record data, not in framing
if len(parsed) >= 2:
    (r0, k0, span0), (r1, k1, span1) = parsed[0], parsed[1]
    diff = [i for i, (a, b) in enumerate(zip(r0, r1, strict=True)) if a != b]
    in_records = all(4 <= off < span0 for off in diff)
    print(f"\ndiff offsets body0 vs body1: {[(o, hex(r0[o]), hex(r1[o])) for o in diff]}")
    print(f"all diffs inside record data (>=4, <used {span0})? {in_records}")
    print(f"framing bytes (marker/linecount/scene_type/record_count) identical? {r0[:4] == r1[:4]}")
    if not in_records or r0[:4] != r1[:4]:
        fails += 1

# generalisation: Forest (record_count 3) parses byte-exact with record_type varying
if len(parsed) >= 3:
    kf = parsed[2][1]
    rec_types = [r.body.record_type for r in kf.records]
    gen_ok = kf.record_count == 3 and rec_types == [1, 2, 0] and kf._io.is_eof() and set(kf.padding) <= {0}
    print(
        f"\nForest generalisation: record_count={kf.record_count} record_types={rec_types} consumed={kf._io.is_eof()}"
    )
    print(f"framing generalises past Aurora record_count 2 with record_type varying? {gen_ok}")
    if not gen_ok:
        fails += 1

print("\nCRUX PASS" if not fails else f"\nCRUX FAIL ({fails})")
sys.exit(1 if fails else 0)
