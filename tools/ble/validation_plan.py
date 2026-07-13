"""Comprehensive Govee H617A/H6199 live protocol validation checklist.

Each Step declares:
  - prompt:  the single action to perform in the Govee app (one change at a time).
  - match:   predicate that recognises the relevant BLE frame (phone -> device, or a
             device reply for query steps).
  - one of:
      * expect (bytes) + check ("exact"|"prefix"): compared byte-for-byte against the
        frame our own protocol.py would emit -> this is how we detect protocol drift.
      * validate (callable): a custom structural check returning (ok, message).
      * neither: "observe only" -- the frame is decoded and reported for manual review.

The plan is intentionally ordered simple -> complex so a live run fails fast on basics.
`build_plan(protocol)` receives our integration's protocol module (may be None if it could
not be imported; exact-compare steps then degrade to observe-only).
"""

from __future__ import annotations

import datetime
import sys
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class Step:
    id: str
    prompt: str
    match: Callable[[bytes], bool]
    section: str = ""
    expect: bytes | None = None
    check: str = "structural"  # "exact" | "prefix" | "structural"
    prefix_len: int | None = None
    validate: Callable[[bytes], tuple[bool, str]] | None = None
    note: str = ""
    direction: str = "TX"  # "TX" phone->device, "RX" device reply
    optional: bool = False
    code_ref: str = ""  # where in our integration this maps (surfaced on FAIL)
    dedup: str = ""  # distinctness group: steps sharing it must each capture a distinct sig()
    sig: Callable[[bytes], bytes] | None = None  # the frame bytes that make a capture "distinct"
    confirm: bool = False  # discovery capture: don't auto-advance; user performs the action then presses Enter
    capture: str = ""  # "" normal; "diff" = phased A/B/A discovery (baseline -> change -> revert)
    phases: tuple[str, str, str] = ("", "", "")  # diff-capture sub-prompts; phases[2]="" skips the revert phase


# Per-step pointers into our integration, matched by step-id prefix. Surfaced in the
# report and on FAIL so a mismatch is resolved without hunting for the code.
CODE_REFS: list[tuple[str, str]] = [
    ("power", "protocol.py build_power"),
    ("bright-", "protocol.py build_brightness"),
    ("color-", "protocol.py build_color_rgb"),
    ("ct-", "protocol.py build_color_temp (sends RGB approx; app uses kelvin field)"),
    ("seg-bright", "protocol.py per-segment brightness (33 05 15 02, single-segment mask)"),
    ("seg-wb", "protocol.py build_white_brightness (all-segments mask 0x7fff = FF 7F, confirmed live)"),
    ("seg-", "protocol.py build_color_rgb per-segment mask"),
    ("scene", "protocol.py build_scene / build_scene_multi (per-scene scene_type prefix)"),
    ("diy-", "protocol.py DIY builders; light.py effect handling"),
    ("music", "protocol.py build_music_mode_with_color; light.py music services"),
    ("timer-", "protocol.py timer table 0x23; coordinator timer entities"),
    ("sleep", "protocol.py sleep timer 0x11"),
    ("wakeup", "protocol.py wake-up timer 0x12"),
    ("gradual", "protocol.py gradual timer 0x14"),
    ("h6199-video", "protocol.py build_video_mode (region, sub-mode and saturation)"),
    ("h6199-whitebalance", "protocol.py build_video_white_balance"),
    ("h6199-scene", "const.py H6199 profile (scenes not surfaced)"),
]


# ---- frame matchers -------------------------------------------------------


def _is(
    header: int, action: int | None = None, sub: int | None = None, subsub: int | None = None
) -> Callable[[bytes], bool]:
    def m(v: bytes) -> bool:
        if v[0] != header:
            return False
        if action is not None and v[1] != action:
            return False
        if sub is not None and v[2] != sub:
            return False
        if subsub is not None and v[3] != subsub:
            return False
        return True

    return m


def _is_music(v: bytes) -> bool:
    return v[0] == 0x33 and v[1] == 0x05 and v[2] in (0x13, 0x0C)


# ---- reusable structural validators --------------------------------------


def _seg_mask(v: bytes) -> int:
    return v[12] | (v[13] << 8)


def _v_level(decode: Callable[[bytes], int], target: int, tol: int, label: str) -> Callable[[bytes], tuple[bool, str]]:
    """Loose intermediate check: the on-wire value should track the asked fraction (catches curves)."""

    def v(frame: bytes) -> tuple[bool, str]:
        val = decode(frame)
        ok = abs(val - target) <= tol
        return ok, f"{label}={val} (asked ~{target} \u00b1{tol}) {'linear-ish' if ok else 'OFF - possible curve'}"

    return v


