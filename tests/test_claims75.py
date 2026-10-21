"""Stop 75: the regression gate's comparison and the shared pairs (no corpus, no answers)."""

from __future__ import annotations

from typing import Any

import pytest

from legal_rag_verifier.verifier import Reason, Verdict
from scripts import claims75


def record(field: str, sha: str, claims: list[list[Any]], set_: str = "dev") -> dict[str, Any]:
    return {"set": set_, "id": "vdev-0001", "field": field, "sha": sha, "claims": claims}


def test_identical_snapshots_change_nothing() -> None:
    snap = [record("sentence", "a", [["MONEY", "GBP:68400", 10, 17]]), record("query", "b", [])]
    out = claims75.compare(snap, snap)
    assert out["changed_texts"] == 0
    assert out["sets"]["dev"] == {
        "tier": 1,
        "texts": 2,
        "claims_before": 1,
        "claims_after": 1,
        "changed": 0,
    }


def test_a_changed_claim_is_listed_with_both_readings() -> None:
    before = [record("premise.passage0", "a", [["NUMBER", "1", 0, 1], ["NUMBER", "3", 2, 3]])]
    after = [record("premise.passage0", "a", [["NUMBER", "1.3", 0, 3]])]
    out = claims75.compare(before, after)
    assert out["changed_texts"] == 1
    (changed,) = out["changed"]
    assert changed["field"] == "premise.passage0"
    assert changed["before"] == before[0]["claims"]
    assert changed["after"] == after[0]["claims"]
    assert out["sets"]["dev"]["claims_before"] == 2
    assert out["sets"]["dev"]["claims_after"] == 1


def test_snapshots_of_different_texts_are_refused() -> None:
    with pytest.raises(ValueError, match="differ"):
        claims75.compare([record("sentence", "a", [])], [record("sentence", "b", [])])
    with pytest.raises(ValueError, match="different texts"):
        claims75.compare([record("sentence", "a", [])], [record("query", "a", [])])


def test_pairs_are_well_formed() -> None:
    ids = [p.id for p in claims75.PAIRS]
    assert len(ids) == len(set(ids)) == 31
    for pair in claims75.PAIRS:
        assert Verdict[pair.verdict] in {Verdict.EMIT, Verdict.ROLLBACK}
        assert Reason[pair.reason] in {Reason.GROUNDED, Reason.UNGROUNDED_FIGURE}
    assert sum(p.verdict == "ROLLBACK" for p in claims75.PAIRS) == 3
