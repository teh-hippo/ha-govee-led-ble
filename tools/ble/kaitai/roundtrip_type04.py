#!/usr/bin/env python3
"""Round-trip verify diy_type04.ksy against real captured Flat DIY + Combo DIY
TYPE 0x04 bodies (reassembled 0xA3 multi-frame bodies).

Captures are ground truth. Fixtures are extracted inline from the capture set
(split A3 runs at idx=0xFF, keep bodies whose byte[0]==0x01 and byte[2]==0x04),
then embedded here as raw hex with provenance so the harness needs no pcap access.

Per body the harness asserts:
  1. the generated DiyType04 parses it and consumes the whole body (is_eof);
  2. the trailing padding is all zero;
  3. marker/type/family plus every decoded field (flat: variant/speed/plen/palette;
     combo: variant/speed/plen/palette/seqlen/pairs) match the raw wire bytes at
     their offsets, and the PLEN = 3 x colours / SEQLEN = 2 x effects relations hold;
  4. a semantic body rebuilt from the parsed fields (mirroring build_flat_diy /
     build_combo) equals the raw bytes from byte[3] up to the zero padding; and
  5. feeding the parsed fields back through the shipped protocol.build_flat_diy /
     protocol.build_combo encoders and reassembling the 0xA3 frames reproduces the
     original body byte-exact (linecount + palette + sequence + padding).

Prints PASS/FAIL per body; exits non-zero on any failure.
"""
import io
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPO = HERE.parent.parent.parent
sys.path.insert(0, str(REPO))

from kaitaistruct import KaitaiStream  # noqa: E402
from diy_type04 import DiyType04  # noqa: E402
from custom_components.ha_govee_led_ble import protocol as proto  # noqa: E402
from custom_components.ha_govee_led_ble.custom_effects import ComboContent, FlatContent  # noqa: E402

# (label, kind, source pcap, reassembled body hex). Extracted from the capture set;
# combo bodies exercise seqlen 0x02/0x04/0x06/0x08, flat bodies exercise plen
# 0x03/0x09/0x0c/0x15 across families 0x00/0x01/0x03/0x08.
FIXTURES = [
    # --- Combo DIY (FAMILY == 0xFF) -- [CONFIRMED_LIVE], combo captures exist ---
    ("combo seqlen=0x02 (1 effect)", "combo", "combo-3.pcap",
     "010204ff003315ff0000ff7f00ffff0000ff000000ff00ffff8b00ff020000000000"),
    ("combo seqlen=0x04 (2 effects)", "combo", "combo-3.pcap",
     "010204ff003315ff0000ff7f00ffff0000ff000000ff00ffff8b00ff040000010000"),
    ("combo seqlen=0x06 (3 effects)", "combo", "combo-3.pcap",
     "010304ff003315ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0600000100030300000000000000000000000000000000"),
    ("combo seqlen=0x08 (4 effects)", "combo", "combo-4.pcap",
     "010304ff003315ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0800000100030308090000000000000000000000000000"),
    ("combo seqlen=0x04 pairs (0,0)(3,3)", "combo", "diy-combo.pcap",
     "010204ff003315ff0000ff7f00ffff0000ff000000ff00ffff8b00ff040000030300"),
    # --- Flat DIY (FAMILY != 0xFF) -- [CONFIRMED_LIVE], flat captures exist ---
    ("flat plen=0x15 (7 colours) fam=0x03", "flat", "diy-marquee.pcap",
     "01020403033215ff0000ff7d00ffff0000ff000000ff00ffff8b00ff000000000000"),
    ("flat plen=0x0c (4 colours) fam=0x00", "flat", "colorlimit-fade.pcap",
     "0102040000640cff0000ff7d00ffff0000ff00000000000000000000000000000000"),
    ("flat plen=0x09 (3 colours) fam=0x08", "flat", "diy-chasing.pcap",
     "01020408096409ff0000ff7d00ffff00000000000000000000000000000000000000"),
    ("flat plen=0x03 (1 colour) fam=0x01", "flat", "h617a-diy-jumping1-a.pcap",
     "010204010064038b00ff000000000000000000000000000000000000000000000000"),
]


def reassemble_a3(frames: list[bytes]) -> bytes:
    """Concatenate the 17-byte payload of each 0xA3 frame, closing a run at idx 0xFF.

    Mirrors the capture-side reassembly used to extract the fixtures, so a body
    re-encoded by build_a3_multi reassembles back to the same wire bytes.
    """
    groups, chunks = [], []
    for f in frames:
        if len(f) != 20 or f[0] != 0xA3:
            continue
        chunks.append(bytes(f[2:19]))
        if f[1] == 0xFF:
            groups.append(b"".join(chunks))
            chunks = []
    if chunks:
        groups.append(b"".join(chunks))
    return groups[0] if groups else b""


