"""Battery scoring logic on synthetic outcomes (the battery itself runs only after label review)."""

from __future__ import annotations

from collections.abc import Sequence

from legal_rag_verifier.verifier import NLIProbs
from scripts.run_battery import CachingScorer, Outcome, summarise


def o(cls: str, verdict: str, expected: str = "EMIT") -> Outcome:
    return Outcome("x", cls, expected, verdict, ())


def test_summary_rates() -> None:
    summary = summarise(
        [
            o("grounded_paraphrase", "EMIT"),
            o("grounded_paraphrase", "EMIT"),
            o("grounded_paraphrase", "EMIT"),
            o("grounded_paraphrase", "ROLLBACK"),
            o("connective", "EMIT"),
            o("wrong_figure", "ROLLBACK", "ROLLBACK"),
            o("wrong_figure", "EMIT", "ROLLBACK"),
            o("modal_shift", "ROLLBACK", "ROLLBACK"),
        ]
    )
    assert summary["classes"]["grounded_paraphrase"] == {
        "n": 4,
        "rolled_back": 1,
        "false_rollback_rate": 0.25,
    }
    assert summary["classes"]["wrong_figure"]["recall"] == 0.5
    head = summary["headline"]
    assert head["grounded_paraphrase_false_rollback_rate"] == 0.25
    assert head["pass_false_rollback_rate"] == 0.2
    assert head["failure_recall"] == round(2 / 3, 4)
    assert head["rollback_precision"] == round(2 / 3, 4)


def test_empty_summary() -> None:
    head = summarise([])["headline"]
    assert head == {
        "grounded_paraphrase_false_rollback_rate": None,
        "pass_false_rollback_rate": None,
        "failure_recall": None,
        "rollback_precision": None,
    }


class Counting:
    model_id = "counting"

    def __init__(self) -> None:
        self.pairs = 0

    def score(self, premises: Sequence[str], hypothesis: str) -> list[NLIProbs]:
        self.pairs += len(premises)
        return [NLIProbs(0.9, 0.05, 0.05) for _ in premises]


def test_caching_scorer_scores_each_pair_once() -> None:
    inner = Counting()
    cached = CachingScorer(inner)
    assert cached.model_id == "counting"
    cached.score(["a", "b"], "h")
    cached.score(["a", "b", "c"], "h")
    cached.score(["a"], "other")
    assert inner.pairs == 4
