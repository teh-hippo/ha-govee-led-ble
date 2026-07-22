#!/usr/bin/env python3
"""Extract capture-verified fixtures for the Kaitai pilot from existing pcaps.

Pulls real wire bytes (ground truth) so the .ksy specs are re-verified against
captures, not transcribed from the docs. Emits JSON:
  - aa05: full aa 05 reply frames + the shipped parse_color_mode_response decode
  - a3_bodies: reassembled 0xA3 multi-frame bodies + the following activation frame
No app-side/overlay data; wire bytes only.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
TOOLS_BLE = HERE.parent.parent
sys.path.insert(0, str(TOOLS_BLE))
REPO = TOOLS_BLE.parent.parent
sys.path.insert(0, str(REPO))

import decode_govee as dg  # noqa: E402

from custom_components.ha_govee_led_ble import protocol as proto  # noqa: E402

CAPS = Path("/mnt/z/libimobiledevice/captures")


def reassemble_groups(records):
    """Yield (body_bytes, activation_frame_or_None) for each 0xA3 frame run."""
    groups = []
    chunks: list[bytes] = []
    for r in records:
        v = r.value
        if len(v) != 20:
            continue
        if v[0] == 0xA3:
            chunks.append(bytes(v[2:19]))  # 17-byte payload chunk
        else:
            if chunks:
                groups.append([b"".join(chunks), None])
                chunks = []
            # activation immediately after a body: 33 05 04 <code_le> <type>
            if groups and groups[-1][1] is None and v[0] == 0x33 and v[1] == 0x05 and v[2] == 0x04:
                groups[-1][1] = bytes(v)
    if chunks:
        groups.append([b"".join(chunks), None])
    return groups


def extract(pcap: Path):
    data = pcap.read_bytes()
    trace = dg.parse_capture(data, allow_truncated=True)
    aa05 = []
    for r in trace.att:
        v = r.value
        if len(v) == 20 and v[0] == 0xAA and v[1] == 0x05 and r.direction == "RX":
            split = proto.split_status_frame(v)
            payload = split[1] if split else b""
            try:
                parsed = proto.parse_color_mode_response(payload)
                decode = {k: getattr(parsed, k) for k in vars(parsed)} if hasattr(parsed, "__dict__") else str(parsed)
            except Exception as e:  # noqa: BLE001
                decode = f"error: {e}"
            aa05.append({"frame": v.hex(), "payload": payload.hex(), "decode": str(decode)})
    bodies = []
    for body, act in reassemble_groups(list(trace.att)):
        bodies.append(
            {
                "len": len(body),
                "body": body.hex(),
                "head": body[:3].hex() if len(body) >= 3 else body.hex(),
                "activation": act.hex() if act else None,
            }
        )
    return {"pcap": pcap.name, "aa05": aa05, "a3_bodies": bodies}


def main() -> int:
    targets = sys.argv[1:] or [
        "20260716151500-h617a-scene-speed.pcap",
        "20260716120000-h617a-music-walkthrough.pcap",
        "20260716140100-h617a-sketch.pcap",
    ]
    out = {}
    for name in targets:
        p = CAPS / name
        if not p.exists():
            print(f"MISSING: {name}", file=sys.stderr)
            continue
        out[name] = extract(p)
        r = out[name]
        print(f"== {name}: aa05={len(r['aa05'])} a3_bodies={len(r['a3_bodies'])}")
        for b in r["a3_bodies"][:6]:
            print(f"   body len={b['len']:3d} head={b['head']} act={b['activation']}")
        for a in r["aa05"][:4]:
            print(f"   aa05 {a['frame']}  -> {a['decode']}")
    Path(HERE.parent / "fixtures.json").write_text(json.dumps(out, indent=2))
    print(f"\nwrote {HERE.parent / 'fixtures.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
