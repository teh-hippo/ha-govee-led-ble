#!/usr/bin/env python3
"""Guided LIVE Govee BLE protocol validation harness.

Runs a comprehensive checklist (validation_plan.py) one action at a time. For each step it
prints ONE thing to do in the Govee app (e.g. "Set brightness to 1%"), watches the live BLE
sniff, decodes the frame the app emits, and checks it against what our own protocol.py would
send -- PASS / FAIL, with a byte diff. No AI in the loop; it is a self-checking capture session.

Frame source (pick one):
  --live [name]      start idevicebtlogger (Windows, via pwsh) writing a fresh pcap, tail it,
                     run the plan, then stop the capture. Default name: validate-<timestamp>.
  --pcap PATH        tail an existing pcap that something else is writing live.
  --replay PATH      feed an existing capture through the plan once (offline replay).
  --sim              NO hardware and NO pcap: build every exact-compare frame from our own
                     protocol.py, then push it back through the SAME decode + compare path.

--sim is a self-test of encode<->decode symmetry and plan<->protocol drift ONLY. A green run
proves every builder ran, every generated frame decodes cleanly, and the round-trip is
self-consistent. It does NOT prove our bytes match a real Govee device -- only --live can.

Examples:
  tools/ble/validate_protocol.py --live
  tools/ble/validate_protocol.py --sim                           # headless self-test / CI smoke
  tools/ble/validate_protocol.py --replay <capture-dir>/music-all.pcap
  tools/ble/validate_protocol.py --replay <cap> --only F         # just the music section
  tools/ble/validate_protocol.py --live --resume                 # skip steps that passed last run
  tools/ble/validate_protocol.py --live --from music-bloom       # jump to a specific step

Env overrides (live mode): GOVEE_BLE_DIR, GOVEE_WIN_CAP, GOVEE_BTLOGGER, PWSH.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import select
import struct
import subprocess
import sys
import time
import types
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import decode_govee as dg  # noqa: E402  (same directory)
import validation_plan as vp  # noqa: E402


# --------------------------------------------------------------------------
# Load our integration's protocol.py standalone (without triggering the HA
# package __init__), so exact-compare steps can compute expected bytes.
# --------------------------------------------------------------------------
def load_protocol():
    root = _HERE.parent.parent / "custom_components" / "ha_govee_led_ble"
    if not (root / "protocol.py").exists():
        return None
    try:
        pkg = types.ModuleType("_hg_shim")
        pkg.__path__ = [str(root)]
        sys.modules["_hg_shim"] = pkg
        for mod in ("scenes", "protocol"):
            spec = importlib.util.spec_from_file_location(f"_hg_shim.{mod}", root / f"{mod}.py")
            m = importlib.util.module_from_spec(spec)
            sys.modules[f"_hg_shim.{mod}"] = m
            spec.loader.exec_module(m)
        return sys.modules["_hg_shim.protocol"]
    except Exception as exc:  # noqa: BLE001
        print(f"! could not import protocol.py ({exc}); exact-compare steps become observe-only")
        return None


# --------------------------------------------------------------------------
# Per-packet ATT extraction (mirrors decode_govee._iter_att, one packet).
# --------------------------------------------------------------------------
def _att_pdus(pkt: bytes):
    if len(pkt) < 5:
        return
    direction = "RX" if (struct.unpack(">I", pkt[0:4])[0] & 1) else "TX"
    if pkt[4] != 0x02:  # H4 ACL only
        return
    acl = pkt[5:]
    if len(acl) < 8:
        return
    l2_len, cid = struct.unpack("<HH", acl[4:8])
    if cid != dg.ATT_CID:
        return
    att = acl[8 : 8 + l2_len]
    if len(att) < 3:
        return
    opcode = att[0]
    if opcode not in dg.WRITE_OPCODES:
        return
    yield direction, att[3:]


class PcapStream:
    """Incrementally reads a (possibly growing) libpcap file, yielding Govee frames."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.offset = 0
        self.endian: str | None = None
        self.rec: struct.Struct | None = None

    def _init_header(self, data: bytes) -> bool:
        if len(data) < 24:
            return False
        magic = struct.unpack("<I", data[0:4])[0]
        self.endian = ">" if magic == 0xD4C3B2A1 else "<"
        self.rec = struct.Struct(self.endian + "IIII")
        self.offset = 24
        return True

    def poll(self) -> list[tuple[str, bytes]]:
        """Return (direction, value) for every new Govee frame since the last poll.

        Reads only the bytes appended since the previous poll. The capture grows to many MB
        during a session, and the discovery phases poll in a tight loop while they wait for the
        user, so re-reading the whole file each time exhausts memory (ENOMEM on the drvfs mount).
        """
        out: list[tuple[str, bytes]] = []
        if not self.path.exists():
            return out
        with self.path.open("rb") as f:
            if self.endian is None:
                if not self._init_header(f.read(24)):
                    return out
            f.seek(self.offset)
            buf = f.read()
        pos = 0
        assert self.rec is not None
        while len(buf) - pos >= 16:
            _, _, incl, _ = self.rec.unpack(buf[pos : pos + 16])
            if len(buf) - pos - 16 < incl:
                break  # packet not fully written yet
            pkt = buf[pos + 16 : pos + 16 + incl]
            pos += 16 + incl
            for direction, val in _att_pdus(pkt):
                if dg._is_govee(val):
                    out.append((direction, val))
        self.offset += pos
        return out


