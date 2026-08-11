#!/usr/bin/env python3
"""Run the Kaitai .kst fixtures in spec/ against the compiled grammars.

One runner in place of the nine hand-written harnesses it replaced. Fixtures and their
field expectations live in spec/*.kst (Kaitai's own test format) with the bytes in src/,
so adding a case is data rather than code, and the corpus is committed so the gate checks
the same thing on a fresh clone as it does locally.

WHAT .kst CANNOT SAY, AND THIS RUNNER SUPPLIES. Checks that appear across the harnesses
and have no expression in the format, applied as repo-wide invariants to every fixture
rather than restated per case:

  * FULL CONSUMPTION. _io.is_eof() is a method call, not an attribute path. A grammar
    that silently leaves bytes unread is the main way a wrong layout still "passes", so
    this is the single most valuable check in the suite.
  * CHECKSUM, per family. The 20-byte envelope is XOR over bytes 0..18 and the 7-byte
    music stream frame is sum-8 over bytes 0..5. command_write models the checksum byte
    opaque and host-validated, and Kaitai 0.11 has no fold, so an in-spec assert could
    only re-read the byte and would prove nothing. The runner also refuses a corpus in
    which no fixture separates the two schemes, since "this family is XOR" is untested
    until some frame disagrees with sum-8.

Four further shapes live in spec/_aggregates.yaml because they span fixtures: value
spread across a corpus, pairwise differentials, capture ordering and cross-case equality.

The runner refuses anything it cannot evaluate. A misspelt attribute path or an assert
syntax it does not implement is a hard error, never a silent pass, because a test suite
that quietly skips is worse than one that is absent. For the same reason it refuses a
fixture in src/ that no case reads, a SPEC that no fixture reaches (see
check_every_spec_is_exercised, which is what stops a new model's grammar being written
from the encoder before any of its bytes have been captured), and an aggregate whose
pattern matches nothing.
"""

from __future__ import annotations

import hashlib
import importlib
import io
import os
import sys
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]  # pyyaml ships no type stubs
from kaitaistruct import KaitaiStream

HERE = Path(__file__).resolve().parent
GENERATED_DIR = Path(os.environ["KAITAI_GENERATED_DIR"]) if "KAITAI_GENERATED_DIR" in os.environ else None
if GENERATED_DIR is not None:
    sys.path.insert(0, str(GENERATED_DIR))

AGGREGATES_PATH = HERE / "spec" / "_aggregates.yaml"
PROTOCOL_BLOCKERS_PATH = HERE / "protocol_blockers.yaml"
FRAME_LENGTH = 20
CHECKSUM_INDEX = 19
MUSIC_STREAM_LENGTH = 7
MUSIC_STREAM_CHECKSUM_INDEX = 6
MUSIC_STREAM_PREFIX = b"\xa5\x02\x83"
PROTOCOL_BLOCKER_STATUSES = frozenset({"open", "resolved"})


class AssertUnevaluatableError(Exception):
    """The runner cannot evaluate this assert, which is a failure rather than a skip."""


@dataclass
class Case:
    path: Path
    id: str
    source: Path
    data: bytes
    module: str
    root: str | None
    asserts: list[dict[str, Any]]
    exception: str | None
    invariants: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)


def class_name(module: str) -> str:
    return "".join(part.title() for part in module.split("_"))


def load_case(path: Path) -> Case:
    doc = yaml.safe_load(path.read_text())
    for required in ("id", "data", "imports", "provenance", "fixture_sha256"):
        if required not in doc:
            raise AssertUnevaluatableError(f"{path.name}: missing required key {required!r}")
    source = HERE / "src" / doc["data"]
    if not source.exists():
        raise AssertUnevaluatableError(f"{path.name}: no such fixture {source}")
    provenance = doc["provenance"]
    if not isinstance(provenance, dict):
        raise AssertUnevaluatableError(f"{path.name}: provenance must be a mapping")
    for required in ("kind", "schema_model", "source_model", "source"):
        if not provenance.get(required):
            raise AssertUnevaluatableError(f"{path.name}: provenance is missing {required!r}")
    data = source.read_bytes()
    fixture_sha256 = hashlib.sha256(data).hexdigest()
    if doc["fixture_sha256"] != fixture_sha256:
        raise AssertUnevaluatableError(f"{path.name}: fixture_sha256 does not match {source.name}")
    imports = doc["imports"]
    modules = imports if isinstance(imports, list) else [imports]
    return Case(
        path=path,
        id=doc["id"],
        source=source,
        data=data,
        module=modules[0],
        root=doc.get("type"),
        asserts=doc.get("asserts") or [],
        exception=doc.get("exception"),
        invariants=doc.get("skip_invariants") or [],
        imports=modules,
        provenance=provenance,
    )


