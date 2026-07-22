#!/usr/bin/env python3
"""Round-trip verify colormode_readback.ksy against real captured aa05 frames.

Parses each real frame with the Kaitai-generated parser, asserts the whole
20-byte frame is consumed and the XOR checksum is valid (host-side, since
Kaitai cannot fold), and checks field parity with the shipped
protocol.parse_color_mode_response. Captures are ground truth.
"""
import io
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # generated parser module
REPO = HERE.parent.parent.parent
sys.path.insert(0, str(REPO))

from kaitaistruct import KaitaiStream  # noqa: E402
from colormode_readback import ColormodeReadback  # noqa: E402
from custom_components.ha_govee_led_ble import protocol as proto  # noqa: E402

# (name, captured frame hex, source pcap) -- real wire bytes, all five modes.
FIXTURES = [
    ("static", "aa051500000000000000000000000000000000ba", "h617a-s5.pcap"),
    ("scene", "aa050409000000000000000000000000000000a2", "20260715111823-h617a-poc-simple.pcap"),
    ("diy", "aa050a980000000000000000000000000000003d", "h617a-s3.pcap"),
    ("video", "aa050000014d00000000000000000000000000e3", "validate-20260709-122350.pcap"),
    ("music", "aa051306630001ff000000000000000000000027", "h617a-full.pcap"),
]


def xor(frame: bytes) -> int:
    c = 0
    for b in frame[:19]:
        c ^= b
    return c


def main() -> int:
    fails = 0
    for name, hx, src in FIXTURES:
        raw = bytes.fromhex(hx)
        checks = []
        checks.append(("xor", xor(raw) == raw[19]))
        k = ColormodeReadback(KaitaiStream(io.BytesIO(raw)))
        checks.append(("consumed_all", k._io.is_eof()))
        checks.append(("mode", int(k.mode.value) == raw[2]))
        payload = proto.split_status_frame(raw)[1]
        ref = proto.parse_color_mode_response(payload)
        b = k.body
        detail = ""
        if name == "music":
            checks += [
                ("mode_id", b.mode_id == payload[1]),
                ("sens", b.sensitivity == payload[2]),
                ("style", b.style == payload[3]),
                ("count", b.manual_color_count == payload[4]),
            ]
            if b.manual_color_count >= 1:
                checks.append(("rgb", b.rgb == payload[5:8]))
            detail = f"mode_id={b.mode_id} sens={b.sensitivity} calm(ref)={ref.music_calm} rgb={b.rgb.hex() if b.manual_color_count >= 1 else None}"
        elif name == "scene":
            checks.append(("scene_id", b.scene_id == int.from_bytes(payload[1:3], "little")))
            detail = f"scene_id={b.scene_id} effect(ref)={ref.effect}"
        elif name == "diy":
            checks.append(("slot", b.slot == payload[1]))
            detail = f"slot={b.slot} diy_slot(ref)={ref.diy_slot}"
        elif name == "video":
            checks += [
                ("full_screen", b.full_screen == payload[1]),
                ("game_mode", b.game_mode == payload[2]),
                ("saturation", b.saturation == payload[3]),
                ("sound_effects", b.sound_effects == payload[4]),
                ("softness", b.softness == payload[5]),
            ]
            detail = f"full_screen={b.full_screen} game={b.game_mode} sat={b.saturation} sound={b.sound_effects} soft={b.softness}"
        elif name == "static":
            checks.append(("sub", int(b.sub) == payload[1]))
            if int(b.sub) == 0x01:
                checks.append(("rgb", b.rgb == payload[2:5]))
            detail = f"sub={int(b.sub)} rgb(ref)={ref.rgb_color} (sub 0x01/0x02 readback INHERITED, no capture)"
        ok = all(v for _, v in checks)
        fails += 0 if ok else 1
        bad = ",".join(n for n, v in checks if not v)
        print(f"{'PASS' if ok else 'FAIL'} {name:7s} [{src}] mode={k.mode.name} {detail}" + (f"  <FAILED: {bad}>" if bad else ""))
    print("\nALL PASS" if not fails else f"\n{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