def replay_frames(path: Path) -> list[tuple[str, bytes]]:
    data = Path(path).read_bytes()
    return [(d, v) for d, _op, _h, v in dg._iter_att(data) if dg._is_govee(v)]


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
def _byte_diff(exp: bytes, got: bytes) -> str:
    n = max(len(exp), len(got))
    diffs = [i for i in range(n) if (exp[i] if i < len(exp) else None) != (got[i] if i < len(got) else None)]
    # byte 19 is the derived XOR checksum; drop it so the diff shows only meaningful payload bytes
    payload = [i for i in diffs if i != 19]
    return ",".join(str(i) for i in (payload or diffs))


def validate_step(step: vp.Step, v: bytes) -> tuple[str, str]:
    """Return (status, detail). status in PASS/FAIL/OBSERVE."""
    if step.validate is not None:
        ok, msg = step.validate(v)
        return ("PASS" if ok else "FAIL"), msg
    if step.expect is not None:
        exp = step.expect
        if step.check == "exact":
            ok = v == exp
        else:  # prefix
            n = step.prefix_len or len(exp)
            ok = v[:n] == exp[:n]
        if ok:
            return "PASS", f"matches ours: {v.hex()}"
        return "FAIL", f"ours={exp.hex()} app={v.hex()} diff@bytes[{_byte_diff(exp, v)}]"
    return "OBSERVE", dg.label(v, step.direction)


def _interesting(v: bytes) -> bool:
    # suppress aa01 power keepalives from the "watching" chatter
    return not (v[0] == 0xAA and v[1] == 0x01)


# --------------------------------------------------------------------------
# Discovery diff-capture (A/B/A). A music/DIY parameter whose on-wire encoding we
# don't yet know is captured by watching the config frames at a baseline, again
# after a known change, and again after a revert, then showing which bytes moved.
# The byte-diff isolates the parameter, so no per-param frame family has to be
# guessed up front; a stale frame can't be mistaken for the change.
# --------------------------------------------------------------------------
def _assemble_a3(frames: list[bytes]) -> bytes:
    """Concatenated bodies (v[2:19]) of the LAST complete a3 transaction (idx 0x00..0xff)."""
    txns: list[list[bytes]] = []
    cur: list[bytes] = []
    for v in frames:
        idx = v[1]
        if idx == 0x00:
            cur = [v]
        elif cur:
            cur.append(v)
        if idx == 0xFF and cur:
            txns.append(cur)
            cur = []
    use = txns[-1] if txns else cur  # last complete transaction, else any partial in progress
    return b"".join(v[2:19] for v in use)


def _cap_family(v: bytes) -> str | None:
    """Classify a config frame: reassembled 'a3' body, or the '33 05 13/0c' music tail."""
    if v[0] == 0xA3:
        return "a3"
    if v[0] == 0x33 and v[1] == 0x05 and v[2] in (0x13, 0x0C):
        return "tail"
    return None


def _collect_phase(stream: PcapStream) -> dict:
    """Watch TX config frames until the user presses [Enter] to end the phase."""
    stream.poll()  # drop frames buffered before the phase armed
    a3: list[bytes] = []
    tails: list[bytes] = []

    def sort(pairs: list[tuple[str, bytes]]) -> None:
        for d, v in pairs:
            if d != "TX":
                continue
            fam = _cap_family(v)
            if fam == "a3":
                a3.append(v)
            elif fam == "tail":
                tails.append(v)

    while True:
        sort(stream.poll())
        if _stdin_key() is not None:
            sort(stream.poll())  # final drain for frames that landed with the keypress
            break
        time.sleep(0.1)
    return {"a3": _assemble_a3(a3), "tail": tails[-1][2:19] if tails else b"", "n": len(a3) + len(tails)}


