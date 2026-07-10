"""Traceability gate: every public protocol builder must cite evidence and be byte-pinned.

This introspects protocol.py's builder surface and asserts it stays in lockstep with
protocol.BUILDER_EVIDENCE, the "# EXPERIMENTAL:" source markers, and the byte-exact tests in
tests/test_protocol.py, so nothing ships un-traced.
"""

import ast
import inspect
import re
from pathlib import Path

from custom_components.ha_govee_led_ble import protocol as proto

QUERY_CONSTANTS = {"STATE_QUERY", "BRIGHTNESS_QUERY", "COLOR_MODE_QUERY", "FW_QUERY", "HW_QUERY", "KEEP_ALIVE"}
_MARKER = re.compile(r"#\s*EXPERIMENTAL:\s*harness=\S+\s+encoding=\S+")
_BYTE_CALLS = {"H", "bytes", "bytearray"}
_TEST_PROTOCOL = Path(__file__).with_name("test_protocol.py")


def _builder_functions():
    out = {}
    for name, obj in vars(proto).items():
        if inspect.isfunction(obj) and obj.__module__ == proto.__name__:
            if name.startswith("build_") or name.startswith("parse_") or name == "split_status_frame":
                out[name] = obj
    return out


def _surface():
    return set(_builder_functions()) | QUERY_CONSTANTS


def _byte_pinned_symbols():
    tree = ast.parse(_TEST_PROTOCOL.read_text(encoding="utf-8"))
    pinned = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name.startswith("test")):
            continue
        refs = set()
        has_bytes = False
        for sub in ast.walk(node):
            if isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name) and sub.value.id == "proto":
                refs.add(sub.attr)
            elif isinstance(sub, ast.Call):
                fn = sub.func
                if isinstance(fn, ast.Name) and fn.id in _BYTE_CALLS:
                    has_bytes = True
                elif isinstance(fn, ast.Attribute) and fn.attr == "fromhex":
                    has_bytes = True
            elif isinstance(sub, ast.Constant) and isinstance(sub.value, bytes):
                has_bytes = True
        if has_bytes:
            pinned |= refs
    return pinned


def test_registry_covers_surface_exactly():
    surface = _surface()
    registered = set(proto.BUILDER_EVIDENCE)
    missing = surface - registered
    stale = registered - surface
    assert not missing, f"un-traced builders (add to BUILDER_EVIDENCE): {sorted(missing)}"
    assert not stale, f"stale registry entries (no such builder): {sorted(stale)}"


def test_registry_status_and_source_are_well_formed():
    for name, ev in proto.BUILDER_EVIDENCE.items():
        assert ev.status in {"VALIDATED", "EXPERIMENTAL"}, f"{name}: bad status {ev.status!r}"
        assert ev.source.strip(), f"{name}: empty evidence source"


def test_experimental_status_matches_source_marker():
    for name, obj in _builder_functions().items():
        ev = proto.BUILDER_EVIDENCE.get(name)
        assert ev is not None, f"{name}: missing from BUILDER_EVIDENCE"
        has_marker = bool(_MARKER.search(inspect.getsource(obj)))
        assert (ev.status == "EXPERIMENTAL") == has_marker, f"{name}: EXPERIMENTAL status must match a source marker"
    for name in QUERY_CONSTANTS:
        ev = proto.BUILDER_EVIDENCE.get(name)
        assert ev is not None and ev.status == "VALIDATED", f"{name}: query constants must be VALIDATED"


def test_every_builder_has_a_byte_pinned_test():
    unpinned = _surface() - _byte_pinned_symbols()
    assert not unpinned, f"builders lacking a byte-exact/decode-pinned test in test_protocol.py: {sorted(unpinned)}"