def resolve(root: Any, expression: str) -> Any:
    """Walk a dotted attribute path with optional [index] and a trailing .size.

    Deliberately not an expression evaluator. Anything richer than a path is rejected so
    a case cannot quietly assert something the runner is only pretending to check.
    """
    if not expression or any(token in expression for token in ("(", ")", "+", "-", "*", "/", "==")):
        raise AssertUnevaluatableError(f"unsupported assert expression: {expression!r}")
    current = root
    for part in expression.split("."):
        name, _, index = part.partition("[")
        if name == "size":
            current = len(current)
            continue
        if not hasattr(current, name):
            raise AssertUnevaluatableError(f"{type(current).__name__} has no attribute {name!r} in {expression!r}")
        current = getattr(current, name)
        if index:
            current = current[int(index.rstrip("]"), 0)]
    return current


def normalise(value: Any) -> Any:
    """Compare enums by value and byte strings by hex, so a .kst stays readable."""
    if hasattr(value, "value") and not isinstance(value, (int, str, bytes)):
        return value.value
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).hex()
    return value


def xor_checksum(payload: bytes) -> int:
    checksum = 0
    for byte in payload:
        checksum ^= byte
    return checksum


def sum_checksum(payload: bytes) -> int:
    return sum(payload) & 0xFF


def checksum_family(data: bytes) -> tuple[str, int, Any] | None:
    """Which checksum scheme this frame belongs to, or None if it carries no checksum.

    Two families are on the wire and they use DIFFERENT schemes, which is the sort of
    thing that gets assumed rather than tested. The 20-byte 0x33/0xaa envelope is XOR
    over the first 19 bytes; the 7-byte 0xa5 0x02 0x83 music stream frame is sum-8 over
    the first six. Getting this backwards still produces a plausible-looking byte.
    """
    if len(data) == FRAME_LENGTH:
        return "xor", CHECKSUM_INDEX, xor_checksum
    if len(data) == MUSIC_STREAM_LENGTH and data[:3] == MUSIC_STREAM_PREFIX:
        return "sum8", MUSIC_STREAM_CHECKSUM_INDEX, sum_checksum
    return None


def run_invariants(case: Case, parsed: Any) -> list[str]:
    failures = []
    if "consumed" not in case.invariants and not parsed._io.is_eof():
        failures.append(f"not fully consumed, {len(case.data) - parsed._io.pos()} byte(s) left")
    family = checksum_family(case.data)
    if family and "checksum" not in case.invariants:
        name, index, scheme = family
        rival = sum_checksum if scheme is xor_checksum else xor_checksum
        expected = case.data[index]
        payload = case.data[:index]
        if scheme(payload) != expected:
            failures.append(f"{name} {scheme(payload):#04x} does not match frame byte {index} {expected:#04x}")
        elif rival(payload) != scheme(payload) and rival(payload) == expected:
            failures.append(f"frame byte {index} matches the rival scheme rather than {name}")
    return failures


def find_type(module: Any, module_name: str, wanted: str) -> Any:
    """Locate a grammar type, which Kaitai nests inside the root class unless it IS the root."""
    if hasattr(module, wanted):
        return getattr(module, wanted)
    root = getattr(module, class_name(module_name), None)
    return getattr(root, wanted, None) if root else None