def _bx(b: bytes, i: int) -> str:
    return f"{b[i]:02x}" if i < len(b) else "--"


def _diff_offsets(a: bytes, b: bytes) -> list[int]:
    return [i for i in range(max(len(a), len(b))) if _bx(a, i) != _bx(b, i)]


def _describe_cap(cap: dict) -> str:
    parts = []
    if cap["a3"]:
        parts.append(f"a3[{len(cap['a3'])}B] {cap['a3'].hex()}")
    if cap["tail"]:
        parts.append(f"tail {cap['tail'].hex()}")
    return "   ".join(parts) if parts else "(no config frames)"


def _diff_caps(base: dict, chg: dict) -> tuple[bool, str]:
    """Return (any_changed, human summary) comparing the a3 body and the 33-05 tail."""
    lines: list[str] = []
    changed = False
    for fam in ("a3", "tail"):
        a, b = base[fam], chg[fam]
        if not a and not b:
            continue
        offs = _diff_offsets(a, b)
        if not offs:
            lines.append(f"{fam}: unchanged")
            continue
        changed = True
        shown = offs[:12]
        detail = ", ".join(f"[{i}] {_bx(a, i)}->{_bx(b, i)}" for i in shown)
        more = f" (+{len(offs) - len(shown)} more)" if len(offs) > len(shown) else ""
        lines.append(f"{fam} moved: {detail}{more}")
    return changed, " | ".join(lines) if lines else "no config frames captured"


def _reverted(base: dict, chg: dict, rev: dict) -> bool:
    """True if every family that MOVED base->change has returned to the baseline value."""
    for fam in ("a3", "tail"):
        if _diff_offsets(base[fam], chg[fam]) and _diff_offsets(base[fam], rev[fam]):
            return False
    return True


def _wait_key(prompt: str) -> str:
    print(prompt, end="", flush=True)
    if not sys.stdin.isatty():
        return ""
    try:
        return sys.stdin.readline().strip().lower()
    except EOFError, OSError:
        return ""


def _phase(stream: PcapStream, tag: str, action: str) -> dict:
    print(f"        [{tag}] {action}; then press [Enter] \u2026")
    cap = _collect_phase(stream)
    print(f"                 captured {cap['n']} frame(s): {_describe_cap(cap)}")
    return cap


def run_diff_capture(step: vp.Step, stream: PcapStream) -> dict:
    base_a, chg_a, rev_a = step.phases
    print("        DIFF-CAPTURE (A/B/A). Do each action IN THE APP, tap Apply if there is one, then [Enter].")
    while True:
        base = _phase(stream, "A baseline", base_a)
        chg = _phase(stream, "B change", chg_a)
        changed, summary = _diff_caps(base, chg)
        rev: dict | None = None
        if base["n"] == 0 and chg["n"] == 0:
            print("        \u26a0 no config frames in EITHER phase \u2014 did you tap Apply?")
        elif not changed:
            print(f"        \u26a0 NO CHANGE \u2014 {summary}")
            print("          (the parameter is not carried in these frames, or Apply was missed)")
        else:
            print(f"        \u0394 {summary}")
            if rev_a:
                rev = _phase(stream, "A' revert", rev_a)
                ok = _reverted(base, chg, rev)
                print(f"          revert: {'OK, bytes returned to baseline' if ok else 'did NOT return (confounded?)'}")
        key = _wait_key("          [Enter]=accept  r=redo  s=skip: ")
        if key == "r":
            print("          (redoing)")
            continue
        if key == "s":
            return _record(step, "SKIP" if step.optional else "MISS", "skipped by user (no encoding captured)")
        detail = summary
        if changed and rev is not None:
            detail += f" | revert {'OK' if _reverted(base, chg, rev) else 'FAIL'}"
        return _record(step, "OBSERVE", detail, chg["a3"] or chg["tail"] or b"")


