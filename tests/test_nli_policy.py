"""NLI policy branches with a scripted scorer (no torch): thresholds, neutral policy, ranking."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from legal_rag_verifier.corpus import instrument_coordinate, instrument_path, load_provision
from legal_rag_verifier.premise import Premise
from legal_rag_verifier.verifier import (
    NLIProbs,
    Reason,
    SentenceVerdict,
    Verdict,
    Verifier,
    VerifierConfig,
)

PREMISE = Premise.from_text(
    "The employer shall give written reasons for dismissal.\n\n"
    "The tribunal may order reinstatement.\n\n"
    "A complaint must be presented within three months."
)


class Scripted:
    model_id = "scripted"

    def __init__(self, probs: Sequence[tuple[float, float, float]]) -> None:
        self.probs = [NLIProbs(*p) for p in probs]
        self.calls = 0

    def score(self, premises: Sequence[str], hypothesis: str) -> list[NLIProbs]:
        self.calls += 1
        assert len(premises) == len(self.probs)
        assert hypothesis
        return self.probs


def run(
    probs: Sequence[tuple[float, float, float]], sentence: str, **config: Any
) -> SentenceVerdict:
    verifier = Verifier(Scripted(probs), VerifierConfig(**config))
    return verifier.check_sentence(PREMISE, sentence)


def test_entailed_claim_emits_and_records_best_window() -> None:
    v = run([(0.1, 0.8, 0.1), (0.95, 0.04, 0.01), (0.2, 0.7, 0.1)], "The tribunal may order it.")
    assert v.verdict is Verdict.EMIT
    assert v.nli is not None
    assert v.nli.window == 1
    assert v.aligned[0] == 1


def test_contradiction_rolls_back_with_ban() -> None:
    v = run([(0.1, 0.3, 0.6), (0.1, 0.8, 0.1), (0.1, 0.8, 0.1)], "The employer gives reasons.")
    assert v.reasons == (Reason.NLI_CONTRADICTION,)
    assert v.repair is not None
    assert v.repair.mode == "ban"


def test_unentailed_claim_rolls_back() -> None:
    v = run([(0.5, 0.45, 0.05)] * 3, "The employer must give reasons.")
    assert v.reasons == (Reason.NLI_NOT_ENTAILED,)


@pytest.mark.parametrize(
    ("policy", "verdict"), [("connective", Verdict.EMIT), ("strict", Verdict.ROLLBACK)]
)
def test_neutral_policy(policy: str, verdict: Verdict) -> None:
    v = run([(0.2, 0.75, 0.05)] * 3, "This is how it works.", neutral_policy=policy)
    assert v.verdict is verdict


def test_claim_failure_skips_nli() -> None:
    scorer = Scripted([(0.9, 0.05, 0.05)] * 3)
    v = Verifier(scorer).check_sentence(PREMISE, "A complaint must be made within six months.")
    assert v.reasons == (Reason.UNGROUNDED_FIGURE,)
    assert scorer.calls == 0


def test_instrument_coordinate() -> None:
    assert instrument_coordinate("uk/ukpga/1996/18/s124/1ZA") == "uk/ukpga/1996/18"
    assert instrument_coordinate("uk/ukpga/Vict/24-25/100/s20") == "uk/ukpga/Vict/24-25/100"


def test_instrument_path() -> None:
    assert instrument_path(Path("data"), "uk/ukpga/1996/18/s124") == Path(
        "data/uk/ukpga/1996/uk_ukpga_1996_18.jsonl"
    )


@pytest.mark.full_data
def test_load_provision_from_local_corpus() -> None:
    data = Path(__file__).parent.parent / "data"
    if not instrument_path(data, "uk/ukpga/1996/18").exists():
        pytest.skip("local corpus not present")
    rows = load_provision(data, "uk/ukpga/1996/18/s124")
    assert rows[0]["record_type"] == "instrument"
    assert any(r["coordinate"] == "uk/ukpga/1996/18/s124/1ZA/a" for r in rows)
    with pytest.raises(KeyError):
        load_provision(data, "uk/ukpga/1996/18/s9999")
    regnal = load_provision(data, "uk/ukpga/Vict/24-25/100/s20")
    assert regnal[0]["coordinate"] == "uk/ukpga/Vict/24-25/100"
    with pytest.raises(FileNotFoundError):
        instrument_path(data, "uk/ukpga/Vict/99-99/1/s1")


class Recording:
    model_id = "scripted"

    def __init__(self) -> None:
        self.hypotheses: list[str] = []

    def score(self, premises: Sequence[str], hypothesis: str) -> list[NLIProbs]:
        self.hypotheses.append(hypothesis)
        return [NLIProbs(0.05, 0.9, 0.05) for _ in premises]


def test_leading_yes_or_no_is_not_judged() -> None:
    scorer = Recording()
    Verifier(scorer).check_sentence(PREMISE, "No, the tribunal may order reinstatement.")
    Verifier(scorer).check_sentence(PREMISE, "Yes. The employer shall give written reasons.")
    Verifier(scorer).check_sentence(PREMISE, "Nobody may order it.")
    assert scorer.hypotheses == [
        "the tribunal may order reinstatement.",
        "The employer shall give written reasons.",
        "Nobody may order it.",
    ]


FIGURES = Premise.from_text(
    "The landlord is to give or refuse consent on or before the 28th day after the request.\n\n"
    "A person convicted is liable to a fine under section 5 of the Housing Act 1988."
)
ENTAILED = [(0.95, 0.04, 0.01), (0.1, 0.8, 0.1)]
NEUTRAL = [(0.2, 0.7, 0.1), (0.1, 0.8, 0.1)]
SENTENCE = "The landlord has 21 days to give or refuse consent."


def figures(probs: Sequence[tuple[float, float, float]], sentence: str, **config: Any) -> Any:
    return Verifier(Scripted(probs), VerifierConfig(**config)).check_sentence(FIGURES, sentence)


def test_an_ungrounded_figure_rolls_back_by_default_without_asking_the_judge() -> None:
    v = figures(ENTAILED, SENTENCE)
    assert v.verdict is Verdict.ROLLBACK
    assert v.reasons == (Reason.UNGROUNDED_FIGURE,)
    assert v.nli is None


def test_with_judge_an_ungrounded_figure_is_emitted_only_if_entailed() -> None:
    v = figures(ENTAILED, SENTENCE, ungrounded_figure="judge")
    assert v.verdict is Verdict.EMIT
    assert [c.reason for c in v.claims] == [Reason.UNGROUNDED_FIGURE]
    assert v.details == ("figure sent to the judge: 21 days",)
    v = figures(NEUTRAL, SENTENCE, ungrounded_figure="judge")
    assert v.verdict is Verdict.ROLLBACK
    assert v.reasons == (Reason.NLI_NOT_ENTAILED,)


def test_with_judge_a_grounded_claim_does_not_carry_an_ungrounded_figure() -> None:
    sentence = "Under section 5 of the Housing Act 1988 the landlord has 21 days."
    v = figures(NEUTRAL, sentence, ungrounded_figure="judge")
    assert v.verdict is Verdict.ROLLBACK
    assert Reason.NLI_NOT_ENTAILED in v.reasons


def test_with_judge_a_missing_citation_still_rolls_back_before_the_judge() -> None:
    sentence = "Under section 99 of the Housing Act 1988 the landlord has 21 days."
    v = figures(ENTAILED, sentence, ungrounded_figure="judge")
    assert v.verdict is Verdict.ROLLBACK
    assert Reason.UNGROUNDED_CITATION in v.reasons
    assert v.nli is None


def test_judge_without_a_scorer_behaves_as_rollback_and_the_setting_is_in_the_trace() -> None:
    config = VerifierConfig(ungrounded_figure="judge")
    v = Verifier(None, config).check_sentence(FIGURES, SENTENCE)
    assert v.reasons == (Reason.UNGROUNDED_FIGURE,)
    assert config.to_dict()["ungrounded_figure"] == "judge"
    assert VerifierConfig().to_dict()["ungrounded_figure"] == "rollback"
