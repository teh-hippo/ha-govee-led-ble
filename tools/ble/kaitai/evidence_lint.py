#!/usr/bin/env python3
"""Evidence gate for the Kaitai protocol specs.

Every field that reads bytes (`seq` entries, at any nesting depth) MUST carry
exactly one re-verification evidence tag in its `doc`:

  [CONFIRMED_LIVE]  position AND meaning proven by a capture this spec
                    round-trips byte-exact (a differential / cross-check isolates it).
  [INFERRED]        position confirmed by round-trip, meaning reasoned from
                    protocol.py / analysis, not isolated by a capture.

A field with no tag FAILS the gate; it is never silently promoted.

THERE WAS A THIRD TAG. [INHERITED] meant "modelled from the write side with no
confirming capture in this direction", and it was used, and it is now empty: every
field that carried it was either promoted by a capture or deleted outright. Deleted
is the important half. The practice that emptied this category is that an unevidenced
field gets removed rather than weakly labelled, because naming bytes nobody has
observed the meaning of asserts knowledge we do not have. That
practice leaves the tag nothing to describe, and an empty category is somewhere to put
a field instead of deleting it.

H617A and H6199 now have independent specs. A new model still starts from its own
captured bytes rather than inheriting either model's fields.

The gate enforces completeness (every field is labelled) and a closed vocabulary; it
does not and cannot judge whether a chosen tag is accurate, that stays a human/panel
call. Run:

    uv run --no-sync --with pyyaml python evidence_lint.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
TAGS = ("CONFIRMED_LIVE", "INFERRED")
# Tags that were once valid. Naming them keeps the failure specific: a stale [INHERITED]
# reports what happened to it rather than reading as a typo.
RETIRED_TAGS = {"INHERITED": "retired 2026-07-31 once empty; delete the field or evidence it"}
TAG_RE = re.compile(r"\[([A-Z_]+)\]")


def _field_doc_tags(doc: str) -> list[str]:
    return [t for t in TAG_RE.findall(doc or "") if t in TAGS]


def _check_entry(where: str, doc: str, problems: list[str], counts: dict[str, int]) -> None:
    doc = doc or ""
    found = _field_doc_tags(doc)
    bracketed = TAG_RE.findall(doc)
    retired = [t for t in bracketed if t in RETIRED_TAGS]
    stray = [t for t in bracketed if t not in TAGS and t not in RETIRED_TAGS and t.isupper() and "_" in t]
    if len(found) == 0 and not retired:
        problems.append(f"{where}: no evidence tag (need one of {TAGS})")
    elif len(found) > 1:
        problems.append(f"{where}: {len(found)} evidence tags {found}, expected exactly one")
    elif found:
        counts[found[0]] = counts.get(found[0], 0) + 1
    for tag in retired:
        problems.append(f"{where}: [{tag}] is retired ({RETIRED_TAGS[tag]})")
    if stray:
        problems.append(f"{where}: unknown bracketed tag(s) {stray} (typo?)")


def _lint_seq(seq: list, path: str, problems: list[str], counts: dict[str, int]) -> None:
    for field in seq:
        if not isinstance(field, dict) or "id" not in field:
            continue
        _check_entry(f"{path}/{field['id']}", field.get("doc", ""), problems, counts)


def _walk(node: dict, path: str, problems: list[str], counts: dict[str, int]) -> None:
    if isinstance(node.get("seq"), list):
        _lint_seq(node["seq"], path, problems, counts)
    instances = node.get("instances")
    if isinstance(instances, dict):
        for name, inst in instances.items():
            # Only byte-reading (positional / foreign-stream) instances need a tag;
            # pure computed `value:` accessors read no bytes and are exempt.
            if isinstance(inst, dict) and ("pos" in inst or "io" in inst):
                _check_entry(f"{path}/inst:{name}", inst.get("doc", ""), problems, counts)
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
    totals: dict[str, int] = dict.fromkeys(TAGS, 0)
    for ksy in specs:
        problems, counts = lint_spec(ksy)
        summary = " ".join(f"{t}={counts.get(t, 0)}" for t in TAGS)
        status = "OK  " if not problems else "FAIL"
        print(f"{status} {ksy.name:24s} {summary}")
        for p in problems:
            print(f"       - {p}")
        total_problems += len(problems)
        for tag in TAGS:
            totals[tag] += counts.get(tag, 0)
    field_count = sum(totals.values())
    print(f"\n{len(specs)} specs, {field_count} fields: " + " ".join(f"{t}={totals[t]}" for t in TAGS))
    if total_problems:
        print(f"\n{total_problems} evidence-gate problem(s)")
        return 1
    print("evidence gate: all fields labelled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
