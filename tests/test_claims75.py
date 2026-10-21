"""Stop 75: the regression gate's comparison, the shared pairs and the corpus run's counting
(no corpus, no answers)."""

from __future__ import annotations

import subprocess
from pathlib import Path
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


def test_each_new_claim_is_put_under_its_rule() -> None:
    assert claims75.rule_of("MONEY", "279,99 €") == "trailing currency"
    assert claims75.rule_of("MONEY", "1 299 EUR") == "trailing currency"
    assert claims75.rule_of("DURATION", "2024 an") == "French unit"
    assert claims75.rule_of("DATE", "1er mars 2026") == "French date"
    assert claims75.rule_of("NUMBER", "5\u00a0000") == "space groups"
    assert claims75.rule_of("PERCENT", "0,25 %") == "decimal comma"
    assert claims75.rule_of("NUMBER", "12") == "other"


def test_the_guard_forms_are_counted_by_what_follows() -> None:
    text = "2,4,6-trinitrotoluene, 1,3-butadiene, 3,3'-dichlorobenzidine, 279,99 and 1,234"
    assert claims75.guard_forms(text) == {
        "comma and digit": 1,
        "hyphen and letter": 2,
        "prime": 1,
        "decimal": 1,
    }


def test_a_changed_text_lists_its_new_claims_with_the_old_ones_they_cover() -> None:
    text = "Price 279,99 € here."
    before = [("NUMBER", "279", 6, 9), ("NUMBER", "99", 10, 12)]
    after = [("MONEY", "EUR:279.99", 6, 14)]
    source = {"coordinate": "c", "source_url": "u"}
    record = claims75.changed_record(source, "text", text, before, after)
    (added,) = record["added"]
    assert added["rule"] == "trailing currency"
    assert added["excerpt"] == ["Price ", "279,99 €", " here."]
    assert added["before"] == [["NUMBER", "279", 6, 9], ["NUMBER", "99", 10, 12]]


def test_the_sample_is_seeded_and_capped_per_rule() -> None:
    added = {"claim": ["NUMBER", "1.5", 0, 3], "rule": "decimal comma", "excerpt": ["", "1,5", ""]}
    one = {"source_url": "u", "field": "text", "added": [{**added, "before": []}]}
    changed = [{"coordinate": f"c{i}", **one} for i in range(claims75.SAMPLE + 10)]
    first = claims75.sample_items(changed)
    assert first == claims75.sample_items(changed)
    assert len(first) == claims75.SAMPLE
    assert {item["id"] for item in first} == {f"dec-{k:02d}" for k in range(1, claims75.SAMPLE + 1)}
    assert first[0]["excerpt"] == "[1,5]"


def test_the_second_run_keeps_the_first_runs_files_and_draws_a_fresh_sample() -> None:
    first, second = claims75.RUNS["75"], claims75.RUNS["76"]
    assert (first.seed, second.seed) == (75, 76)
    for field in ("snapshot", "gate", "raw", "report", "grades"):
        assert getattr(first, field) != getattr(second, field)
    assert first.report == claims75.CORPUS_REPORT


def test_grades_outside_the_three_names_are_refused(tmp_path: Path) -> None:
    path = tmp_path / "grades.csv"
    path.write_text("id,grade,note\ndec-01,right,\ndec-02,maybe,\n", encoding="utf-8")
    with pytest.raises(ValueError, match="dec-02"):
        claims75.read_grades(path)


def _have_old_blobs() -> bool:
    try:
        for blob in claims75.OLD_BLOBS.values():
            subprocess.run(  # noqa: S603
                ["git", "cat-file", "-e", blob],  # noqa: S607
                cwd=claims75.ROOT,
                check=True,
                capture_output=True,
            )
    except (OSError, subprocess.CalledProcessError):
        return False
    return True


@pytest.mark.skipif(not _have_old_blobs(), reason="needs the v0.2.0 git objects (absent in CI)")
def test_the_old_reader_is_the_0_2_0_reading() -> None:
    old = claims75.old_extractor()
    assert claims75.reading(old("Prix : 279,99 €.")) == [
        ("NUMBER", "279", 7, 10),
        ("NUMBER", "99", 11, 13),
    ]
    assert claims75.reading(old("The cap is £68,400.")) == [("MONEY", "GBP:68400", 11, 18)]