def run_case(case: Case) -> tuple[list[str], Any]:
    module = importlib.import_module(case.module)
    wanted = class_name(case.root) if case.root else class_name(case.module)
    grammar = find_type(module, case.module, wanted)
    if grammar is None:
        raise AssertUnevaluatableError(f"{case.id}: {case.module} defines no type {wanted!r}")
    try:
        parsed = grammar(KaitaiStream(io.BytesIO(case.data)))
        parsed._read()
    except Exception as exc:  # noqa: BLE001 -- a rejected fixture is a result, not a crash
        if case.exception and type(exc).__name__ == case.exception:
            return [], None
        return [f"parse raised {type(exc).__name__}: {exc}"], None
    if case.exception:
        return [f"expected the grammar to reject this with {case.exception}, but it parsed"], parsed

    failures = run_invariants(case, parsed)
    for entry in case.asserts:
        if "actual" not in entry or "expected" not in entry:
            raise AssertUnevaluatableError(f"{case.id}: an assert needs both 'actual' and 'expected'")
        actual = normalise(resolve(parsed, entry["actual"]))
        expected = entry["expected"]
        if actual != expected:
            failures.append(f"{entry['actual']}: expected {expected!r}, got {actual!r}")
    parsed._fetch_instances()
    parsed._check()
    output_stream = KaitaiStream(io.BytesIO(bytes(len(case.data))))
    parsed._write(output_stream)
    written = output_stream.to_byte_array()
    if written != case.data:
        failures.append("generated writer did not reproduce the fixture byte-for-byte")
    return failures, parsed


REQUIREMENTS = ("distinct_at_least", "count_at_least")
DIFFERENTIALS = ("differs_at", "differs_within", "equal_at")


def check_schemes_are_separated(cases: list[Case]) -> None:
    """Refuse a corpus that cannot tell the two checksum schemes apart.

    Asserting a frame matches XOR proves nothing about sum-8 unless the corpus holds a
    frame where the two disagree, and on short or sparse payloads they often agree. So
    each family must carry at least one separating fixture, otherwise "this family is
    XOR" is a label that was never tested.
    """
    separated: dict[str, int] = {}
    for case in cases:
        family = checksum_family(case.data)
        if not family:
            continue
        name, index, scheme = family
        rival = sum_checksum if scheme is xor_checksum else xor_checksum
        payload = case.data[:index]
        separated.setdefault(name, 0)
        if scheme(payload) != rival(payload):
            separated[name] += 1
    barren = sorted(name for name, count in separated.items() if count == 0)
    if barren:
        raise AssertUnevaluatableError(
            f"no fixture separates {'/'.join(barren)} from the rival scheme, so the claim is untested"
        )


def diff_offsets(left: bytes, right: bytes) -> set[int]:
    """Offsets at which two frames differ, counting the tail when lengths differ."""
    shared = min(len(left), len(right))
    return {i for i in range(shared) if left[i] != right[i]} | set(range(shared, max(len(left), len(right))))


def run_differential(entry: dict[str, Any], requirement: str, data_by_id: dict[str, bytes]) -> str | None:
    """Check a claim about how two fixtures differ, which no per-fixture assert can make.

    "Exactly one byte moved, and it is brightness_order" is a single claim in two halves.
    The value half is an ordinary assert; the "and nothing else moved" half is what pins
    the field to that byte, and it is the half a naive port silently drops. workshop_body
    alone rests on ten of these, under a heading calling them the isolation proofs behind
    its confirmed fields.
    """
    pair = entry.get("between")
    if not isinstance(pair, list) or len(pair) != 2:
        raise AssertUnevaluatableError(f"differential {entry.get('id')!r}: needs 'between: [case_a, case_b]'")
    for case_id in pair:
        if case_id not in data_by_id:
            raise AssertUnevaluatableError(f"differential {entry['id']!r}: no case {case_id!r}")
    moved = diff_offsets(data_by_id[pair[0]], data_by_id[pair[1]])
    claimed = set(entry[requirement])
    if requirement != "equal_at" and not moved:
        raise AssertUnevaluatableError(
            f"differential {entry['id']!r}: {pair[0]} and {pair[1]} are byte-identical, "
            "so the claim is satisfied by having nothing to say"
        )
    if requirement == "differs_at" and moved != claimed:
        return f"differs at {sorted(moved)}, claimed exactly {sorted(claimed)}"
    if requirement == "differs_within" and not moved <= claimed:
        return f"differs at {sorted(moved)}, which escapes {sorted(claimed)}"
    if requirement == "equal_at" and moved & claimed:
        return f"differs at {sorted(moved & claimed)}, which must be identical"
    return None