def diff_selftest() -> int:
    """Headless self-check of the diff-capture pure logic (a3 reassembly, diff, revert)."""
    f0 = bytes([0xA3, 0x00]) + bytes(range(1, 18)) + bytes([0])
    f1 = bytes([0xA3, 0xFF]) + bytes(range(18, 35)) + bytes([0])
    g0 = bytes([0xA3, 0x00]) + bytes([9]) * 17 + bytes([0])
    g1 = bytes([0xA3, 0xFF]) + bytes([9]) * 17 + bytes([0])
    base = {"a3": bytes([1, 2, 3]), "tail": b"", "n": 1}
    chg = {"a3": bytes([1, 9, 3]), "tail": b"", "n": 1}
    changed, summary = _diff_caps(base, chg)
    checks = {
        "a3-reassemble": _assemble_a3([f0, f1]) == bytes(range(1, 35)),
        "a3-last-transaction-wins": _assemble_a3([f0, f1, g0, g1]) == bytes([9]) * 34,
        "a3-partial-dropped": _assemble_a3([bytes([0xA3, 0x00]) + bytes(17) + bytes([0])]) == bytes(17),
        "no-change": _diff_caps(base, dict(base)) == (False, "a3: unchanged"),
        "change-detected": changed and "[1] 02->09" in summary,
        "revert-ok": _reverted(base, chg, base),
        "revert-fail": not _reverted(base, chg, chg),
    }
    bad = [name for name, ok in checks.items() if not ok]
    if bad:
        print(f"DIFF-LOGIC SELFTEST: FAIL {bad}")
        return 1
    print(f"DIFF-LOGIC SELFTEST: PASS ({len(checks)} checks)")
    return 0


# --------------------------------------------------------------------------
# Runners
# --------------------------------------------------------------------------
def run_replay(frames: list[tuple[str, bytes]], steps: list[vp.Step]) -> list[dict]:
    results: list[dict] = []
    seen: dict[str, set] = {}  # distinctness, mirroring run_live
    cursor = 0
    for step in steps:
        if step.capture == "diff":
            results.append(_record(step, "OBSERVE", "diff-capture needs --live (interactive A/B/A)"))
            _print_result(step, "OBSERVE", "diff-capture needs --live (interactive A/B/A)")
            continue
        outcome: tuple[str, str, bytes] | None = None
        near: tuple[str, str, bytes] | None = None
        near_i = cursor
        i = cursor
        while i < len(frames):
            d, v = frames[i]
            i += 1
            if d != step.direction or not step.match(v):
                continue
            if step.dedup and step.sig is not None and bytes(step.sig(v)) in seen.get(step.dedup, set()):
                continue  # already captured; keep scanning for a distinct one
            status, detail = validate_step(step, v)
            if status == "FAIL":  # wrong value: keep scanning for the target (as live does)
                near = (status, detail, v)
                near_i = i
                continue
            outcome = (status, detail, v)
            cursor = i
            break
        if outcome is None and near is not None:
            outcome = near
            cursor = near_i  # advance past the near-miss so the next step can't reuse it
        if outcome is None:
            status, detail, frame = ("SKIP" if step.optional else "MISS"), "no matching frame in capture", b""
        else:
            status, detail, frame = outcome
            if step.confirm and status == "PASS":
                status = "OBSERVE"  # replay cannot confirm a discovery capture; record as observed
            if step.dedup and step.sig is not None:
                seen.setdefault(step.dedup, set()).add(bytes(step.sig(frame)))
        results.append(_record(step, status, detail, frame))
        _print_result(step, status, detail)
    return results


def _stdin_key() -> str | None:
    if not sys.stdin.isatty():  # background/piped run: auto-advance on frames only
        return None
    if select.select([sys.stdin], [], [], 0)[0]:
        line = sys.stdin.readline()
        if line == "":  # EOF, not a keypress
            return None
        return line.strip().lower() or "\n"
    return None


def _record(step: vp.Step, status: str, detail: str, frame: bytes = b"") -> dict:
    return {
        "id": step.id,
        "section": step.section,
        "prompt": step.prompt,
        "status": status,
        "detail": detail,
        "frame": frame.hex() if frame else "",
        "note": step.note,
        "code_ref": step.code_ref,
    }


def _progress_path() -> Path:
    return _capture_dir() / "validation-progress.json"


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"set {name} before using capture or replay modes")
    return value


def _capture_dir() -> Path:
    return Path(_required_env("GOVEE_BLE_DIR")) / "captures"


def load_progress() -> dict[str, dict]:
    path = _progress_path()
    if not path.exists():
        return {}
    try:
        return {r["id"]: r for r in json.loads(path.read_text())}
    except ValueError, KeyError:
        return {}


def save_progress(results: list[dict]) -> None:
    _progress_path().write_text(json.dumps(results, indent=2))