def _v_color_temp(v: bytes) -> tuple[bool, str]:
    """The colour-temperature control sends true-white as kelvin
    (33 05 15 01 00 00 00 <Khi Klo> <R G B>). An RGB-form frame means a colour was set, not a
    temperature -- reject it (soft) so the sweep only records real kelvin values."""
    if not (v[4] == 0 and v[5] == 0 and v[6] == 0):
        return False, f"RGB white rgb=({v[4]},{v[5]},{v[6]}) - use the colour-TEMPERATURE control, not a colour"
    kelvin = (v[7] << 8) | v[8]
    return True, f"KELVIN {kelvin}K rgb=({v[9]},{v[10]},{v[11]}) mask={_seg_mask(v):#06x}"


def _v_color_temp_bound(target_k: int, tol_k: int) -> Callable[[bytes], tuple[bool, str]]:
    """CT sweep quarter: must be kelvin-form AND near the linear-expected kelvin (catches curves)."""

    def v(frame: bytes) -> tuple[bool, str]:
        ok, msg = _v_color_temp(frame)
        if not ok:
            return ok, msg
        kelvin = (frame[7] << 8) | frame[8]
        near = abs(kelvin - target_k) <= tol_k
        return near, f"{msg} (asked ~{target_k}K \u00b1{tol_k}) {'linear-ish' if near else 'OFF - possible curve'}"

    return v


def _v_seg_color(want_mask: int) -> Callable[[bytes], tuple[bool, str]]:
    """Per-segment colour with teeth: the mask must match the addressed segment(s) EXACTLY
    (first segment = 0x0001, all 15 = 0x7fff). Confirmed live: segment k -> bit (k-1)."""

    def v(frame: bytes) -> tuple[bool, str]:
        mask = _seg_mask(frame)
        bits = [i for i in range(15) if mask & (1 << i)]
        ok = mask == want_mask
        msg = f"rgb=({frame[4]},{frame[5]},{frame[6]}) mask={mask:#06x} segments={bits or ['none']}"
        if ok:
            return True, msg
        want_bits = [i for i in range(15) if want_mask & (1 << i)]
        return False, msg + f" - expected mask {want_mask:#06x} segments={want_bits}"

    return v


def _v_seg_bright(v: bytes) -> tuple[bool, str]:
    """Per-segment brightness with teeth: exactly one segment targeted (single-bit mask)."""
    mask = v[5] | (v[6] << 8)
    n = bin(mask).count("1")
    ok = n == 1
    msg = f"brightness={v[4]}% mask={mask:#06x} ({n} seg)"
    return ok, msg if ok else msg + " - expected exactly ONE segment"


def _v_wb_level(target: int, tol: int) -> Callable[[bytes], tuple[bool, str]]:
    """Whole-strip brightness via the segment/white control: the level must track the asked
    fraction (catches curves) AND the mask must cover the whole strip, not a single segment."""

    def v(frame: bytes) -> tuple[bool, str]:
        bri, mask = frame[4], frame[5] | (frame[6] << 8)
        nbits = bin(mask).count("1")
        if mask != 0x7FFF:  # whole strip == all 15 segments; anything else isn't a strip-wide set
            return False, f"wb%={bri} mask={mask:#06x} ({nbits}/15) - set ALL segments (expected 0x7fff)"
        level_ok = abs(bri - target) <= tol
        verdict = "linear-ish" if level_ok else "level OFF - possible curve"
        return level_ok, f"wb%={bri} mask=0x7fff (all 15) (asked ~{target} \u00b1{tol}) {verdict}"

    return v


# Populated by build_plan() by inverting const.MUSIC_MODE_SLUGS so the harness display can
# never drift from the codes we actually ship. Single source of truth.
_MODE_NAMES: dict[int, str] = {}


def _music_mode_name(code: int) -> str:
    return _MODE_NAMES.get(code, f"unknown={code:#04x}")


def _v_music(v: bytes) -> tuple[bool, str]:
    sub, mode, sens = v[2], v[3], v[4]
    style = "calm" if v[5] == 1 else "dynamic"
    return True, (
        f"subcmd={sub:#04x} mode={mode:#04x} ({_music_mode_name(mode)}) sens={sens} style={style} tail={v[5:13].hex()}"
    )


def _v_music_mode(expected: int) -> Callable[[bytes], tuple[bool, str]]:
    """Music-mode select with teeth: the wire code must equal what we ship in const.MUSIC_MODE_SLUGS."""

    def v(frame: bytes) -> tuple[bool, str]:
        ok = frame[3] == expected
        _, msg = _v_music(frame)
        return (
            ok,
            msg if ok else msg + f" - expected {_music_mode_name(expected)} ({expected:#04x}); DRIFT vs our const",
        )

    return v


def _is_music_param(v: bytes) -> bool:
    # a music param change may arrive as the 33 05 13 frame or an a3 multi-frame (extended modes)
    return (v[0] == 0x33 and v[1] == 0x05 and v[2] in (0x13, 0x0C)) or v[0] == 0xA3


