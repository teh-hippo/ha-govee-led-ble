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
    ("timer", "aa23ff81071ec0010910800100008001000080b6"),
    ("sleep_timer", "aa11003210100000000000000000000000000089"),
    ("wake_timer", "aa1200641101001d0000000000000000000000d1"),
    ("cm_static", "aa051500000000000000000000000000000000ba"),
    ("cm_scene", "aa050409000000000000000000000000000000a2"),
    ("cm_diy", "aa050a980000000000000000000000000000003d"),
    ("cm_diy_saved", "aa050a8403000000000000000000000000000022"),
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
            ref = proto.parse_timer_schedule_table(payload)
            slots = list(b.slots)
            checks += [
                ("slot_count", len(slots) == 4),
                ("hours", [s.hour for s in slots] == [p.hour for p in ref]),
                ("minutes", [s.minute for s in slots] == [p.minute for p in ref]),
                ("repeat", [proto.parse_timer_repeat(s.repeat) for s in slots] == [p.repeat_days for p in ref]),
                (
                    "slot0",
                    (slots[0].enable_and_type, slots[0].hour, slots[0].minute, slots[0].repeat)
                    == (0x81, 0x07, 0x1E, 0xC0),
                ),
            ]
            detail = f"timer slot0=07:30 Sunday enabled(0x81); slots={[(s.enable_and_type, s.hour, s.minute, s.repeat) for s in slots]}"
        elif name == "sleep_timer":
            checks += [
                ("enabled", b.enabled == raw[2]),
                ("start_bri", b.start_brightness == raw[3]),
                ("close_min", b.close_minutes == raw[4]),
                ("current_min", b.current_minutes == raw[5]),
            ]
            detail = f"sleep enabled={b.enabled} start_bri={b.start_brightness} close={b.close_minutes}min (shared govee_common.sleep_timer)"
        elif name == "wake_timer":
            checks += [
                ("enabled", b.enabled == raw[2]),
                ("end_bri", b.end_brightness == raw[3]),
                ("hour", b.hour == raw[4]),
                ("minute", b.minute == raw[5]),
                ("repeat", b.repeat == raw[6]),
                ("duration", b.duration_minutes == raw[7]),
            ]
            detail = f"wake enabled={b.enabled} end_bri={b.end_brightness} {b.hour:02d}:{b.minute:02d} dur={b.duration_minutes}min (shared govee_common.wake_timer)"
        elif name.startswith("cm_"):
            ref = proto.parse_color_mode_response(payload)
            m = b.mode_body
            checks.append(("mode", int(b.mode.value) == payload[0]))
            if name == "cm_static":
                checks.append(("sub", int(m.sub) == payload[1]))
                detail = f"static sub={int(m.sub)} (RGB set + CT set both read back aa0515 00; colour never echoed, ref.rgb={ref.rgb_color})"
            elif name == "cm_scene":
                checks.append(("scene_id", m.scene_id == int.from_bytes(payload[1:3], "little")))
                detail = f"scene scene_id={m.scene_id} effect(ref)={ref.effect}"
            elif name in ("cm_diy", "cm_diy_saved"):
                checks += [("slot", m.slot == payload[1]), ("type_byte", m.type_byte == payload[2])]
                detail = f"diy slot={m.slot} type_byte=0x{m.type_byte:02x} diy_slot(ref)={ref.diy_slot}"
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
