"""Stop 37: the grading sheet's merging and the readings from your grades."""

from __future__ import annotations

from typing import Any

from scripts.software_review import compare, lettered, score


def g(correct: str, answers: str = "yes", reads_well: str = "yes") -> dict[str, str]:
    return {"correct": correct, "answers": answers, "reads_well": reads_well}


def test_lettered_merges_identical_texts_and_drops_empty_ones() -> None:
    out = lettered([("Same.", {"arm": "rejected"}), ("", {"arm": "4B"}), ("Same.", {"arm": "v2"})])
    assert out == [("Same.", [{"arm": "rejected"}, {"arm": "v2"}])]


def test_score_reads_s1_to_s3() -> None:
    key: list[dict[str, Any]] = [
        {
            "item": "A01A",
            "part": "A",
            "id": "q1",
            "sources": [{"arm": "rejected", "verdict": "ROLLBACK"}],
        },
        {"item": "A01B", "part": "A", "id": "q1", "sources": [{"arm": "4B", "verdict": "EMIT"}]},
        {"item": "A01C", "part": "A", "id": "q1", "sources": [{"arm": "v2", "verdict": "EMIT"}]},
        {
            "item": "A02A",
            "part": "A",
            "id": "q2",
            "sources": [{"arm": "rejected", "verdict": "ROLLBACK"}],
        },
        {"item": "A02B", "part": "A", "id": "q2", "sources": [{"arm": "v2", "verdict": "EMIT"}]},
        {"item": None, "part": "A", "id": "q2", "empty": ["4B"]},
        {"item": "B01A", "part": "B", "id": "q1", "sources": [{"arm": "plain"}]},
        {"item": "B01B", "part": "B", "id": "q1", "sources": [{"arm": "4B"}, {"arm": "v2"}]},
    ]
    grades = {
        "A01A": g("no"),
        "A01B": g("yes", reads_well="no"),
        "A01C": g("yes"),
        "A02A": g("yes"),
        "A02B": g("no"),
        "B01A": g("no", reads_well="n/a"),
        "B01B": g("yes", reads_well="n/a"),
    }
    out = score(key, grades)
    assert out["S1_rejections_real"]["wrong"] == 1
    assert not out["S1_rejections_real"]["readable"]
    s2 = out["S2_good_retry_v2_vs_4B"]
    assert (s2["a"], s2["b"]) == (1, 0)
    assert out["part_a"]["4B"]["no_text"] == 1
    assert out["part_a"]["v2"]["accepted_not_correct"] == 1
    assert out["part_b"]["plain"]["good"] == 0
    assert out["part_b"]["v2"]["good"] == 1
    assert out["S3_good_answer_vs_plain_holm"]["4B_vs_plain"]["only_a"] == 1


def test_compare_gives_kappa_per_column() -> None:
    mine = {"x": g("yes"), "y": g("no"), "z": g("yes", reads_well="n/a")}
    other = {"x": g("yes"), "y": g("no"), "z": g("no", reads_well="n/a")}
    out = compare(mine, other)
    assert out["correct"]["pairs"] == 3
    assert out["reads_well"]["pairs"] == 2
    assert out["answers"]["kappa"] is None  # all "yes": kappa undefined