def _v_music_is_mode(code: int) -> Callable[[bytes], tuple[bool, str]]:
    """Mode-activation gate (teeth): the frame must be this mode's select frame (v[3] == code)."""

    def v(frame: bytes) -> tuple[bool, str]:
        ok = frame[3] == code
        _, msg = _v_music(frame)
        return ok, msg if ok else msg + f" - waiting for {_music_mode_name(code)} ({code:#04x}); switch to it"

    return v


def _timer_fields(v: bytes) -> tuple[int, bool, bool, int, int, int]:
    eat = v[3]
    return v[2], bool(eat & 0x80), bool(eat & 0x01), v[4], v[5], v[6]


_WEEKDAY_BIT = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6}


def _target_time() -> tuple[int, int]:
    # A clearly-non-default time for this run. 06:00 is the app default, so "set it to 06:00"
    # changed nothing and validated nothing. Current wall-clock is stable per run and easy to read.
    now = datetime.datetime.now()
    return now.hour, now.minute


def _v_timer_set(slot: int, target: tuple[int, int] | None) -> Callable[[bytes], tuple[bool, str]]:
    """Scheduled slot: correct SLOT INDEX, ENABLED and turning ON. Slot 0 also pins the time and
    that NO day bits are set (the 'no repeat' the prompt asks for)."""

    def v(frame: bytes) -> tuple[bool, str]:
        idx, enabled, on, hh, mm, repeat = _timer_fields(frame)
        ok = idx == slot and enabled and on
        want = f"slot {slot} ENABLED + ON"
        if target is not None:
            ok = ok and (hh, mm) == target and (repeat & 0x7F) == 0
            want += f" at {target[0]:02d}:{target[1]:02d}, no day bits"
        msg = f"slot={idx} enabled={enabled} action={'on' if on else 'off'} time={hh:02d}:{mm:02d} repeat={repeat:#04x}"
        return ok, msg if ok else msg + f" - expected {want}"

    return v


def _v_timer_off(target: tuple[int, int]) -> Callable[[bytes], tuple[bool, str]]:
    """timer-off: slot 0 stays enabled at the target time but flips to action OFF."""

    def v(frame: bytes) -> tuple[bool, str]:
        idx, enabled, on, hh, mm, _repeat = _timer_fields(frame)
        ok = idx == 0 and enabled and not on and (hh, mm) == target
        msg = f"slot={idx} enabled={enabled} action={'on' if on else 'off'} time={hh:02d}:{mm:02d}"
        return ok, msg if ok else msg + f" - expected slot 0 ENABLED + OFF at {target[0]:02d}:{target[1]:02d}"

    return v


def _v_timer_day(day: str, target: tuple[int, int]) -> Callable[[bytes], tuple[bool, str]]:
    """Single-day repeat: exactly this day's confirmed bit, Mon=0 through Sun=6."""

    want_bit = _WEEKDAY_BIT[day]

    def v(frame: bytes) -> tuple[bool, str]:
        idx, enabled, on, hh, mm, repeat = _timer_fields(frame)
        bits = repeat & 0x7F
        ok = idx == 0 and enabled and on and (hh, mm) == target and bits == (1 << want_bit)
        set_days = [d for d, b in _WEEKDAY_BIT.items() if bits & (1 << b)] or ["none"]
        msg = f"slot={idx} repeat={repeat:#010b} ({repeat:#04x}) days={set_days}"
        return (
            ok,
            msg if ok else msg + f" - expected slot 0, {day} ONLY (bit {want_bit}) at {target[0]:02d}:{target[1]:02d}",
        )

    return v


def _v_sleep(v: bytes) -> tuple[bool, str]:
    """Sleep 0x11 with teeth: ENABLED (v[2]==1), initial brightness 10-100% (v[3]), countdown set."""
    ok = v[2] == 1 and 10 <= v[3] <= 100 and v[4] > 0
    msg = f"enable={v[2]} startBri={v[3]} closeMin={v[4]} curMin={v[5]}"
    return ok, msg if ok else msg + " - expected ENABLED, initial brightness 10-100%, countdown > 0"


def _v_wakeup(v: bytes) -> tuple[bool, str]:
    """Wake-up 0x12 with teeth: ENABLED (v[2]==1), final brightness 10-100% (v[3]), duration 10-60min (v[7])."""
    ok = v[2] == 1 and 10 <= v[3] <= 100 and 10 <= v[7] <= 60
    msg = f"enable={v[2]} endBri={v[3]} time={v[4]:02d}:{v[5]:02d} repeat={v[6]:#04x} rampMin={v[7]}"
    return ok, msg if ok else msg + " - expected ENABLED, final bri 10-100%, duration 10-60min"