def run_live(stream: PcapStream, steps: list[vp.Step], prior: dict[str, dict] | None = None) -> list[dict]:
    prior = prior or {}
    results: list[dict] = []
    pending: list[tuple[str, bytes]] = []  # frames not yet consumed carry across steps (no drop)
    seen: dict[str, set] = {}  # distinctness signatures, owned here so back/resume stay correct
    print(
        "\nMost steps auto-pass the instant the app sends the matching frame."
        "\nCAPTURE steps (discovery) wait for you: do the action, then press [Enter] to record what's shown."
        "\nKeys:  [Enter]=accept what's shown & move on   b=back   r=re-watch   p=pause   q=quit (saves)\n"
    )

    def remember(step: vp.Step, frame: bytes) -> None:
        if step.dedup and step.sig is not None and frame:
            seen.setdefault(step.dedup, set()).add(bytes(step.sig(frame)))

    def forget(step: vp.Step, rec: dict) -> None:
        if step.dedup and step.sig is not None and rec.get("frame"):
            seen.get(step.dedup, set()).discard(bytes(step.sig(bytes.fromhex(rec["frame"]))))

    i = 0
    while i < len(steps):
        step = steps[i]
        if step.id in prior:  # already passed in a prior run, or skipped before --from
            rec = prior[step.id]
            results.append(rec)
            if rec.get("status") in ("PASS", "OBSERVE") and rec.get("frame"):
                remember(step, bytes.fromhex(rec["frame"]))
            print(f"[{i + 1}/{len(steps)}] {step.section}  \u2713 {rec['status']} (resumed) {step.id}")
            i += 1
            continue
        if step.capture == "diff":
            print(f"[{i + 1}/{len(steps)}] {step.section}  \u2794 {step.prompt}")
            if step.note:
                print(f"        note: {step.note}")
            pending.clear()
            try:
                rec = run_diff_capture(step, stream)
            except Exception as exc:  # noqa: BLE001  a discovery crash must not kill the whole run
                rec = _record(step, "ERROR", f"diff-capture crashed: {exc!r}")
                print(f"        ! error: {exc!r} (recorded; continuing)")
            results.append(rec)
            _print_result(step, rec["status"], rec["detail"])
            save_progress(results)
            i += 1
            continue
        auto = step.prompt.startswith("(auto)")
        opt = " (optional \u2014 [Enter] to skip if it doesn't fire)" if step.optional else ""
        print(f"[{i + 1}/{len(steps)}] {step.section}  \u2794 {step.prompt}{opt}")
        if step.note:
            print(f"        note: {step.note}")
        if not auto:
            if step.confirm:
                print("        (CAPTURE: perform the action in the app, then press [Enter] to record what's shown)")
            else:
                print("        (perform it in the Govee app now; watching\u2026)")
        outcome: tuple[str, str, bytes] | None = None
        action: str | None = None
        near: tuple[str, str, bytes] | None = None  # right command, value not matched yet
        candidate: tuple[str, str, bytes] | None = None  # confirm steps: last capture awaiting [Enter]
        shown: bytes | None = None
        captured_announced = False  # confirm steps: announce the capture ONCE, then update silently
        if step.confirm:
            stream.poll()  # drop tail frames already emitted by the PRIOR action before we start
            pending.clear()  # discovery capture: only frames from THIS action count, not a buffered one
        while outcome is None and action is None:
            pending.extend(stream.poll())
            while pending:
                d, v = pending.pop(0)
                if d == step.direction and step.match(v):
                    key = bytes(step.sig(v)) if step.sig is not None else b""
                    if step.dedup and key in seen.get(step.dedup, set()):
                        if v != shown:
                            shown = v
                            print(f"        \u25cb already captured {key.hex()} \u2014 pick a DIFFERENT one")
                        continue
                    status, detail = validate_step(step, v)
                    if status == "FAIL":  # not the expected value yet: show it, keep watching
                        near = (status, detail, v)
                        candidate = None  # a newer wrong action supersedes any earlier capture
                        if v != shown:
                            shown = v
                            print(f"        \u25cb not yet: {detail}")
                        continue
                    if step.confirm:  # discovery capture: honest OBSERVE, not PASS (no byte-compare)
                        candidate = ("OBSERVE", detail, v)  # always keep the LATEST matching frame
                        if not captured_announced:  # announce once; a flood must not spam the screen
                            captured_announced = True
                            print("        \u25c9 matched \u2014 finish the action, then [Enter] records the latest")
                        continue
                    outcome = (status, detail, v)
                    break
                if _interesting(v) and v != shown:
                    shown = v
                    print(f"        \u00b7 saw {d} {dg.label(v, d)}")
            if outcome is not None:
                break
            key = _stdin_key()
            if key == "q":
                action = "quit"
            elif key == "b":
                action = "back"
            elif key == "r":
                near = shown = candidate = None
                captured_announced = False
                print("        (re-watching\u2026)")
            elif key == "p":
                print("        paused; press Enter to resume watching\u2026")
                sys.stdin.readline()
            elif key is not None:
                action = "accept"
            else:
                time.sleep(0.15)
        if action == "quit":
            save_progress(results)
            print("        progress saved; resume with --resume")
            return results
        if action == "back":
            if results and i >= 1:
                forget(steps[i - 1], results[-1])
                results.pop()
            i = max(0, i - 1)
            prior.pop(steps[i].id, None)  # so a resumed step can be re-watched after backing into it
            continue
        if action == "accept":  # confirm-capture first, else the near-miss drift, else skip
            if candidate is not None:
                remember(step, candidate[2])
                results.append(_record(step, candidate[0], candidate[1], candidate[2]))
                _print_result(step, candidate[0], candidate[1])
            elif near is not None:
                results.append(_record(step, near[0], near[1], near[2]))
                _print_result(step, near[0], near[1])
            else:
                results.append(_record(step, "SKIP", "skipped by user"))
                print("        \u2013 SKIP")
            save_progress(results)
            i += 1
            continue
        status, detail, frame = outcome
        remember(step, frame)
        results.append(_record(step, status, detail, frame))
        _print_result(step, status, detail)
        save_progress(results)
        i += 1
    return results


