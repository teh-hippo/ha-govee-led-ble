from __future__ import annotations

import copy

import pytest

from tools.ble.kaitai import kst_runner


@pytest.fixture
def aggregates():
    return kst_runner.load_aggregates()


@pytest.fixture
def blockers():
    return kst_runner.load_protocol_blockers()


def test_committed_protocol_blockers_are_valid(blockers, aggregates):
    kst_runner.validate_protocol_blockers(blockers, aggregates)


def test_protocol_blockers_reject_duplicate_issues(blockers, aggregates):
    invalid = copy.deepcopy(blockers)
    invalid["blockers"].append(copy.deepcopy(invalid["blockers"][0]))

    with pytest.raises(kst_runner.AssertUnevaluatableError, match="duplicate issue"):
        kst_runner.validate_protocol_blockers(invalid, aggregates)


def test_protocol_blockers_reject_unknown_aggregate(blockers, aggregates):
    invalid = copy.deepcopy(blockers)
    invalid["blockers"][0]["evidence_aggregates"].append("missing_aggregate")

    with pytest.raises(kst_runner.AssertUnevaluatableError, match="unknown evidence aggregate"):
        kst_runner.validate_protocol_blockers(invalid, aggregates)


def test_protocol_blockers_reject_duplicate_affected_capability(blockers, aggregates):
    invalid = copy.deepcopy(blockers)
    invalid["blockers"][0]["affected_capabilities"].append(
        copy.deepcopy(invalid["blockers"][0]["affected_capabilities"][0])
    )

    with pytest.raises(kst_runner.AssertUnevaluatableError, match="affected_capabilities must not contain duplicates"):
        kst_runner.validate_protocol_blockers(invalid, aggregates)


def test_resolved_protocol_blockers_require_a_resolution(blockers, aggregates):
    invalid = copy.deepcopy(blockers)
    del invalid["blockers"][0]["resolution"]

    with pytest.raises(kst_runner.AssertUnevaluatableError, match="resolved blockers need"):
        kst_runner.validate_protocol_blockers(invalid, aggregates)