def _v_video(v: bytes) -> tuple[bool, str]:
    """H6199 video: 33 05 00 <region> <dynamic> <saturation> ... Live capture (2026-07-08):
    region 1=full-screen / 0=part (matches our build_video_mode int(full_screen)); saturation at
    v[5]. Overall brightness is the general 33 04 command, NOT this frame."""
    region = "full" if v[3] == 1 else "part"
    return True, f"region={v[3]} ({region}) dynamic={v[4]} saturation={v[5]} body={v[3:10].hex()}"


def _v_video_region(expected: int) -> Callable[[bytes], tuple[bool, str]]:
    def v(frame: bytes) -> tuple[bool, str]:
        ok = frame[3] == expected
        _, msg = _v_video(frame)
        return ok, msg if ok else msg + f" - expected region {expected}"

    return v


def _v_whitebalance(v: bytes) -> tuple[bool, str]:
    """H6199 raw white-balance frame with teeth; UI-to-axis mapping is checked separately."""
    ok = v[2] == 0x00 and v[3] == 0x03
    msg = f"selector={v[2]:#04x} count={v[3]} values={v[4:9].hex()}"
    return ok, msg + (" (0x00/3 matches our code)" if ok else " - expected selector 0x00, count 0x03")


def _safe(fn, *a, **k):
    try:
        return fn(*a, **k)
    except Exception as exc:  # noqa: BLE001 - surface a broken builder instead of silently degrading
        print(f"warning: {getattr(fn, '__name__', fn)}{a} raised {exc!r}; step degraded to observe", file=sys.stderr)
        return None