def _capture_position(case: Case) -> tuple[int, int]:
    start = case.provenance.get("source_start_index")
    end = case.provenance.get("source_end_index")
    if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end < start:
        raise AssertUnevaluatableError(
            f"{case.id}: capture sequence needs non-negative source_start_index/source_end_index"
        )
    return start, end


def _capture_write_position(case: Case) -> tuple[int, int]:
    start = case.provenance.get("source_write_start_index")
    end = case.provenance.get("source_write_end_index")
    if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end < start:
        raise AssertUnevaluatableError(
            f"{case.id}: adjacent writes need non-negative source_write_start_index/source_write_end_index"
        )
    return start, end


def run_capture_sequence(entry: dict[str, Any], cases_by_id: dict[str, Case]) -> str | None:
    sequence = entry.get("capture_sequence")
    if not isinstance(sequence, list) or len(sequence) < 2 or not all(isinstance(case_id, str) for case_id in sequence):
        raise AssertUnevaluatableError(f"capture sequence {entry.get('id')!r}: needs at least two case ids")
    if len(set(sequence)) != len(sequence):
        raise AssertUnevaluatableError(f"capture sequence {entry['id']!r}: case ids must be unique")
    cases = []
    for case_id in sequence:
        if case_id not in cases_by_id:
            raise AssertUnevaluatableError(f"capture sequence {entry['id']!r}: no case {case_id!r}")
        cases.append(cases_by_id[case_id])

    provenance_keys = ("source", "source_sha256", "actions_sha256", "prediction_sha256")
    for case in cases:
        for key in provenance_keys:
            value = case.provenance.get(key)
            if not isinstance(value, str) or not value:
                raise AssertUnevaluatableError(f"{case.id}: capture sequence provenance is missing {key!r}")
            if key.endswith("_sha256") and (len(value) != 64 or any(char not in "0123456789abcdef" for char in value)):
                raise AssertUnevaluatableError(f"{case.id}: capture sequence provenance has invalid {key!r}")
        if not isinstance(case.provenance.get("action"), str) or not case.provenance["action"]:
            raise AssertUnevaluatableError(f"{case.id}: capture sequence provenance is missing 'action'")
    for key in provenance_keys:
        values = {case.provenance[key] for case in cases}
        if len(values) != 1:
            return f"{key} differs across {sequence}"
    same_action = entry.get("same_action", False)
    if not isinstance(same_action, bool):
        raise AssertUnevaluatableError(f"capture sequence {entry['id']!r}: same_action must be a boolean")
    if same_action and len({case.provenance["action"] for case in cases}) != 1:
        return f"actions differ across {sequence}"

    positions = [_capture_position(case) for case in cases]
    for left, right in zip(positions, positions[1:], strict=False):
        if left[1] >= right[0]:
            return f"capture positions are not strictly ordered: {positions}"
    adjacent_writes = entry.get("adjacent_writes", False)
    if not isinstance(adjacent_writes, bool):
        raise AssertUnevaluatableError(f"capture sequence {entry['id']!r}: adjacent_writes must be a boolean")
    if adjacent_writes:
        write_positions = [_capture_write_position(case) for case in cases]
        for left, right in zip(write_positions, write_positions[1:], strict=False):
            if left[1] + 1 != right[0]:
                return f"capture writes are not adjacent: {write_positions}"
    return None


def run_equal_values(entry: dict[str, Any], parsed_by_id: dict[str, Any]) -> tuple[str | None, Any]:
    selections = entry.get("equal_values")
    if not isinstance(selections, list) or len(selections) < 2:
        raise AssertUnevaluatableError(f"equal values {entry.get('id')!r}: needs at least two selections")
    values = []
    for selection in selections:
        if (
            not isinstance(selection, dict)
            or not isinstance(selection.get("case"), str)
            or not isinstance(selection.get("actual"), str)
        ):
            raise AssertUnevaluatableError(f"equal values {entry['id']!r}: each selection needs case and actual")
        case_id = selection["case"]
        if case_id not in parsed_by_id or parsed_by_id[case_id] is None:
            raise AssertUnevaluatableError(f"equal values {entry['id']!r}: no parsed case {case_id!r}")
        values.append(normalise(resolve(parsed_by_id[case_id], selection["actual"])))
    if len(set(values)) != 1:
        return f"values differ: {values}", values
    return None, values[0]


