#!/usr/bin/env python3
"""Round-trip verify workshop_body.ksy against real captured H617A Workshop bodies.

Workshop is the length-delimited layer container uploaded as A3 TYPE 0x02 and
activated with 33 05 04 91 01 02. These bodies are reassembled 0xA3 payloads (each
frame's bytes[2:19] concatenated by the host); captures are ground truth.

The harness proves, for every embedded body:
  1. it parses with the generated WorkshopBody;
  2. the whole body is consumed (k._io.is_eof());
  3. the transport padding is all zero;
  4. layer_count matches, each record_len matches the bytes it spans, and
     4 (header) + sum(record spans) + padding == body length;
  5. the Christmas draft's five records tile applied-area r1 as 20 22 24 26 28.

It then runs capture-grounded ISOLATION proofs (byte-clean differentials against a
shared baseline) that back the [CONFIRMED_LIVE] tags on the record fields: the Select
Type enum + its r3:r4 params, the colour_count -> palette length law, the brightness
scope/speed/retention band, the r13 direction/distribution byte, both movement packed
bytes and the priority byte.

Fixtures are embedded as inline hex extracted from these captures (split at A3 idx
0xff): workshop-baseline-christmas, the 20260715134003 select-type matrix,
20260715140050 colour-family, 20260715141908 brightness-moving-effects,
workshop-priority, workshop-movement-dir, workshop-overall-dir and 20260716165800 r13.
"""

import io
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from kaitaistruct import KaitaiStream  # noqa: E402
from workshop_body import WorkshopBody  # noqa: E402

# name -> (hex, expected_layer_count). Verified byte-for-byte from the captures.
FIXTURES = {
    # 5-layer Christmas draft: the r1 tiling proof (20 22 24 26 28), one colour each.
    "christmas_5layer": (
        "010902051a200100020001ff000080141401801401ff0005000080000080001a220100020001ff0000"
        "8014140180140100ff04000080000080001a240100020001ff000080141401801401ff00010000800000"
        "80001a260100020001ff00008014140180140100ff00000080000080001a280100010001ff0000801414"
        "01801401ff0000000080000080000000000000000000000000000000",
        5,
    ),
    # canonical one-layer Select IC Continuously, ordered red+blue (doc example); baseline.
    "two_colour_continuously": ("010202011d0001000f1001ff000080141401801402ff00000000ff00008000008000", 1),
    # select-type matrix: same body, only r2:r4 change (Segment / Randomly / Customize).
    "matrix_segment": ("010202011d000000071001ff000080141401801402ff00000000ff00008000008000", 1),
    "matrix_randomly": ("010202011d00020f011001ff000080141401801402ff00000000ff00008000008000", 1),
    "matrix_customize": ("010202011d000301001001ff000080141401801402ff00000000ff00008000008000", 1),
    # three colours: colour_count 03, record_len grows to 0x20, palette red+blue+green.
    "three_colour": (
        "01030201200001000f1001ff000080141401801403ff00000000ff00ff00000080000080000000000000000000000000000000",
        1,
    ),
    # brightness differential: r7:r8 c639, r10 ff, r11:r12 c830, r14 7f (vs the baseline).
    "brightness_scope": ("010202011d0001000f1001c63900ffc830017f1402ff00000000ff00008000008000", 1),
    # two-layer bodies that share rec0 except the movement/priority tail:
    #   priority: sel packed 00, ovr packed 10, priority 02
    "priority_2layer": (
        "010402021d400000021201ff000080141483b26d0200ff00ff00000001ef1001b7021a0001000f1001"
        "ff00008014140180140106ff000000800000800000000000000000",
        2,
    ),
    #   selected-area movement direction: sel packed 16 (enable|enter-exit|dir2), priority 01
    "selected_movement_dir": (
        "010402021d400000021201ff000080141483b26d0200ff00ff00001601ef1001b7011a0001000f1001"
        "ff00008014140180140106ff000000800000800000000000000000",
        2,
    ),
    #   overall movement direction: ovr packed 12 (enable|dir2), priority 00
    "overall_movement_dir": (
        "010402021d400000021201ff000080141483b26d0200ff00ff00000001ef1201b7001a0001000f1001"
        "ff00008014140180140106ff000000800000800000000000000000",
        2,
    ),
    # r13 differential: Christmas with rec0 direction/distribution 0x80 (Unified + Backward).
    "r13_direction": (
        "010902051a200100020001ff000080141480801401ff0005000080000080001a220100020001ff0000"
        "8014140180140100ff04000080000080001a240100020001ff000080141401801401ff00010000800000"
        "80001a260100020001ff00008014140180140100ff00000080000080001a280100010001ff0000801414"
        "01801401ff0000000080000080000000000000000000000000000000",
        5,
    ),
}