def palette_bytes(body) -> bytes:
    return b"".join(bytes([c.r, c.g, c.b]) for c in body.palette.colours)


def check(label: str, kind: str, pcap: str, hx: str) -> tuple[bool, str]:
    raw = bytes.fromhex(hx)
    k = DiyType04(KaitaiStream(io.BytesIO(raw)))
    body = k.body
    checks: list[tuple[str, bool]] = []

    # 1. whole body consumed
    checks.append(("consumed", k._io.is_eof()))
    # 2. padding all zero
    checks.append(("pad_zero", set(body.padding) <= {0}))
    # 3. shared header fields vs raw
    checks += [
        ("marker", k.header.marker == b"\x01" and raw[0] == 0x01),
        ("a3_type", k.a3_type == raw[2] == 0x04),
        ("family", k.family == raw[3]),
    ]

    pal = palette_bytes(body)
    if kind == "combo":
        checks += [
            ("combo_family", k.family == 0xFF),
            ("variant", body.variant == raw[4]),
            ("speed", body.speed == raw[5]),
            ("plen", body.plen == raw[6]),
            ("palette", pal == raw[7:7 + body.plen]),
            ("plen=3xcolours", body.plen == 3 * len(body.palette.colours)),
            ("seqlen", body.seqlen == raw[7 + body.plen]),
            ("seqlen=2xpairs", body.seqlen == 2 * len(body.pairs)),
        ]
        seq_off = 7 + body.plen + 1
        seq_raw = raw[seq_off:seq_off + body.seqlen]
        seq_parsed = b"".join(bytes([p.family, p.variant]) for p in body.pairs)
        checks.append(("pairs", seq_parsed == seq_raw))
        # 4. semantic body rebuilt from parsed fields, mirroring build_combo
        rebuilt = bytes([0xFF, body.variant, body.speed, body.plen]) + pal + bytes([body.seqlen]) + seq_parsed
        # 5. feed parsed fields back through the shipped encoder, reassemble, compare
        content = ComboContent(
            variant=body.variant,
            speed=body.speed,
            palette=tuple((c.r, c.g, c.b) for c in body.palette.colours),
            effects=tuple((p.family, p.variant) for p in body.pairs),
        )
        encoded = reassemble_a3(proto.build_combo(content))
        detail = (f"var={body.variant} speed={body.speed} plen={body.plen} "
                  f"colours={len(body.palette.colours)} seqlen={body.seqlen} "
                  f"pairs={[(p.family, p.variant) for p in body.pairs]} pad={len(body.padding)}B")
    else:  # flat
        checks += [
            ("flat_family", k.family != 0xFF),
            ("variant", body.variant == raw[4]),
            ("speed", body.speed == raw[5]),
            ("plen", body.plen == raw[6]),
            ("palette", pal == raw[7:7 + body.plen]),
            ("plen=3xcolours", body.plen == 3 * len(body.palette.colours)),
        ]
        # 4. semantic body rebuilt from parsed fields, mirroring build_flat_diy
        rebuilt = bytes([k.family, body.variant, body.speed, body.plen]) + pal
        # 5. feed parsed fields back through the shipped encoder, reassemble, compare
        content = FlatContent(
            family=k.family,
            variant=body.variant,
            speed=body.speed,
            palette=tuple((c.r, c.g, c.b) for c in body.palette.colours),
        )
        encoded = reassemble_a3(proto.build_flat_diy(content))
        detail = (f"fam={k.family} var={body.variant} speed={body.speed} plen={body.plen} "
                  f"colours={len(body.palette.colours)} pad={len(body.padding)}B")

    # 4. equality up to padding (semantic reconstruction lands at byte[3])
    checks.append(("rebuild_upto_pad", rebuilt == raw[3:3 + len(rebuilt)]))
    checks.append(("tail_all_zero", set(raw[3 + len(rebuilt):]) <= {0}))
    # 5. shipped-encoder round-trip is byte-exact (linecount + payload + padding)
    checks.append(("encoder_byte_exact", encoded == raw))

    ok = all(v for _, v in checks)
    bad = ",".join(n for n, v in checks if not v)
    line = f"{'PASS' if ok else 'FAIL'} {label:38s} [{pcap}] {detail}"
    if bad:
        line += f"  <FAILED: {bad}>"
    return ok, line


def main() -> int:
    fails = 0
    for label, kind, pcap, hx in FIXTURES:
        ok, line = check(label, kind, pcap, hx)
        fails += 0 if ok else 1
        print(line)
    print("\nALL PASS" if not fails else f"\n{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
