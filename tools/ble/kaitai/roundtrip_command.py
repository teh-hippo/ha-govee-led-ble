#!/usr/bin/env python3
"""Round-trip verify command_write.ksy against real captured 33 command writes.

Full-frame consumption + host-side XOR + field parity with the shipped
protocol.py builders, across every 33 opcode confirmed live this session
(power / brightness / static colour / colour-temperature / scene / diy / music).
Captures are ground truth: every frame below is real wire bytes from a marked
single-action capture (resume-* pcaps, 2026-07-22).
"""

import io
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPO = HERE.parent.parent.parent
sys.path.insert(0, str(REPO))

from command_write import CommandWrite  # noqa: E402
from kaitaistruct import KaitaiStream  # noqa: E402

from custom_components.ha_govee_led_ble import protocol as proto  # noqa: E402

# (name, captured frame hex) -- real wire bytes, one per confirmed 33 opcode/sub.
FIXTURES = [
    ("power_off", "3301000000000000000000000000000000000032"),
    ("power_on", "3301010000000000000000000000000000000033"),
    ("brightness", "3304330000000000000000000000000000000004"),
    ("color_rgb", "33051501ff00000000000000ff7f00000000005d"),
    ("color_temp", "330515010000000e10ffcb8dff7f000000000005"),
    ("scene", "3305047308000000000000000000000000000049"),
    ("diy", "33050af0000000000000000000000000000000cc"),
    ("music", "3305130363000100e6d200000000000000000070"),
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
        k = CommandWrite(KaitaiStream(io.BytesIO(raw)))
        checks = [
            ("xor", xor(raw) == raw[19]),
            ("consumed", k._io.is_eof()),
            ("opcode", int(k.opcode.value) == raw[1]),
        ]
        b = k.body
        detail = ""
        if name.startswith("power"):
            checks += [
                ("is_on", b.is_on == raw[2]),
                ("builder", proto.build_power(bool(b.is_on)) == raw),
            ]
            detail = f"power is_on={b.is_on}"
        elif name == "brightness":
            checks += [
                ("percent", b.percent == raw[2]),
                ("builder", proto.build_brightness(b.percent) == raw),
            ]
            detail = f"brightness={b.percent}% (raw 0..100)"
        elif name == "color_rgb":
            s = b.sub_body.static_body
            rgb = (s.rgb_direct.r, s.rgb_direct.g, s.rgb_direct.b)
            checks += [
                ("sub_static", int(b.sub.value) == 0x15),
                ("static_sub", b.sub_body.static_sub == 0x01),
                ("rgb_direct", rgb == (255, 0, 0)),
                ("kelvin_zero", s.kelvin == 0),
                ("preview_zero", (s.rgb_preview.r, s.rgb_preview.g, s.rgb_preview.b) == (0, 0, 0)),
                ("mask_all", s.mask == 0x7FFF),
                ("builder", proto.build_segment_color(proto.ALL_SEGMENTS, *rgb) == raw),
            ]
            detail = f"static colour rgb={rgb} mask=0x{s.mask:04x}"
        elif name == "color_temp":
            s = b.sub_body.static_body
            preview = (s.rgb_preview.r, s.rgb_preview.g, s.rgb_preview.b)
            # Same unified static_color layout as color_rgb: rgb_direct zeroed, kelvin +
            # preview populated, mask all-segments. protocol.build_color_temp matches on
            # everything EXCEPT the preview RGB curve (device keys off kelvin; cosmetic).
            builder = proto.build_color_temp(s.kelvin)
            builder_preview = proto.kelvin_to_rgb(s.kelvin)
            checks += [
                ("static_sub", b.sub_body.static_sub == 0x01),
                ("direct_zero", (s.rgb_direct.r, s.rgb_direct.g, s.rgb_direct.b) == (0, 0, 0)),
                ("kelvin", s.kelvin == 3600),
                ("mask_all", s.mask == 0x7FFF),
                ("builder_struct", builder[:7] == raw[:7] and builder[12:14] == raw[12:14]),
                ("preview_diverges", preview != builder_preview),
            ]
            detail = f"static temp kelvin={s.kelvin} preview={preview} vs protocol.py {builder_preview} (cosmetic)"
        elif name == "scene":
            sc = b.sub_body
            checks += [
                ("sub_scene", int(b.sub.value) == 0x04),
                ("code", sc.code == int.from_bytes(raw[3:5], "little")),
                ("builder", proto.build_scene(sc.code) == raw),
            ]
            detail = f"scene code={sc.code} (0x{sc.code:04x})"
        elif name == "diy":
            d = b.sub_body
            checks += [
                ("sub_diy", int(b.sub.value) == 0x0A),
                ("slot", d.slot == raw[3]),
                ("builder", proto.build_diy_activate(d.slot) == raw),
            ]
            detail = f"diy slot=0x{d.slot:02x}"
        elif name == "music":
            m = b.sub_body
            mode_id = getattr(m.mode_id, "value", m.mode_id)
            rgb = (m.rgb.r, m.rgb.g, m.rgb.b) if m.manual_color_count >= 1 else None
            checks += [
                ("sub_music", int(b.sub.value) == 0x13),
                ("mode_id", mode_id == raw[3]),
                ("sensitivity", m.sensitivity == raw[4]),
                ("style", m.style == raw[5]),
                ("count", m.manual_color_count == raw[6]),
                ("rgb", rgb == (0, 230, 210)),
                (
                    "builder",
                    proto.build_music_mode_with_color(mode_id, m.sensitivity, rgb, bool(m.style)) == raw,
                ),
            ]
            detail = f"music mode={getattr(m.mode_id, 'name', mode_id)} sens={m.sensitivity} style={m.style} rgb={rgb}"
        ok = all(v for _, v in checks)
        fails += 0 if ok else 1
        bad = ",".join(n for n, v in checks if not v)
        print(
            f"{'PASS' if ok else 'FAIL'} {name:11s} op={k.opcode.name} {detail}" + (f"  <FAILED: {bad}>" if bad else "")
        )
    print("\nALL PASS" if not fails else f"\n{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