def parse(hx: str):
    raw = bytes.fromhex(hx)
    return raw, WorkshopBody(KaitaiStream(io.BytesIO(raw)))


def check_body(name: str, hx: str, exp_layers: int):
    """The five required structural checks + framing/record byte-exactness."""
    raw, k = parse(hx)
    checks = []

    # (2) whole body consumed
    checks.append(("consumed", k._io.is_eof()))
    # (3) padding all zero
    checks.append(("pad_all_zero", set(k.padding) <= {0}))
    # (4a) layer_count matches the wire byte and the parsed record list
    checks.append(("layer_count", k.layer_count == raw[3] == len(k.layers) == exp_layers))
    # framing: body is a whole number of 17-byte A3 chunks, linecount == len/17
    checks.append(("chunk_boundary", len(raw) % 17 == 0 and k.header.linecount == len(raw) // 17))

    # (4b) each record_len matches the bytes it spans; record_len == 23 + 3*colour_count
    rec_span = 4  # marker + linecount + a3_type + layer_count
    for i, rec in enumerate(k.layers):
        m = rec.body.colour_count
        checks.append((f"rec{i}_len==23+3M", rec.record_len == 23 + 3 * m))
        checks.append((f"rec{i}_no_excess", len(rec.body.excess) == 0))
        rec_span += 1 + rec.record_len
    # (4c) record spans + padding == body length
    checks.append(("span_sum==len", rec_span + len(k.padding) == len(raw)))

    # (5) Christmas tiling proof
    if name == "christmas_5layer":
        r1 = [rec.body.applied_area for rec in k.layers]
        checks.append(("r1_tiling==2022242628", r1 == [0x20, 0x22, 0x24, 0x26, 0x28]))

    ok = all(v for _, v in checks)
    bad = ",".join(n for n, v in checks if not v)
    lens = [rec.record_len for rec in k.layers]
    print(
        f"{'PASS' if ok else 'FAIL':4s} {name:24s} len={len(raw):3d} lc={k.layer_count} "
        f"linecount={k.header.linecount} rec_lens={lens} pad={len(k.padding)}B" + (f"  <FAILED: {bad}>" if bad else "")
    )
    return ok, (raw, k)


def diff_offsets(a: bytes, b: bytes) -> set[int]:
    return {i for i in range(min(len(a), len(b))) if a[i] != b[i]} | set(
        range(min(len(a), len(b)), max(len(a), len(b)))
    )


def isolation_proofs(parsed: dict) -> int:
    """Byte-clean differentials + decoded-value assertions backing CONFIRMED_LIVE tags."""
    fails = 0
    base_raw, _ = parsed["two_colour_continuously"]

    def emit(label: str, ok: bool, detail: str = ""):
        nonlocal fails
        fails += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'} {label:34s} {detail}")

    # Select Type enum + r3:r4 params, isolated to record offsets r2,r3,r4 (body offsets 6,7,8).
    select_offsets = {6, 7, 8}
    expect = {
        "matrix_segment": (WorkshopBody.SelectType.segment, 0x00, 0x07),
        "two_colour_continuously": (WorkshopBody.SelectType.select_ic_continuously, 0x00, 0x0F),
        "matrix_randomly": (WorkshopBody.SelectType.select_ic_randomly, 0x0F, 0x01),
        "matrix_customize": (WorkshopBody.SelectType.customize_segment, 0x01, 0x00),
    }
    for nm, (st, p1, p2) in expect.items():
        raw, k = parsed[nm]
        r0 = k.layers[0].body
        good = r0.select_type == st and r0.select_param_1 == p1 and r0.select_param_2 == p2
        confined = diff_offsets(raw, base_raw) <= select_offsets
        emit(
            f"select_type {nm}",
            good and confined,
            f"{r0.select_type.name}={int(r0.select_type.value)} params=({p1:#04x},{p2:#04x}) diff{sorted(diff_offsets(raw, base_raw))}",
        )

    # colour_count -> palette length law across M = 1, 2, 3.
    for nm, m in (("christmas_5layer", 1), ("two_colour_continuously", 2), ("three_colour", 3)):
        _, k = parsed[nm]
        r0 = k.layers[0].body
        emit(
            f"colour_count law M={m}",
            r0.colour_count == m and len(r0.palette) == m and k.layers[0].record_len == 23 + 3 * m,
            f"r16={r0.colour_count} palette={[(c.r, c.g, c.b) for c in r0.palette]} rec_len={k.layers[0].record_len}",
        )

    # Brightness band r7:r8/r10/r11:r12 (+ r14), isolated to body offsets {11,12,14,15,16,18}.
    braw, bk = parsed["brightness_scope"]
    br = bk.layers[0].body
    bright_offsets = {11, 12, 14, 15, 16, 18}
    emit(
        "brightness values",
        (
            br.brightness_scope_start,
            br.brightness_scope_end,
            br.brightness_speed,
            br.brightest_retention,
            br.darkest_retention,
        )
        == (0xC6, 0x39, 0xFF, 0xC8, 0x30),
        f"scope=({br.brightness_scope_start:#04x},{br.brightness_scope_end:#04x}) speed={br.brightness_speed:#04x} "
        f"retention=({br.brightest_retention:#04x},{br.darkest_retention:#04x})",
    )
    emit(
        "brightness isolated to r7:r8/r10-12/r14",
        diff_offsets(braw, base_raw) <= bright_offsets,
        f"diff{sorted(diff_offsets(braw, base_raw))}",
    )

    # r13 direction/distribution: r13_direction differs from Christmas at exactly rec0 r13 (offset 17).
    craw, ck = parsed["christmas_5layer"]
    rraw, rk = parsed["r13_direction"]
    c13 = ck.layers[0].body.direction_distribution
    r13 = rk.layers[0].body.direction_distribution
    emit(
        "r13 one-byte differential",
        diff_offsets(rraw, craw) == {17} and c13 == 0x01 and r13 == 0x80,
        f"christmas=0x{c13:02x}(back={ck.layers[0].body.direction_is_backward}) "
        f"r13cap=0x{r13:02x}(back={rk.layers[0].body.direction_is_backward}) diff{sorted(diff_offsets(rraw, craw))}",
    )
    # and the segment+gradient value 0x83 round-trips (backward | based-on-segment | gradient bit).
    p2r = parsed["priority_2layer"][1].layers[0].body
    emit(
        "r13 segment+gradient 0x83",
        p2r.direction_distribution == 0x83
        and p2r.direction_is_backward
        and (p2r.direction_distribution & 0x03) == 0x03,
        f"r13=0x{p2r.direction_distribution:02x}",
    )

    # Movement packed bytes + priority: three 2-layer bodies differ only in the tail
    # offsets {27 (sel packed r23), 30 (ovr packed r26), 33 (priority r29)}.
    praw, pk = parsed["priority_2layer"]
    sraw, sk = parsed["selected_movement_dir"]
    oraw, ok_ = parsed["overall_movement_dir"]
    tail_offsets = {27, 30, 33}
    emit(
        "movement/priority tail isolated",
        diff_offsets(sraw, praw) <= tail_offsets and diff_offsets(oraw, praw) <= tail_offsets,
        f"sel^prio diff{sorted(diff_offsets(sraw, praw))} ovr^prio diff{sorted(diff_offsets(oraw, praw))}",
    )
    sm = sk.layers[0].body.selected_area_movement
    emit(
        "selected movement packed 0x16",
        sm.packed == 0x16 and sm.enabled and sm.enter_exit_effect and sm.direction == 2,
        f"packed=0x{sm.packed:02x} enabled={sm.enabled} enter_exit={sm.enter_exit_effect} dir={sm.direction}",
    )
    om = ok_.layers[0].body.overall_movement
    emit(
        "overall movement packed 0x12",
        om.packed == 0x12 and om.enabled and not om.enter_exit_effect and om.direction == 2,
        f"packed=0x{om.packed:02x} enabled={om.enabled} enter_exit={om.enter_exit_effect} dir={om.direction}",
    )
    prios = {
        nm: parsed[nm][1].layers[0].body.priority
        for nm in ("priority_2layer", "selected_movement_dir", "overall_movement_dir")
    }
    emit(
        "priority levels 2/1/0",
        prios == {"priority_2layer": 2, "selected_movement_dir": 1, "overall_movement_dir": 0},
        f"{prios}",
    )

    return fails


def main() -> int:
    print("== structural round-trip (parse, EOF, padding, spans, tiling) ==")
    fails = 0
    parsed = {}
    for name, (hx, exp_layers) in FIXTURES.items():
        ok, pk = check_body(name, hx, exp_layers)
        parsed[name] = pk
        fails += 0 if ok else 1

    print("\n== isolation proofs (capture-grounded differentials backing CONFIRMED_LIVE) ==")
    fails += isolation_proofs(parsed)

    print(f"\n{'ALL PASS' if not fails else f'{fails} FAILED'} ({len(FIXTURES)} bodies round-tripped byte-exact)")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
