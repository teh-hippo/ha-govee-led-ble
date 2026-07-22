#!/usr/bin/env python3
"""Evidence gate for the Kaitai protocol specs.

Every field that reads bytes (`seq` entries, at any nesting depth) MUST carry
exactly one re-verification evidence tag in its `doc`:

  [CONFIRMED_LIVE]  position AND meaning proven by a capture this spec
                    round-trips byte-exact (a differential / cross-check isolates it).
  [INFERRED]        position confirmed by round-trip, meaning reasoned from
                    protocol.py / analysis, not isolated by a capture.
  [INHERITED]       modelled from the write-side / docs with no confirming
                    capture in this direction (opaque regions, unexercised
                    branches). This is the pessimistic default: a field with no
                    tag FAILS the gate, it is never silently promoted.

The gate enforces completeness (every field is labelled) and a closed
vocabulary; it does not and cannot judge whether a chosen tag is accurate, that
stays a human/panel call. Run:

    uv run --no-sync --with pyyaml python evidence_lint.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
TAGS = ("CONFIRMED_LIVE", "INFERRED", "INHERITED")
TAG_RE = re.compile(r"\[([A-Z_]+)\]")


def _field_doc_tags(doc: str) -> list[str]:
    return [t for t in TAG_RE.findall(doc or "") if t in TAGS]


def _lint_seq(seq: list, path: str, problems: list[str], counts: dict[str, int]) -> None:
    for field in seq:
        if not isinstance(field, dict) or "id" not in field:
            continue
        fid = field["id"]
        where = f"{path}/{fid}"
        found = _field_doc_tags(field.get("doc", ""))
        stray = [t for t in TAG_RE.findall(field.get("doc", "") or "") if t not in TAGS and t.isupper() and "_" in t]
        if len(found) == 0:
            problems.append(f"{where}: no evidence tag (need one of {TAGS})")
        elif len(found) > 1:
            problems.append(f"{where}: {len(found)} evidence tags {found}, expected exactly one")
        else:
            counts[found[0]] = counts.get(found[0], 0) + 1
        if stray:
            problems.append(f"{where}: unknown bracketed tag(s) {stray} (typo?)")


def _walk(node: dict, path: str, problems: list[str], counts: dict[str, int]) -> None:
    if isinstance(node.get("seq"), list):
        _lint_seq(node["seq"], path, problems, counts)
    types = node.get("types")
    if isinstance(types, dict):
        for name, sub in types.items():
            if isinstance(sub, dict):
                _walk(sub, f"{path}::{name}", problems, counts)


def lint_spec(ksy: Path) -> tuple[list[str], dict[str, int]]:
    spec = yaml.safe_load(ksy.read_text())
    problems: list[str] = []
    counts: dict[str, int] = {}
    _walk(spec, ksy.stem, problems, counts)
    return problems, counts


def main(argv: list[str]) -> int:
    specs = [Path(a) for a in argv[1:]] or sorted(HERE.glob("*.ksy"))
    if not specs:
        print("no .ksy specs found", file=sys.stderr)
        return 2
    total_problems = 0
    for ksy in specs:
        problems, counts = lint_spec(ksy)
        summary = " ".join(f"{t}={counts.get(t, 0)}" for t in TAGS)
        status = "OK  " if not problems else "FAIL"
        print(f"{status} {ksy.name:24s} {summary}")
        for p in problems:
            print(f"       - {p}")
        total_problems += len(problems)
    if total_problems:
        print(f"\n{total_problems} evidence-gate problem(s)")
        return 1
    print("\nevidence gate: all fields labelled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
