"""NLI policy branches with a scripted scorer (no torch): thresholds, neutral policy, ranking."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from legal_rag_verifier.corpus import instrument_path, load_provision
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
