"""Stop 42: the judge's plumbing (``scripts/auditor_judge.py``), with fake judges only."""

from __future__ import annotations

from typing import Any

import pytest

from legal_rag_verifier.premise import Passage, Premise
from legal_rag_verifier.verifier import NLIProbs
from scripts.auditor_judge import (
    JudgeScorer,
    RecordingScorer,
    appeal,
    ask,
    auc,
    choose,
    one_hot,
    parse_reply,
    prompt_key,
    record,
    replay,
    requests,
)

PREMISE = Premise(
    (
        Passage(
            "The divisor used in calculations is N - ddof. By default ddof is zero.",
            heading="numpy.std, parameter ddof",
        ),
    )
)
TEXTS = [
    {"key": "t1", "id": "x", "query": "", "prefix": "", "sentence": "numpy.std divides by N."},
    {
        "key": "t2",
        "id": "x",
        "query": "",
        "prefix": "",
        "sentence": "By default numpy.std ignores ddof.",
    },
]


def test_labels_map_to_one_hot_probabilities() -> None:
    neutral = NLIProbs(0.0, 1.0, 0.0)
    assert one_hot("supported", 2, 3) == [neutral, NLIProbs(1.0, 0.0, 0.0), neutral]
    assert one_hot("contradicted", 1, 2) == [NLIProbs(0.0, 0.0, 1.0), neutral]
    assert one_hot("not_stated", 1, 2) == [neutral, neutral]
    assert one_hot("error", 0, 1) == [neutral]
    assert one_hot("supported", 9, 2) == [NLIProbs(1.0, 0.0, 0.0)] * 2


def test_replies_are_parsed_and_bad_ones_re_asked() -> None:
    assert parse_reply('```json\n{"label": "Not stated", "passage": "2", "reason": "r"}\n```') == {
        "label": "not_stated",
        "passage": 2,
        "reason": "r",
    }
    with pytest.raises(ValueError, match="label"):
        parse_reply('{"label": "maybe"}')
    replies = iter(["no json", '{"label": "supported", "passage": 1, "reason": "ok"}'])

    def chat(messages: list[dict[str, str]]) -> dict[str, Any]:
        return {"content": next(replies), "ms": 10.0, "tokens": 5}

    out = ask(chat, "user")
    assert (out["label"], out["attempts"], out["ms"], out["tokens"]) == ("supported", 2, 20.0, 10)

    def silent(messages: list[dict[str, str]]) -> dict[str, Any]:
        return {"content": "", "ms": 1.0}

    assert ask(silent, "user")["label"] == "error"


def labels_for(verdict: dict[str, str]) -> dict[str, dict[str, Any]]:
    """A fake judge: the label per text key, keyed by each of its prompts."""
    built = {t["key"]: PREMISE for t in TEXTS}
    recorded = record(TEXTS, built)
    out = {}
    for t, r in zip(TEXTS, recorded, strict=True):
        for sha in requests([r]):
            out[sha] = {"label": verdict[t["key"]], "passage": 1, "reason": ""}
    return out


def test_replace_follows_the_judge() -> None:
    built = {t["key"]: PREMISE for t in TEXTS}
    labels = labels_for({"t1": "supported", "t2": "contradicted"})
    out = replay(TEXTS, built, JudgeScorer("fake", labels))
    assert out["t1"]["verdict"] == "EMIT"
    assert out["t2"] == {"verdict": "ROLLBACK", "reasons": ["NLI_CONTRADICTION"]}


def test_appeal_lifts_only_entailment_rollbacks_the_judge_supports() -> None:
    built = {t["key"]: PREMISE for t in TEXTS}
    recorded = {t["key"]: r for t, r in zip(TEXTS, record(TEXTS, built), strict=True)}
    labels = labels_for({"t1": "supported", "t2": "not_stated"})
    v0 = {
        "t1": {"verdict": "ROLLBACK", "reasons": ["NLI_CONTRADICTION"]},
        "t2": {"verdict": "ROLLBACK", "reasons": ["NLI_NOT_ENTAILED"]},
    }
    out = appeal(v0, recorded, labels)
    assert out["t1"]["verdict"] == "EMIT"
    assert out["t2"]["verdict"] == "ROLLBACK"
    claim = {**v0, "t1": {"verdict": "ROLLBACK", "reasons": ["FIGURE_UNGROUNDED"]}}
    assert appeal(claim, recorded, labels)["t1"]["verdict"] == "ROLLBACK"


def test_the_prompt_carries_the_answer_so_far() -> None:
    scorer = RecordingScorer()
    scorer.score(["a passage"], "It is zero.")
    recorded = [{"calls": [["It is zero.", ["a passage"]]], "prefix": "ddof is a parameter."}]
    ((sha, user),) = requests(recorded).items()
    assert "ddof is a parameter." in user
    assert "[1] a passage" in user
    assert sha == prompt_key(user)


def test_auc_and_the_control_rule() -> None:
    assert auc([0.9, 0.8], [0.1, 0.2]) == 1.0
    assert auc([0.5], [0.5]) == 0.5
    assert auc([], [0.1]) is None
    grid = [
        {
            "entail": 0.7,
            "contradict": 0.4,
            "failure_recall": 0.80,
            "pass_false_rollback_rate": 0.01,
        },
        {
            "entail": 0.5,
            "contradict": 0.7,
            "failure_recall": 0.86,
            "pass_false_rollback_rate": 0.05,
        },
        {
            "entail": 0.6,
            "contradict": 0.4,
            "failure_recall": 0.90,
            "pass_false_rollback_rate": 0.05,
        },
    ]
    assert choose(grid, 0.85)["entail"] == 0.6  # tie on false rollbacks: nearer 0.70 / 0.40
    fallback = choose(grid, 0.95)
    assert (fallback["entail"], fallback["qualified"]) == (0.6, False)
