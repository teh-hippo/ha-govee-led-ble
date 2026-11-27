"""Capture evidence for test-suite rationalisation."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from coverage import CoverageData

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO_ROOT / ".build" / "test-rationalisation"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> str:
    return subprocess.run(  # noqa: S603
        ["/usr/bin/git", *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _node_inventory(path: Path) -> tuple[list[str], dict[str, int]]:
    nodes = [line for line in path.read_text().splitlines() if line.startswith("tests/") and "::" in line]
    modules: Counter[str] = Counter()
    for node in nodes:
        modules[node.split("::", 1)[0]] += 1
    return nodes, dict(sorted(modules.items()))


def _suite_inventory() -> dict[str, list[str]]:
    return {
        "python": sorted(str(path.relative_to(REPO_ROOT)) for path in (REPO_ROOT / "tests").glob("test_*.py")),
        "frontend_unit": sorted(
            str(path.relative_to(REPO_ROOT)) for path in (REPO_ROOT / "frontend" / "tests" / "unit").rglob("*.spec.ts")
        ),
        "frontend_browser": sorted(
            str(path.relative_to(REPO_ROOT))
            for path in (REPO_ROOT / "frontend" / "tests" / "browser").rglob("*.spec.ts")
        ),
        "workflows": sorted(
            str(path.relative_to(REPO_ROOT)) for path in (REPO_ROOT / ".github" / "workflows").glob("*.yml")
        ),
    }


def _context_arcs(path: Path, context_suffix: str) -> dict[str, dict[str, list[list[int]]]]:
    data = CoverageData(basename=str(path), read_only=True)
    data.read()
    if not data.has_arcs():
        raise ValueError(f"Coverage database has no branch arcs: {path}")
    measured_files = sorted(data.measured_files())
    contexts = sorted(context for context in data.measured_contexts() if context.endswith(context_suffix))
    result: dict[str, dict[str, list[list[int]]]] = {}
    for context in contexts:
        data.set_query_context(context)
        files: dict[str, list[list[int]]] = {}
        for filename in measured_files:
            arcs = data.arcs(filename)
            if arcs:
                relative = str(Path(filename).resolve().relative_to(REPO_ROOT))
                files[relative] = [list(arc) for arc in sorted(arcs)]
        result[context.removesuffix(context_suffix)] = files
    return result


def capture(nodes_path: Path, coverage_path: Path, output: Path, *, context_suffix: str = "|run") -> dict[str, Any]:
    nodes, modules = _node_inventory(nodes_path)
    suite_inventory = _suite_inventory()
    coverage = _context_arcs(coverage_path, context_suffix)
    summary = {
        "sha": _git("rev-parse", "HEAD"),
        "dirty": bool(_git("status", "--short")),
        "python": sys.version.split()[0],
        "coverage_core": sys.modules["coverage"].version_info,
        "lock_hashes": {
            str(path.relative_to(REPO_ROOT)): _sha256(path)
            for path in (REPO_ROOT / "uv.lock", REPO_ROOT / "frontend" / "package-lock.json")
        },
        "node_count": len(nodes),
        "module_case_counts": modules,
        "suite_inventory": suite_inventory,
        "coverage_context_count": len(coverage),
        "coverage_context_suffix": context_suffix,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "baseline.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    (output / "node-ids.json").write_text(json.dumps(nodes, indent=2) + "\n")
    (output / "context-arcs.json").write_text(json.dumps(coverage, indent=2, sort_keys=True) + "\n")
    return summary


def _union_arcs(
    contexts: dict[str, dict[str, list[list[int]]]],
    selected: list[str],
) -> set[tuple[str, int, int]]:
    arcs: set[tuple[str, int, int]] = set()
    missing = sorted(set(selected) - contexts.keys())
    if missing:
        raise ValueError(f"Unknown coverage contexts: {', '.join(missing)}")
    for context in selected:
        for filename, file_arcs in contexts[context].items():
            arcs.update((filename, start, end) for start, end in file_arcs)
    return arcs


def compare(
    baseline_path: Path,
    candidate_path: Path,
    baseline_nodes: list[str],
    candidate_nodes: list[str],
    output: Path,
) -> dict[str, Any]:
    baseline = json.loads(baseline_path.read_text())
    candidate = _context_arcs(candidate_path, "|run")
    original = _union_arcs(baseline, baseline_nodes)
    replacement = _union_arcs(candidate, candidate_nodes)
    report = {
        "baseline_nodes": baseline_nodes,
        "candidate_nodes": candidate_nodes,
        "baseline_arc_count": len(original),
        "candidate_arc_count": len(replacement),
        "lost_arcs": [list(arc) for arc in sorted(original - replacement)],
        "gained_arcs": [list(arc) for arc in sorted(replacement - original)],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    capture_parser = commands.add_parser("capture")
    capture_parser.add_argument("--nodes", type=Path, required=True, help="pytest --collect-only output")
    capture_parser.add_argument("--coverage", type=Path, required=True, help="raw CoverageData database")
    capture_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    capture_parser.add_argument("--context-suffix", default="|run")

    compare_parser = commands.add_parser("compare")
    compare_parser.add_argument("--baseline", type=Path, required=True, help="baseline context-arcs JSON")
    compare_parser.add_argument("--candidate", type=Path, required=True, help="candidate CoverageData database")
    compare_parser.add_argument("--baseline-node", action="append", required=True)
    compare_parser.add_argument("--candidate-node", action="append", required=True)
    compare_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT / "acceptance.json")

    args = parser.parse_args()
    if args.command == "capture":
        report = capture(
            args.nodes.resolve(),
            args.coverage.resolve(),
            args.output.resolve(),
            context_suffix=args.context_suffix,
        )
    else:
        report = compare(
            args.baseline.resolve(),
            args.candidate.resolve(),
            args.baseline_node,
            args.candidate_node,
            args.output.resolve(),
        )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report.get("lost_arcs") else 0


if __name__ == "__main__":
    raise SystemExit(main())
