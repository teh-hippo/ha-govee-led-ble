#!/usr/bin/env python3
"""Round-trip verify status_reply.ksy against real captured aa status replies.

Full-frame consumption + host-side XOR + field parity with the shipped
protocol.py decoders. Captures are ground truth.
"""
import io
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPO = HERE.parent.parent.parent
sys.path.insert(0, str(REPO))

from kaitaistruct import KaitaiStream  # noqa: E402
from status_reply import StatusReply  # noqa: E402
from custom_components.ha_govee_led_ble import protocol as proto  # noqa: E402

FIXTURES = [
    ("power", "aa010000000000000000000000000000000000ab"),
    ("fw", "aa06332e30322e3234000000000000000000009b"),
    ("hw", "aa0703332e30312e30310000000000000000009d"),
    ("segments", "aaa50164ff880d64ff880d64ff880d0000000010"),
    ("timer", "aa23ff01071ec001091080010000800100008036"),
]


def xor(frame: bytes) -> int:
    c = 0
    for b in frame[:19]:
        c ^= b
    return c


def main() -> int:
    fails = 0
    for name, hx in FIXTURES:
        raw = bytes.fromhex(hx)
        checks = [("xor", xor(raw) == raw[19])]
        k = StatusReply(KaitaiStream(io.BytesIO(raw)))
        checks += [("consumed", k._io.is_eof()), ("domain", int(k.domain.value) == raw[1])]
        payload = proto.split_status_frame(raw)[1]
        b = k.body
        detail = ""
        if name == "power":
            checks.append(("is_on", b.is_on == raw[2]))
            detail = f"is_on={b.is_on}"
        elif name == "fw":
            checks.append(("text", b.text == proto.parse_fw_version(payload)))
            detail = f"fw={b.text!r}"
        elif name == "hw":
            checks.append(("text", b.text == proto.parse_hw_version(payload)))
            detail = f"hw={b.text!r}"
        elif name == "segments":
            segs = [(s.brightness, s.r, s.g, s.b) for s in b.segments]
            exp = [tuple(raw[3 + i * 4 : 3 + i * 4 + 4]) for i in range(3)]
            checks += [("group", b.group == raw[2]), ("segments", segs == exp)]
            detail = f"group={b.group} segs={segs}"
        elif name == "timer":
            detail = "ff-marker + opaque 4-slot region (INHERITED)"
        ok = all(v for _, v in checks)
        fails += 0 if ok else 1
        bad = ",".join(n for n, v in checks if not v)
        print(f"{'PASS' if ok else 'FAIL'} {name:9s} domain={k.domain.name} {detail}" + (f"  <FAILED: {bad}>" if bad else ""))
    print("\nALL PASS" if not fails else f"\n{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
