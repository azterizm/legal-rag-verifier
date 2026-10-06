"""The real NLI head (needs the [nli] extra and cached weights; skipped otherwise)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from legal_rag_verifier.nli import SentenceNLIVerifier
from legal_rag_verifier.premise import Premise
from legal_rag_verifier.verifier import Reason, Verdict, Verifier

MODEL = "cross-encoder/nli-deberta-v3-small"


def _cached(model: str) -> bool:
    if importlib.util.find_spec("torch") is None:
        return False
    snapshots = Path.home() / ".cache/huggingface/hub" / f"models--{model.replace('/', '--')}"
    return any(snapshots.glob("snapshots/*/model.safetensors"))


pytestmark = [
    pytest.mark.torch,
    pytest.mark.model,
    pytest.mark.skipif(not _cached(MODEL), reason=f"{MODEL} weights or torch not available"),
]


@pytest.fixture(scope="module")
def scorer() -> SentenceNLIVerifier:
    return SentenceNLIVerifier(MODEL, device="cpu")


def test_labels_and_revision(scorer: SentenceNLIVerifier) -> None:
    assert (scorer._entailment, scorer._neutral, scorer._contradiction) == (1, 2, 0)
    assert scorer.model_id.startswith(MODEL + "@")
    assert not scorer.model_id.endswith("@unknown")


def test_one_result_per_premise(scorer: SentenceNLIVerifier) -> None:
    probs = scorer.score(
        ["The employer shall give reasons.", "It rained."], "Reasons must be given."
    )
    assert len(probs) == 2
    for p in probs:
        assert abs(p.entailment + p.neutral + p.contradiction - 1.0) < 1e-4
    assert probs[0].entailment > probs[1].entailment
    assert scorer.score([], "x") == []


def test_long_premise_is_chunked_within_budget(scorer: SentenceNLIVerifier) -> None:
    long_text = " ".join(f"Rule {i} requires the employer to keep record {i}." for i in range(200))
    chunks = scorer.chunks(long_text)
    assert len(chunks) > 1
    assert all(scorer._length(c) <= scorer._premise_budget for c in chunks)
    assert "".join(chunks).replace(" ", "") == long_text.replace(" ", "")
    one_word_run = "word " * 1000
    assert all(scorer._length(c) <= scorer._premise_budget for c in scorer.chunks(one_word_run))
    assert len(scorer.score([long_text], "The employer keeps record 150.")) == 1


def test_04_examples_with_nli(scorer: SentenceNLIVerifier, premise_04: Premise) -> None:
    verifier = Verifier(scorer)
    ok = verifier.check_sentence(
        premise_04, "The statutory cap on the compensatory award is set at £68,400."
    )
    assert ok.verdict is Verdict.EMIT
    assert ok.nli is not None
    assert ok.nli.model_id == scorer.model_id
    bad = verifier.check_sentence(premise_04, "The cap is £85,000.")
    assert bad.reasons == (Reason.UNGROUNDED_FIGURE,)
    assert bad.nli is None  # claim failure short-circuits NLI