_ICON = {
    "PASS": "\u2713",
    "FAIL": "\u2717",
    "OBSERVE": "\u25cb",
    "MISS": "\u2717",
    "SKIP": "\u2013",
    "ABORT": "\u2013",
    "ERROR": "\u2717",
}


def _print_result(step: vp.Step, status: str, detail: str) -> None:
    print(f"        {_ICON.get(status, ' ')} {status}: {detail}")
    if status in ("FAIL", "MISS") and step.code_ref:
        print(f"        \u2192 our code: {step.code_ref}")
    print()


class _Tee:
    """Mirror stdout to a flushed log file so a run in a separate terminal can be tailed."""

    def __init__(self, stream, log):
        self._stream = stream
        self._log = log

    def write(self, s: str) -> int:
        self._stream.write(s)
        try:
            self._log.write(s)
            self._log.flush()
        except OSError:
            pass
        return len(s)

    def flush(self) -> None:
        self._stream.flush()

    def isatty(self) -> bool:
        return self._stream.isatty()


# --------------------------------------------------------------------------
# Live capture control (Windows idevicebtlogger via pwsh)
# --------------------------------------------------------------------------
def start_capture(name: str) -> tuple[str, Path]:
    ble_dir = Path(_required_env("GOVEE_BLE_DIR"))
    win_cap = _required_env("GOVEE_WIN_CAP")
    exe = _required_env("GOVEE_BTLOGGER")
    pwsh = os.environ.get("PWSH", "pwsh.exe")
    cap_dir = ble_dir / "captures"
    cap_dir.mkdir(parents=True, exist_ok=True)
    win_out = f"{win_cap}/{name}.pcap"
    cmd = (
        f"$p = Start-Process -FilePath '{exe}' -ArgumentList '-f','pcap','{win_out}' "
        f"-WindowStyle Hidden -PassThru; $p.Id"
    )
    pid = subprocess.check_output([pwsh, "-NoProfile", "-Command", cmd], text=True).strip()  # noqa: S603  controlled pwsh command, no user input
    pcap = cap_dir / f"{name}.pcap"
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if pcap.exists() and pcap.stat().st_size >= 24:
            return pid, pcap
        time.sleep(0.25)
    stop_capture(pid)
    raise RuntimeError("capture preflight failed: idevicebtlogger wrote no pcap header")


