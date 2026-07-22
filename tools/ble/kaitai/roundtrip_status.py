#!/usr/bin/env python3
"""Round-trip verify status_reply.ksy against real captured aa status replies.

Full-frame consumption + host-side XOR + field parity with the shipped
protocol.py decoders, across every aa domain including colour-mode (0x05).
Captures are ground truth.
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

# (name, captured frame hex) -- real wire bytes, one per aa domain plus the five
# colour-mode selectors.
FIXTURES = [
    ("power", "aa010000000000000000000000000000000000ab"),
    ("fw", "aa06332e30322e3234000000000000000000009b"),
    ("hw", "aa0703332e30312e30310000000000000000009d"),
    ("segments", "aaa50164ff880d64ff880d64ff880d0000000010"),
    ("timer", "aa23ff01071ec001091080010000800100008036"),
    ("cm_static", "aa051500000000000000000000000000000000ba"),
    ("cm_scene", "aa050409000000000000000000000000000000a2"),
    ("cm_diy", "aa050a980000000000000000000000000000003d"),
    ("cm_video", "aa050000014d00000000000000000000000000e3"),
    ("cm_music", "aa051306630001ff000000000000000000000027"),
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
            segs = [(s.brightness, s.colour.r, s.colour.g, s.colour.b) for s in b.segments]
            exp = [tuple(raw[3 + i * 4 : 3 + i * 4 + 4]) for i in range(3)]
            checks += [("group", b.group == raw[2]), ("segments", segs == exp)]
            detail = f"group={b.group} segs={segs}"
        elif name == "timer":
            detail = "ff-marker + opaque 4-slot region (INHERITED)"
        elif name.startswith("cm_"):
            ref = proto.parse_color_mode_response(payload)
            m = b.mode_body
            checks.append(("mode", int(b.mode.value) == payload[0]))
            if name == "cm_static":
                checks.append(("sub", int(m.sub) == payload[1]))
                detail = f"static sub={int(m.sub)} rgb(ref)={ref.rgb_color} (sub 0x01/0x02 INHERITED)"
            elif name == "cm_scene":
                checks.append(("scene_id", m.scene_id == int.from_bytes(payload[1:3], "little")))
                detail = f"scene scene_id={m.scene_id} effect(ref)={ref.effect}"
            elif name == "cm_diy":
                checks.append(("slot", m.slot == payload[1]))
                detail = f"diy slot={m.slot} diy_slot(ref)={ref.diy_slot}"
            elif name == "cm_video":
                checks += [
                    ("full_screen", m.full_screen == payload[1]),
                    ("game_mode", m.game_mode == payload[2]),
                    ("saturation", m.saturation == payload[3]),
                    ("sound_effects", m.sound_effects == payload[4]),
                    ("softness", m.softness == payload[5]),
                ]
                detail = f"video sat={m.saturation} sound={m.sound_effects} soft={m.softness}"
            elif name == "cm_music":
                checks += [
                    ("mode_id", getattr(m.mode_id, "value", m.mode_id) == payload[1]),
                    ("sens", m.sensitivity == payload[2]),
                    ("style", getattr(m.style, "value", m.style) == payload[3]),
                    ("count", m.manual_color_count == payload[4]),
                ]
                if m.manual_color_count >= 1:
                    checks.append(("rgb", bytes([m.rgb.r, m.rgb.g, m.rgb.b]) == payload[5:8]))
                detail = f"music mode_id={getattr(m.mode_id, 'name', m.mode_id)} sens={m.sensitivity} calm(ref)={ref.music_calm}"
        ok = all(v for _, v in checks)
        fails += 0 if ok else 1
        bad = ",".join(n for n, v in checks if not v)
        print(
            f"{'PASS' if ok else 'FAIL'} {name:10s} domain={k.domain.name} {detail}"
            + (f"  <FAILED: {bad}>" if bad else "")
        )
    print("\nALL PASS" if not fails else f"\n{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