def load_aggregates(path: Path = AGGREGATES_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    doc = yaml.safe_load(path.read_text()) or []
    if not isinstance(doc, list):
        raise AssertUnevaluatableError(f"{path.name}: document root must be a list")
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, entry in enumerate(doc):
        if not isinstance(entry, dict):
            raise AssertUnevaluatableError(f"{path.name}[{index}]: must be a mapping")
        aggregate_id = entry.get("id")
        if not isinstance(aggregate_id, str) or not aggregate_id:
            raise AssertUnevaluatableError(f"{path.name}[{index}]: needs a non-empty string id")
        if aggregate_id in seen:
            raise AssertUnevaluatableError(f"{path.name}[{index}]: duplicate id {aggregate_id!r}")
        seen.add(aggregate_id)
        entries.append(entry)
    return entries


def load_protocol_blockers(path: Path = PROTOCOL_BLOCKERS_PATH) -> dict[str, Any]:
    doc = yaml.safe_load(path.read_text())
    if not isinstance(doc, dict):
        raise AssertUnevaluatableError(f"{path.name}: document root must be a mapping")
    return doc


def validate_protocol_blockers(
    doc: dict[str, Any],
    aggregates: list[dict[str, Any]],
    path: Path = PROTOCOL_BLOCKERS_PATH,
) -> None:
    if doc.get("schema_version") != 1:
        raise AssertUnevaluatableError(f"{path.name}: schema_version must be 1")
    blockers = doc.get("blockers")
    if not isinstance(blockers, list):
        raise AssertUnevaluatableError(f"{path.name}: blockers must be a list")

    aggregate_ids = {entry["id"] for entry in aggregates}
    seen_issues: set[int] = set()
    for index, blocker in enumerate(blockers):
        label = f"{path.name}: blockers[{index}]"
        if not isinstance(blocker, dict):
            raise AssertUnevaluatableError(f"{label}: must be a mapping")
        issue = blocker.get("issue")
        if not isinstance(issue, int) or isinstance(issue, bool) or issue <= 0:
            raise AssertUnevaluatableError(f"{label}: issue must be a positive integer")
        if issue in seen_issues:
            raise AssertUnevaluatableError(f"{label}: duplicate issue {issue}")
        seen_issues.add(issue)

        status = blocker.get("status")
        if status not in PROTOCOL_BLOCKER_STATUSES:
            raise AssertUnevaluatableError(
                f"{label}: status {status!r} is not one of {sorted(PROTOCOL_BLOCKER_STATUSES)}"
            )
        summary = blocker.get("summary")
        if not isinstance(summary, str) or not summary:
            raise AssertUnevaluatableError(f"{label}: summary must be a non-empty string")
        if status == "resolved" and (not isinstance(blocker.get("resolution"), str) or not blocker["resolution"]):
            raise AssertUnevaluatableError(f"{label}: resolved blockers need a non-empty resolution")

        affected = blocker.get("affected_capabilities")
        if not isinstance(affected, list) or not affected:
            raise AssertUnevaluatableError(f"{label}: affected_capabilities must be a non-empty list")
        affected_keys: list[tuple[str, str]] = []
        for affected_index, capability in enumerate(affected):
            affected_label = f"{label}: affected_capabilities[{affected_index}]"
            if not isinstance(capability, dict):
                raise AssertUnevaluatableError(f"{affected_label}: must be a mapping")
            model = capability.get("model")
            capability_name = capability.get("capability")
            if not isinstance(model, str) or not model or not isinstance(capability_name, str) or not capability_name:
                raise AssertUnevaluatableError(f"{affected_label}: model and capability must be non-empty strings")
            affected_keys.append((model, capability_name))
        if len(affected_keys) != len(set(affected_keys)):
            raise AssertUnevaluatableError(f"{label}: affected_capabilities must not contain duplicates")

        evidence = blocker.get("evidence_aggregates")
        if (
            not isinstance(evidence, list)
            or not evidence
            or not all(isinstance(value, str) and value for value in evidence)
        ):
            raise AssertUnevaluatableError(f"{label}: evidence_aggregates must be a non-empty list of strings")
        if len(evidence) != len(set(evidence)):
            raise AssertUnevaluatableError(f"{label}: evidence_aggregates must not contain duplicates")
        missing = sorted(set(evidence) - aggregate_ids)
        if missing:
            raise AssertUnevaluatableError(f"{label}: unknown evidence aggregate(s): {', '.join(missing)}")

        boundaries = blocker.get("boundaries")
        if (
            not isinstance(boundaries, list)
            or not boundaries
            or not all(isinstance(value, str) and value for value in boundaries)
        ):
            raise AssertUnevaluatableError(f"{label}: boundaries must be a non-empty list of strings")


def check_every_spec_is_exercised(cases: list[Case]) -> None:
    """Refuse a .ksy that no fixture reaches, directly or through an import.

    A spec nothing parses still compiles, still passes evidence_lint, and still reads as
    documentation of the wire, so it is the field-level version of an orphan fixture: a
    layout that has never met a byte, indistinguishable from one proven against hundreds
    of them. That matters most for a model whose discovery run has not happened yet. The
    tempting move is to write its spec from an existing encoder or another model first and
    check captures against it later. This check makes that impossible rather than merely
    discouraged: a new spec cannot be committed until a fixture reads it.

    The closure is transitive on purpose. govee_common is named by no .kst, only by other
    specs' meta.imports, so a direct "some fixture names it" test would fail the one spec
    every other spec depends on.
    """
    named = {module for case in cases for module in case.imports}
    closure = set(named)
    frontier = set(named)
    while frontier:
        following = set()
        for module in frontier:
            spec = HERE / f"{module}.ksy"
            if spec.exists():
                meta = (yaml.safe_load(spec.read_text(encoding="utf-8")) or {}).get("meta") or {}
                following |= set(meta.get("imports") or [])
        frontier = following - closure
        closure |= frontier
    unexercised = sorted(p.name for p in HERE.glob("*.ksy") if p.stem not in closure)
    if unexercised:
        raise AssertUnevaluatableError(
            f"{len(unexercised)} spec(s) that no fixture exercises: {', '.join(unexercised)}. "
            "Add a .kst case reading real captured bytes, or delete the spec."
        )


def check_every_fixture_is_claimed(cases: list[Case]) -> None:
    """Refuse a fixture in src/ that no case reads.

    Bytes sitting in src/ with no .kst reading them are indistinguishable from bytes that
    are thoroughly checked, and that is not hypothetical: the command_write pilot carried
    20 fixtures against 10 cases, so deleting its harness would have dropped ten fixtures'
    worth of assertions in silence. Same reasoning as an aggregate pattern matching no
    case, so it gets the same treatment.
    """
    claimed = {case.source.resolve() for case in cases}
    present = {path.resolve() for path in (HERE / "src").glob("*.bin")}
    orphans = sorted(path.name for path in present - claimed)
    if orphans:
        raise AssertUnevaluatableError(f"{len(orphans)} fixture(s) in src/ that no .kst reads: {', '.join(orphans)}")


def run_aggregates(
    entries: list[dict[str, Any]],
    cases: list[Case],
    parsed_by_id: dict[str, Any],
    data_by_id: dict[str, bytes],
) -> int:
    """Check claims that span fixtures, which .kst asserts cannot express.

    A per-fixture assert cannot say "palette_count takes eight different values across the
    corpus", yet that is the whole reason the scene_type1 falsification corpus exists: a
    constant cannot take eight values, so the rival fixed-selector reading dies on it.
    Nor can it say "and no other byte moved", which is the half of every isolation proof
    that pins a field to its offset. Migrating either to per-fixture asserts would leave
    every row green while the claim quietly disappeared. The vocabulary is deliberately
    tiny and anything outside it is a hard error.
    """
    failed = 0
    cases_by_id = {case.id: case for case in cases}
    for entry in entries:
        if "capture_sequence" in entry:
            problem = run_capture_sequence(entry, cases_by_id)
            if problem:
                failed += 1
                print(f"FAIL {entry['id']}")
                print(f"       {problem}")
            else:
                print(f"PASS {entry['id']:38s} capture sequence")
            continue
        if "equal_values" in entry:
            problem, value = run_equal_values(entry, parsed_by_id)
            if problem:
                failed += 1
                print(f"FAIL {entry['id']}")
                print(f"       {problem}")
            else:
                print(f"PASS {entry['id']:38s} equal value {value!r}")
            continue
        differential = next((key for key in DIFFERENTIALS if key in entry), None)
        if differential:
            problem = run_differential(entry, differential, data_by_id)
            if problem:
                failed += 1
                print(f"FAIL {entry['id']}")
                print(f"       {problem}")
            else:
                print(f"PASS {entry['id']:38s} {differential} {sorted(entry[differential])}")
            continue
        requirement = next((key for key in REQUIREMENTS if key in entry), None)
        if requirement is None:
            raise AssertUnevaluatableError(
                f"aggregate {entry.get('id')!r}: none of {REQUIREMENTS + DIFFERENTIALS} given"
            )
        # A THRESHOLD OF ONE CANNOT FAIL, so it is rejected rather than run. Any aggregate
        # that matches a case at all satisfies it, whatever the bytes hold, which makes it a
        # comment wearing a test's clothes. Two such aggregates existed to assert that a
        # field was CONSTANT, and one of them went on passing after its field was shown to
        # vary under its own slider, which is the exact failure a suite is meant to catch.
        # Constancy is a differential claim: use equal_at between two cases that differ
        # elsewhere, which fails the moment the field moves.
        if entry[requirement] < 2:
            raise AssertUnevaluatableError(
                f"aggregate {entry['id']!r}: {requirement} {entry[requirement]} cannot fail. "
                f"To assert a field is constant, use equal_at between two differing cases."
            )
        matched = [obj for case_id, obj in parsed_by_id.items() if fnmatch(case_id, entry["cases"]) and obj]
        if not matched:
            raise AssertUnevaluatableError(f"aggregate {entry['id']!r}: pattern {entry['cases']!r} matched no case")
        values = [normalise(resolve(obj, entry["collect"])) for obj in matched]
        seen = len(set(values)) if requirement == "distinct_at_least" else len(values)
        if seen < entry[requirement]:
            failed += 1
            print(f"FAIL {entry['id']}")
            print(f"       {requirement} {entry[requirement]}, got {seen} from {sorted(set(values))}")
        else:
            print(f"PASS {entry['id']:38s} {requirement} {entry[requirement]}, got {seen}")
    return failed


def check_parsers_are_available() -> None:
    """Require the freshly generated parser directory supplied by check-kaitai.sh."""
    if GENERATED_DIR is None:
        raise AssertUnevaluatableError("KAITAI_GENERATED_DIR is not set; run bash scripts/check-kaitai.sh")
    missing = [spec.stem for spec in sorted(HERE.glob("*.ksy")) if not (GENERATED_DIR / f"{spec.stem}.py").exists()]
    if missing:
        raise AssertUnevaluatableError(f"generated parser directory is missing: {', '.join(missing)}")


def main() -> int:
    check_parsers_are_available()
    aggregates = load_aggregates()
    validate_protocol_blockers(load_protocol_blockers(), aggregates)
    specs = sorted((HERE / "spec").glob("*.kst"))
    if not specs:
        print("no .kst fixtures found under spec/", file=sys.stderr)
        return 1
    failed = 0
    parsed_by_id: dict[str, Any] = {}
    cases = [load_case(path) for path in specs]
    check_every_fixture_is_claimed(cases)
    check_every_spec_is_exercised(cases)
    check_schemes_are_separated(cases)
    for case in cases:
        problems, parsed = run_case(case)
        parsed_by_id[case.id] = parsed
        if problems:
            failed += 1
            print(f"FAIL {case.id}")
            for problem in problems:
                print(f"       {problem}")
        else:
            checks = len(case.asserts) + (1 if case.exception else 2)
            print(f"PASS {case.id:38s} {checks} check(s)")
    failed += run_aggregates(aggregates, cases, parsed_by_id, {case.id: case.data for case in cases})
    print(f"\n{len(specs)} fixture(s), {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