def stop_capture(pid: str) -> None:
    pwsh = os.environ.get("PWSH", "pwsh.exe")
    subprocess.run(  # noqa: S603  controlled pwsh command, no user input
        [pwsh, "-NoProfile", "-Command", f"Stop-Process -Id {pid} -ErrorAction SilentlyContinue"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


# --------------------------------------------------------------------------
def write_report(results: list[dict], dest_dir: Path, source: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    counts: dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    md = [
        f"# Govee protocol validation report ({ts})",
        "",
        f"Source: `{source}`",
        "",
        "Summary: " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())),
        "",
        "| step | section | status | detail | our code |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        ref = r.get("code_ref", "") if r["status"] in ("FAIL", "MISS") else ""
        detail = r["detail"].replace("|", "/")
        md.append(f"| {r['id']} | {r['section']} | {r['status']} | {detail} | {ref.replace('|', '/')} |")
    out_md = dest_dir / f"validation-report-{ts}.md"
    out_md.write_text("\n".join(md) + "\n")
    (dest_dir / f"validation-report-{ts}.json").write_text(json.dumps(results, indent=2))
    return out_md


# --------------------------------------------------------------------------
# Self-test source (--sim): no hardware, no pcap. Every exact-compare frame is
# built by our own protocol.py and pushed back through the SAME decode + compare
# path a live run uses. This proves three things, and ONLY these three:
#   1. each step's expected-bytes computation runs (no builder raised),
#   2. the generated frame decodes cleanly (decode_govee accepts it),
#   3. the round-trip is self-consistent (expected == observed).
# It guards encode<->decode symmetry and plan<->protocol drift. It does NOT prove
# our bytes match a real Govee device -- only --live can.
# --------------------------------------------------------------------------
def _sim_exact(step: vp.Step) -> tuple[str, str, bytes]:
    exp = step.expect
    if exp is None:  # builder raised or was pruned: plan<->protocol drift
        return "FAIL", "expected-bytes computation produced nothing (protocol.py builder failed)", b""
    if not dg._is_govee(exp):  # bad length / header / XOR checksum
        return "FAIL", f"generated frame does not decode as Govee: {exp.hex()}", exp
    decoded = dg.label(exp, step.direction)
    status, detail = validate_step(step, exp)
    return status, f"{detail}  [{decoded}]", exp


def _sim_readbacks(protocol: types.ModuleType) -> list[bytes]:
    """Drive a GoveeDeviceSim with the coordinator's wire frames and collect its query replies."""
    sys.path.insert(0, str(_HERE.parent.parent))  # repo root, so tools.ble.* resolves as in the tests
    try:
        from tools.ble.mock_ble.mock_device import GoveeDeviceSim
    except Exception as exc:  # noqa: BLE001  sim pulls in the HA package; degrade to skips without it
        print(f"  ! GoveeDeviceSim unavailable ({exc}); device read-back self-tests will skip")
        return []
    sim = GoveeDeviceSim("H617A")
    weekdays = [protocol.Weekday.MON, protocol.Weekday.WED, protocol.Weekday.FRI]
    commands = (
        protocol.build_power(True),
        protocol.build_brightness(42),
        protocol.build_color_rgb(10, 20, 30),
        # Program a scheduled slot so the aa 23 timer read-back has a real slot to report.
        protocol.build_timer_schedule(index=0, enabled=True, on_action=True, hour=7, minute=30, repeat_days=weekdays),
    )
    for command in commands:
        sim.handle_write(command)
    replies: list[bytes] = []
    queries = (
        protocol.STATE_QUERY,
        protocol.BRIGHTNESS_QUERY,
        protocol.COLOR_MODE_QUERY,
        protocol.build_packet(protocol.STATUS_HEADER, 0x23, []),  # aa 23 timer table
    )
    for query in queries:
        replies.extend(bytes(reply) for reply in sim.handle_write(query))
    return replies


def _sim_readback(step: vp.Step, replies: list[bytes]) -> tuple[str, str, bytes]:
    for reply in replies:
        if not step.match(reply):
            continue
        if not dg._is_govee(reply):
            return "FAIL", f"sim read-back does not decode as Govee: {reply.hex()}", reply
        decoded = dg.label(reply, step.direction)
        status, detail = validate_step(step, reply)
        return status, f"sim read-back {detail}  [{decoded}]", reply
    return "SKIP", "sim does not model this read-back yet (opcode unsupported; needs --live)", b""


def run_sim(steps: list[vp.Step], protocol: types.ModuleType) -> list[dict[str, str]]:
    print(
        "\nSELF-TEST (--sim): frames are built by our own protocol.py, not captured from a device."
        "\nThis guards encode<->decode symmetry and plan<->protocol drift ONLY; it does NOT prove"
        "\nour bytes match a real Govee light (use --live for that).\n"
    )
    replies = _sim_readbacks(protocol)
    results: list[dict[str, str]] = []
    for step in steps:
        if step.check == "exact":
            status, detail, frame = _sim_exact(step)
        elif step.direction == "RX":
            status, detail, frame = _sim_readback(step, replies)
        else:  # structural / observe-only: the plan has no canonical protocol.py frame to self-test
            status, detail, frame = "SKIP", "not self-testable (structural/observe; needs --live)", b""
        results.append(_record(step, status, detail, frame))
        print(f"  {_ICON.get(status, ' ')} {status:<5} {step.section:<13} {step.id:<20} {detail}")
        if status == "FAIL" and step.code_ref:
            print(f"        -> our code: {step.code_ref}")
    return results


def _sim_summary(results: list[dict[str, str]]) -> int:
    counts: dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    passed, failed, skipped = counts.get("PASS", 0), counts.get("FAIL", 0), counts.get("SKIP", 0)
    print(f"\nSIM SUMMARY  pass={passed} fail={failed} skip={skipped}")
    print("  (skip = structural/observe step or a read-back the sim does not model yet)")
    if failed:
        print("SIM RESULT: FAIL -- a builder broke, a frame stopped decoding, or the plan drifted from protocol.py")
        return 1
    print("SIM RESULT: PASS -- encode<->decode symmetry holds (NOT a real-device check; use --live)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Guided live Govee BLE protocol validation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--live", nargs="?", const="", metavar="NAME", help="start+tail a fresh capture")
    src.add_argument("--pcap", metavar="PATH", help="tail an existing (live) pcap")
    src.add_argument("--replay", metavar="PATH", help="feed an existing capture through the plan")
    src.add_argument(
        "--sim",
        action="store_true",
        help="self-test (no hardware/pcap): round-trip our protocol.py frames through decode+compare; "
        "guards encode<->decode symmetry and plan drift, NOT real-device parity",
    )
    ap.add_argument("--only", metavar="SECTION", help="run only steps whose section starts with this letter/word")
    ap.add_argument("--resume", action="store_true", help="skip steps that PASSed in the last run")
    ap.add_argument("--from", dest="from_step", metavar="STEP", help="start at this step id (skip earlier)")
    args = ap.parse_args()

    protocol = load_protocol()
    steps = vp.build_plan(protocol)
    if args.only:
        key = args.only.lower()
        steps = [s for s in steps if s.section.lower().startswith(key)]
        if not steps:
            print(f"no steps match section '{args.only}'")
            return 2
    print(f"loaded {len(steps)} validation steps; protocol.py {'OK' if protocol else 'UNAVAILABLE'}")
    if protocol is None:
        print(
            "\n  !! protocol.py could not be imported -- exact byte-compare is DISABLED.\n"
            "     Every exact step degrades to observe-only, so drift will NOT be caught.\n"
            "     Fix the import before trusting a run (Ctrl-C now if this is unexpected).\n",
            file=sys.stderr,
        )

    if args.sim:  # headless, deterministic self-test: no capture dir, no report, no live log
        if protocol is None:
            print("--sim needs protocol.py: its exact-compare frames come from our builders.", file=sys.stderr)
            return 2
        return _sim_summary(run_sim(steps, protocol)) or diff_selftest()

    dest = _capture_dir()
    dest.mkdir(parents=True, exist_ok=True)
    if not args.replay:
        live_log_path = dest / "validation-live.log"
        log_fh = live_log_path.open("w", buffering=1)
        sys.stdout = _Tee(sys.stdout, log_fh)
        sys.stderr = _Tee(sys.stderr, log_fh)  # so a traceback lands in the log, not just the terminal
        print(f"live log: {live_log_path}")

    if args.replay:
        frames = replay_frames(Path(args.replay))
        print(f"replaying {len(frames)} Govee frames from {args.replay}\n")
        results = run_replay(frames, steps)
        report = write_report(results, dest, f"replay:{args.replay}")
    else:
        pid = None
        if args.live is not None:
            name = args.live or f"validate-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            pid, pcap = start_capture(name)
            print(f"started capture '{name}' (pid {pid}) -> {pcap}")
        else:
            pcap = Path(args.pcap)
        prior: dict[str, dict] = {}
        if args.resume:
            prior = {sid: r for sid, r in load_progress().items() if r.get("status") in ("PASS", "OBSERVE")}
            print(f"resuming: {len(prior)} previously-passed steps will be skipped")
        if args.from_step:
            idx = next((k for k, s in enumerate(steps) if s.id == args.from_step), None)
            if idx is None:
                print(f"--from step '{args.from_step}' not found")
                return 2
            for s in steps[:idx]:
                prior.setdefault(s.id, _record(s, "SKIP", "before --from"))
        stream = PcapStream(pcap)
        try:
            results = run_live(stream, steps, prior)
        except KeyboardInterrupt:
            print("\naborted (progress saved)")
            results = []
        finally:
            if pid:
                stop_capture(pid)
                print(f"stopped capture (pid {pid})")
        report = write_report(results, dest, str(pcap)) if results else None

    if "report" in dir() and report:
        passed = sum(1 for r in results if r["status"] == "PASS")
        failed = sum(1 for r in results if r["status"] in ("FAIL", "MISS"))
        print(f"\nDONE: {passed} pass, {failed} fail/miss.  Report: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