def build_plan(protocol) -> list[Step]:  # noqa: ANN001
    p = protocol
    steps: list[Step] = []

    def add(**kw):
        steps.append(Step(**kw))

    # ---- A. Basics (exact byte-compare against our protocol.py) ----
    add(
        id="power-off",
        section="A basics",
        prompt="Turn the light OFF (if it's already off, turn it on first, then off)",
        match=_is(0x33, 0x01, 0x00),
        expect=_safe(p.build_power, False) if p else None,
        check="exact",
        note="33 01 00",
    )
    add(
        id="power-on",
        section="A basics",
        prompt="Turn the light ON",
        match=_is(0x33, 0x01, 0x01),
        expect=_safe(p.build_power, True) if p else None,
        check="exact",
        note="33 01 01 (leaves the strip on for the rest of section A)",
    )
    add(
        id="bright-min",
        section="A basics",
        prompt="Set brightness to MINIMUM (1%)",
        match=_is(0x33, 0x04),
        expect=_safe(p.build_brightness, 1) if p else None,
        check="exact",
        note="range endpoint (exact)",
    )
    add(
        id="bright-max",
        section="A basics",
        prompt="Set brightness to MAXIMUM (100%)",
        match=_is(0x33, 0x04),
        expect=_safe(p.build_brightness, 100) if p else None,
        check="exact",
        note="range endpoint (exact)",
    )
    add(
        id="color-red",
        section="A basics",
        prompt="Set colour to pure RED (255,0,0)",
        match=_is(0x33, 0x05, 0x15, 0x01),
        expect=_safe(p.build_color_rgb, 255, 0, 0) if p else None,
        check="exact",
    )
    add(
        id="color-green",
        section="A basics",
        prompt="Set colour to pure GREEN (0,255,0)",
        match=_is(0x33, 0x05, 0x15, 0x01),
        expect=_safe(p.build_color_rgb, 0, 255, 0) if p else None,
        check="exact",
    )
    add(
        id="color-blue",
        section="A basics",
        prompt="Set colour to pure BLUE (0,0,255)",
        match=_is(0x33, 0x05, 0x15, 0x01),
        expect=_safe(p.build_color_rgb, 0, 0, 255) if p else None,
        check="exact",
    )

    # ---- B. Colour temperature: sweep warm->cool. build_color_temp now emits the true kelvin
    # frame (33 05 15 01 00 00 00 <Khi Klo> <R G B preview>); validate the kelvin field within
    # tolerance (the RGB preview bytes are cosmetic and not byte-compared). ----
    add(
        id="ct-min",
        section="B colour-temp",
        prompt="Set colour temperature to the WARMEST end (minimum)",
        match=_is(0x33, 0x05, 0x15, 0x01),
        validate=_v_color_temp_bound(2000, 1000),
        note="record the MIN kelvin the app emits (expect ~2000K)",
    )
    add(
        id="ct-50",
        section="B colour-temp",
        prompt="Set colour temperature to about the MIDDLE",
        match=_is(0x33, 0x05, 0x15, 0x01),
        validate=_v_color_temp_bound(5500, 1500),
        note="one midpoint confirms the mapping scales (kelvin is a new encoding this session)",
    )
    add(
        id="ct-max",
        section="B colour-temp",
        prompt="Set colour temperature to the COOLEST end (maximum)",
        match=_is(0x33, 0x05, 0x15, 0x01),
        validate=_v_color_temp_bound(9000, 1500),
        note="record the MAX kelvin the app emits (expect ~9000K)",
    )

    # ---- C. Segments (H617A: 15 addressable) ----
    add(
        id="seg-one",
        section="C segments",
        prompt="Colour ONLY the first segment (e.g. red)",
        match=_is(0x33, 0x05, 0x15, 0x01),
        validate=_v_seg_color(0x0001),
        note="expect single-bit mask 0x0001",
    )
    add(
        id="seg-all",
        section="C segments",
        prompt="Colour ALL segments the same (e.g. red)",
        match=_is(0x33, 0x05, 0x15, 0x01),
        validate=_v_seg_color(0x7FFF),
        note="expect mask 0x7fff (all 15)",
    )
    add(
        id="seg-bright",
        section="C segments",
        prompt="Set ONE segment's brightness lower than the rest",
        match=_is(0x33, 0x05, 0x15, 0x02),
        validate=_v_seg_bright,
        note="per-segment brightness frame 33 05 15 02",
    )
    # Whole-strip brightness via the segment/white control: sweep min->max to check the level
    # curve and confirm the all-segments mask (0x7fff). build_white_brightness must use this
    # mask (the app sends FF 7F, not 0x0000).
    add(
        id="seg-wb-min",
        section="C segments",
        prompt="Set the WHOLE-strip brightness to MINIMUM (via the segment/white brightness control)",
        match=_is(0x33, 0x05, 0x15, 0x02),
        validate=_v_wb_level(1, 4),
        note="endpoint: tight tolerance; expect all-segments mask",
    )
    add(
        id="seg-wb-50",
        section="C segments",
        prompt="Set the whole-strip brightness to about 50%",
        match=_is(0x33, 0x05, 0x15, 0x02),
        validate=_v_wb_level(50, 12),
        note="one midpoint confirms scaling; endpoints prove range + all-segments mask",
    )
    add(
        id="seg-wb-max",
        section="C segments",
        prompt="Set the whole-strip brightness to MAXIMUM",
        match=_is(0x33, 0x05, 0x15, 0x02),
        validate=_v_wb_level(100, 4),
        note="endpoint: tight tolerance; expect all-segments mask",
    )

    # ---- D. Scenes: exact-compare a thorough sample against OUR catalogue (scenes.py) so every
    # name->code and the complex multi-frame definitions are PROVEN, not assumed. Simple scenes
    # verify the activation code; multi scenes verify the a3 body (definition + scene prefix). ----
    if p:
        for name in ("sunrise", "candlelight", "rainbow", "energetic"):
            e = p.SCENES.get(name)
            if e is None or not e.is_simple:
                continue
            add(
                id=f"scene-{name}",
                section="D scenes",
                prompt=f"Apply the '{name}' scene",
                match=_is(0x33, 0x05, 0x04),
                expect=_safe(p.build_scene, e.code),
                check="exact",
                note=f"verify name->code: {name} = {e.code}",
            )
        for name in ("aurora", "bloom", "candy", "halloween", "desert b"):
            e = p.SCENES.get(name)
            if e is None or e.is_simple:
                continue
            frames = _safe(p.build_scene_multi, e.param, e.code, e.scene_type)
            add(
                id=f"scene-{name.replace(' ', '-')}",
                section="D scenes",
                prompt=f"Apply the '{name}' scene (complex, multi-frame)",
                match=lambda v: v[0] == 0xA3 and v[1] == 0x00,
                expect=frames[0] if frames else None,
                check="exact",
                note=f"line up the effect definition + scene prefix for {name} (code {e.code})",
            )
    else:
        add(
            id="scene-observe",
            section="D scenes",
            prompt="Apply any built-in SCENE",
            match=_is(0x33, 0x05, 0x04),
            validate=lambda v: (True, f"scene activation {v[2:6].hex()}"),
        )

    # ---- E. DIY effects: the 33 05 0a activation is GENERIC (same 3f... for every DIY); the
    # effect definition is the a3 idx=0x00 body, which varies per effect -- so match that. These are
    # OBSERVE captures (we have no per-name body reference to byte-compare), confirmed by the user.
    # NOTE: applying a DIY (or opening the DIY screen) can sync the WHOLE library as a burst of
    # a3-idx0 bodies, so the captured body is "a real DIY definition", not provably the tapped one.
    # dedup makes diy-2/diy-color pick a body not already recorded. ----
    add(
        id="diy-1",
        section="E diy",
        prompt="Apply any DIY effect (a DIY definition body is captured)",
        match=lambda v: v[0] == 0xA3 and v[1] == 0x00,
        validate=lambda v: (True, f"diy body {v[2:12].hex()}"),
        dedup="diy",
        sig=lambda v: bytes(v[2:19]),
        confirm=True,
        note="a3 idx=0x00 body = a DIY definition; the app may upload the whole DIY library at once",
    )
    add(
        id="diy-2",
        section="E diy",
        prompt="Apply a DIFFERENT DIY effect (compare its pattern to the first)",
        match=lambda v: v[0] == 0xA3 and v[1] == 0x00,
        validate=lambda v: (True, f"diy body {v[2:12].hex()}"),
        dedup="diy",
        sig=lambda v: bytes(v[2:19]),
        confirm=True,
        note="a3 idx=0x00 body; must differ from the first DIY capture",
    )
    add(
        id="diy-color",
        section="E diy",
        prompt="Discover the DIY PALETTE-colour encoding (A/B/A diff-capture)",
        match=lambda v: v[0] == 0xA3,
        capture="diff",
        phases=(
            "apply a DIY effect and let its palette settle",
            "change exactly ONE palette colour to a clearly different colour, then Apply",
            "change that same colour back to what it was, then Apply",
        ),
        note="diff-capture the a3 body: a single controlled palette change shows which body bytes hold the colour",
    )

    # ---- F. Music. Mode codes come from OUR const (protocol.MUSIC_MODE_SLUGS) so a DRIFT only fires
    # when the wire disagrees with what we ship, not with a stale analysis table. The shipped slugs
    # are underscored; reconstruct the spaced display names so the labels below still key cleanly. ----
    music_display = {
        "energetic": "Energetic",
        "rhythm": "Rhythm",
        "spectrum": "Spectrum",
        "rolling": "Rolling",
        "separation": "Separation",
        "hopping": "Hopping",
        "piano keys": "Piano Keys",
        "fountain": "Fountain",
        "day and night": "Day and Night",
        "bloom": "Bloom",
        "shiny": "Shiny",
    }
    mode_code = (
        {slug.replace("_", " "): code for slug, code in p.MUSIC_MODE_SLUGS.items()}
        if p is not None
        else {
            "energetic": 0x05,
            "rhythm": 0x03,
            "spectrum": 0x04,
            "rolling": 0x06,
            "separation": 0x32,
            "hopping": 0x33,
            "piano keys": 0x34,
            "fountain": 0x35,
            "day and night": 0x37,
            "bloom": 0x30,
            "shiny": 0x31,
        }
    )
    _MODE_NAMES.clear()
    _MODE_NAMES.update({code: music_display.get(name, name.title()) for name, code in mode_code.items()})
    for name, code in mode_code.items():
        disp = music_display.get(name, name.title())
        add(
            id=f"music-{name.replace(' ', '')}",
            section="F music",
            prompt=f"Switch to Music mode '{disp}' (if it's already on, switch away then back so it re-sends)",
            match=_is_music,
            validate=_v_music_mode(code),
            dedup="music-mode",
            sig=lambda v: bytes(v[3:4]),
            note=f"our const wire code = {code:#04x} ({code}); each mode must send a distinct code",
        )
    for sid, level, target, tol in [
        ("min", "MINIMUM", 0, 4),
        ("50", "about 50%", 50, 15),
        ("max", "MAXIMUM", 100, 4),
    ]:
        add(
            id=f"music-sens-{sid}",
            section="F music",
            prompt=f"On the current music mode, set SENSITIVITY to {level}",
            match=_is_music,
            validate=_v_level(lambda v: v[4], target, tol, "sens"),
            note="byte[4] sensitivity; endpoints tight, quarters loose (confirms range + linearity)",
        )
    # ---- F2. Per-mode PARAMETERS. Each mode is ACTIVATED first (a strict mode-select gate that
    # consumes the switch frame), then every parameter is a user-CONFIRMED capture: do the action,
    # then press [Enter]. Discovery has no value-teeth, so auto-advance raced through mode switches
    # and stale frames -- activation + confirmation is the fix. ----
    # Per-mode PARAMETERS discovered by A/B/A diff-capture: the harness captures the config
    # frames at a baseline, again after a known change, and again after reverting, then shows
    # which bytes moved. No guessing which frame carries the param -- the diff reveals it.
    # (pid, mode, baseline action, change action, revert action ["" = no revert])
    music_params = [
        ("style", "rhythm", "set the style to DYNAMIC", "switch the style to CALM", "switch back to DYNAMIC"),
        ("autocolor", "spectrum", "turn AUTO-COLOUR ON", "turn AUTO-COLOUR OFF", "turn AUTO-COLOUR back ON"),
        (
            "color1",
            "spectrum",
            "auto-colour OFF, set the single colour to RED",
            "change the colour to BLUE",
            "set it back to RED",
        ),
        (
            "colors",
            "separation",
            "note the current multi-colour palette",
            "change the palette to clearly different colours",
            "",
        ),
        (
            "seppoint",
            "separation",
            "move the SEPARATION POINT to its LEFT-most position",
            "move it to its RIGHT-most position",
            "move it back to the LEFT-most",
        ),
        ("gradient", "separation", "turn GRADIENT OFF", "turn GRADIENT ON", "turn GRADIENT OFF"),
        (
            "bgcolor",
            "hopping",
            "set the BACKGROUND colour to RED",
            "change the background to BLUE",
            "set it back to RED",
        ),
        ("relbright", "hopping", "set RELATIVE BRIGHTNESS to MINIMUM", "set it to MAXIMUM", "set it back to MINIMUM"),
        ("keys", "piano keys", "set the NUMBER OF KEYS to 8", "set it to 15", "set it back to 8"),
        (
            "direction",
            "fountain",
            "set DIRECTION to CLOCKWISE",
            "set it to TWO-WAY (the third option)",
            "set it back to CLOCKWISE",
        ),
        ("segments", "day and night", "set the NUMBER OF SEGMENTS to 1", "set it to 7", "set it back to 1"),
        ("speed", "day and night", "set SPEED to MINIMUM", "set it to MAXIMUM", "set it back to MINIMUM"),
    ]
    current_mode = None
    for pid, mode, base_a, chg_a, rev_a in music_params:
        disp = music_display.get(mode, mode.title())
        if mode != current_mode:
            current_mode = mode
            add(
                id=f"music-act-{mode.replace(' ', '-')}",
                section="F music",
                prompt=f"Switch to '{disp}' music mode (from a DIFFERENT mode so it re-sends)",
                match=_is_music,
                validate=_v_music_is_mode(mode_code[mode]),
                note=f"activate {disp} ({mode_code[mode]:#04x}); consumes the mode-select frame",
            )
        add(
            id=f"music-p-{pid}",
            section="F music",
            prompt=f"On '{disp}': discover the {pid.upper()} encoding (A/B/A diff-capture)",
            match=_is_music_param,
            capture="diff",
            phases=(base_a, chg_a, rev_a),
            note=f"diff-capture '{pid}': baseline -> change -> revert; the harness reports which config bytes move",
        )

    # ---- G. Timers. 4 scheduled slots (0x23) + 1 sleep (0x11) + 1 wake-up (0x12), all with TEETH.
    # Uses a non-default TARGET time so "set the timer" actually changes something (06:00 was the
    # app default). Weekday bit-order Mon=bit0 through Sun=bit6 is live-confirmed. ----
    th, tm = _target_time()
    for slot in range(4):
        extra = f" at {th:02d}:{tm:02d}, NO repeat (clear all days)" if slot == 0 else " (any time)"
        add(
            id=f"timer-slot{slot}",
            section="G timers",
            prompt=f"Enable scheduled TIMER #{slot + 1} to turn the light ON{extra}",
            match=_is(0x33, 0x23),
            validate=_v_timer_set(slot, (th, tm) if slot == 0 else None),
            dedup="timer-slot",
            sig=lambda v: bytes(v[2:3]),
            note="33 23 <idx> <enableAndType 0x81=on> <hh> <mm> <repeat>; pins the SLOT INDEX byte v[2]",
        )
    for day in ("Monday", "Sunday"):
        add(
            id=f"timer-day-{day[:3].lower()}",
            section="G timers",
            prompt=f"Set TIMER #1 to repeat on {day.upper()} ONLY (clear the other days)",
            match=_is(0x33, 0x23),
            validate=_v_timer_day(day, (th, tm)),
            note=f"{day} = bit {_WEEKDAY_BIT[day]} (Mon=0 through Sun=6 confirmed); expect that one day bit",
        )
    add(
        id="timer-off",
        section="G timers",
        prompt="Change TIMER #1 to turn the light OFF instead of on",
        match=_is(0x33, 0x23),
        validate=_v_timer_off((th, tm)),
        note="enableAndType bit0 clears (action off); slot 0 stays enabled at the target time",
    )
    add(
        id="sleep",
        section="G timers",
        prompt="ENABLE a SLEEP timer: set a countdown (minutes) and an initial brightness (10-100%)",
        match=_is(0x33, 0x11),
        validate=_v_sleep,
        confirm=True,
        note="0x11: enable v[2] (must be 1), initial brightness v[3], countdown minutes v[4]",
    )
    add(
        id="wakeup",
        section="G timers",
        prompt="ENABLE a WAKE-UP timer: set a time, a duration (10-60 min) and a final brightness (10-100%)",
        match=_is(0x33, 0x12),
        validate=_v_wakeup,
        confirm=True,
        note="0x12: enable v[2] (must be 1), final brightness v[3], time v[4:6], repeat v[6], duration v[7]",
    )
    add(
        id="gradual",
        section="G timers",
        prompt="In device SETTINGS (gear), toggle any 'Gradual on/off' soft transition (skip with Enter if absent)",
        match=_is(0x33, 0x14),
        validate=lambda v: (True, f"gradual state={v[2]}"),
        note="cmd 0x14 from prior protocol analysis; not exposed on the captured H617A app",
        optional=True,
    )
    add(
        id="poweroff-memory",
        section="G timers",
        prompt="In SETTINGS: toggle 'Power-off memory' / 'Resume last state' ON then OFF (Enter to skip)",
        match=_is(0x33, 0x41),
        validate=lambda v: (True, f"power-off memory enabled={v[2]}"),
        confirm=True,
        note="0x41: NO live capture yet; pins build_poweroff_memory + parse_poweroff_memory (aa 41 reply)",
        optional=True,
    )

    # ---- H. Queries (device replies observed on connect / on demand) ----
    add(
        id="q-power",
        section="H queries",
        direction="RX",
        prompt="(auto) observe device power query reply",
        match=lambda v: v[0] == 0xAA and v[1] == 0x01,
        validate=lambda v: (True, f"power={'on' if v[2] else 'off'}"),
        optional=True,
    )
    add(
        id="q-segments",
        section="H queries",
        direction="RX",
        prompt="(auto) observe segment read-back (aa a5)",
        match=lambda v: v[0] == 0xAA and v[1] == 0xA5,
        validate=lambda v: (True, f"group={v[2]} {v[3:13].hex()}"),
        optional=True,
    )
    add(
        id="q-timer",
        section="H queries",
        direction="RX",
        prompt="(auto) observe timer table reply (aa 23)",
        match=lambda v: v[0] == 0xAA and v[1] == 0x23,
        validate=lambda v: (True, f"timer table {v[2:19].hex()}"),
        optional=True,
    )
    add(
        id="q-colormode",
        section="H queries",
        direction="RX",
        prompt="(auto) observe colour-mode reply (aa 05) -- drive a colour-temp value first for the CT read-back",
        match=lambda v: v[0] == 0xAA and v[1] == 0x05,
        validate=lambda v: (True, f"mode={v[2:4].hex()} payload={v[4:13].hex()}"),
        optional=True,
    )

    # ---- I. H6199 TV (passive app-sniff only; never direct-drive the H6199).
    # From live s7 capture: 33 05 00 <region> ... <saturation@v5>; brightness is the general
    # 33 04 command; white balance 33 a9 00 03 matches our code. ----
    add(
        id="h6199-video-full",
        section="I h6199",
        prompt="On the H6199 in the app: set Video mode to FULL-screen ('All') capture",
        match=_is(0x33, 0x05, 0x00),
        validate=_v_video_region(1),
        note="region byte v[3]=1 for full/All (confirmed live 2026-07-08; matches our int(full_screen))",
    )
    add(
        id="h6199-video-part",
        section="I h6199",
        prompt="On the H6199: switch Video capture to PART/portion of screen",
        match=_is(0x33, 0x05, 0x00),
        validate=_v_video_region(0),
        note="region byte v[3]=0 for part/portion (confirmed live 2026-07-08)",
    )
    add(
        id="h6199-video-sat",
        section="I h6199",
        prompt="On the H6199 Video mode: change the SATURATION",
        match=_is(0x33, 0x05, 0x00),
        validate=_v_video,
        confirm=True,
        note="saturation is v[5] of the 33 05 00 video frame",
    )
    add(
        id="h6199-video-bright",
        section="I h6199",
        prompt="On the H6199: change the overall BRIGHTNESS",
        match=_is(0x33, 0x04),
        validate=lambda v: (True, f"brightness={v[2]}% via the general 33 04 command (not the video frame)"),
        confirm=True,
        note="H6199 overall brightness = general 33 04 brightness command, confirmed live",
    )
    add(
        id="h6199-whitebalance",
        section="I h6199",
        prompt="On the H6199: adjust the WHITE BALANCE / colour calibration",
        match=_is(0x33, 0xA9),
        validate=_v_whitebalance,
        confirm=True,
        note="live: 33 a9 00 03 01 <red><blue>; raw axes only, UI mapping unresolved",
    )
    add(
        id="h6199-scene",
        section="I h6199",
        prompt="On the H6199: apply a built-in SCENE",
        match=_is(0x33, 0x05, 0x04),
        validate=lambda v: (True, f"scene activation {v[2:6].hex()}"),
        confirm=True,
        note="confirms H6199 exposes scenes (we do not surface them yet)",
        optional=True,
    )
    add(
        id="h6199-music",
        section="I h6199",
        prompt="On the H6199: enable MUSIC and pick a mode (e.g. Rhythm), with and without a chosen colour",
        match=_is(0x33, 0x05, 0x13),
        validate=lambda v: (True, f"mode={v[3]:#04x} sens={v[4]} byte5={v[5]} rgb={v[7:10].hex()}"),
        confirm=True,
        note="H6199 music 33 05 13; confirm byte5 sub-variant + Spectrum code 0x04 (never drive; sniff only)",
        optional=True,
    )

    for s in steps:
        s.code_ref = next((ref for prefix, ref in CODE_REFS if s.id.startswith(prefix)), "")
        if s.section.startswith("I "):  # H6199 is a separate session; never mandatory in an H617A run
            s.optional = True

    return steps
