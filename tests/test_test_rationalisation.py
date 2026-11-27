import json
from pathlib import Path

import pytest
from coverage import CoverageData
from coverage.exceptions import DataError

from tools.test_rationalisation import _context_arcs, _node_inventory, _suite_inventory, _union_arcs


def test_node_inventory_preserves_parameter_ids(tmp_path: Path) -> None:
    nodes = tmp_path / "nodes.txt"
    nodes.write_text(
        "tests/test_one.py::test_value[one]\ntests/test_one.py::test_value[two]\ntests/test_two.py::test_other\n"
    )

    collected, modules = _node_inventory(nodes)

    assert collected == [
        "tests/test_one.py::test_value[one]",
        "tests/test_one.py::test_value[two]",
        "tests/test_two.py::test_other",
    ]
    assert modules == {"tests/test_one.py": 2, "tests/test_two.py": 1}


def test_context_arcs_keep_pytest_case_partitioned(tmp_path: Path) -> None:
    source = Path(__file__).resolve()
    database = tmp_path / "coverage.sqlite"
    data = CoverageData(basename=str(database))
    data.set_context("tests/test_one.py::test_value[one]|run")
    data.add_arcs({str(source): {(10, 11), (11, -1)}})
    data.set_context("tests/test_one.py::test_value[two]|run")
    data.add_arcs({str(source): {(20, 21)}})
    data.set_context("old-tests/test_one.py::test_value[one]|run")
    data.add_arcs({str(source): {(30, 31)}})
    data.write()

    contexts = _context_arcs(database, "|run")

    relative_source = str(source.relative_to(source.parents[1]))
    assert contexts["tests/test_one.py::test_value[one]"][relative_source] == [[10, 11], [11, -1]]
    assert contexts["tests/test_one.py::test_value[two]"][relative_source] == [[20, 21]]
    assert [30, 31] not in contexts["tests/test_one.py::test_value[one]"][relative_source]


def test_suite_inventory_covers_repository_test_surfaces() -> None:
    inventory = json.loads(json.dumps(_suite_inventory()))

    assert "tests/test_h6102_protocol.py" in inventory["python"]
    assert "frontend/tests/browser/packaged-studio.spec.ts" in inventory["frontend_browser"]
    assert ".github/workflows/validate.yml" in inventory["workflows"]


def test_union_arcs_reports_only_selected_contexts() -> None:
    contexts = {
        "selected": {"module.py": [[1, 2], [2, -1]]},
        "excluded": {"module.py": [[2, 3]]},
    }

    assert _union_arcs(contexts, ["selected"]) == {
        ("module.py", 1, 2),
        ("module.py", 2, -1),
    }


def test_context_arcs_reject_line_only_coverage(tmp_path: Path) -> None:
    database = tmp_path / "line-coverage.sqlite"
    data = CoverageData(basename=str(database))
    data.set_context("tests/test_one.py::test_value|run")
    data.add_lines({str(Path(__file__).resolve()): {10, 11}})
    data.write()

    with pytest.raises(ValueError, match="has no branch arcs"):
        _context_arcs(database, "|run")


def test_context_arcs_does_not_modify_unrelated_database(tmp_path: Path) -> None:
    database = tmp_path / "unrelated.sqlite"
    database.write_bytes(b"not coverage data")
    before = database.read_bytes()

    with pytest.raises(DataError, match="file is not a database"):
        _context_arcs(database, "|run")

    assert database.read_bytes() == before
