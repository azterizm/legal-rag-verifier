"""Stop 73: the ConSens formula, the words scored, prompts, thresholds and token arithmetic."""

from __future__ import annotations

import math
from typing import Any

import pytest

from scripts import consens as cs


def test_formula_reproduces_the_papers_table_1() -> None:
    # Table 1: word perplexities of "biochemist computational biologist", empty context and the
    # right context. The paper gives ConSens 0.91.
    empty, context = [4814.38, 7117.1, 1.61], [263.73, 293.92, 1.72]
    pe = cs.perplexity([-math.log(w) for w in empty])
    pc = cs.perplexity([-math.log(w) for w in context])
    assert pe == pytest.approx(sum(empty) / 3)
    assert round(cs.score(pe, pc) or 0.0, 2) == 0.91
    assert cs.score(pc, pc) == 0.0
    assert (cs.score(pc, pe) or 0.0) < 0
    assert cs.score(None, pc) is None
    assert cs.perplexity([]) is None


def test_the_papers_example_keeps_three_words() -> None:
    sentence = "David Baker is a biochemist and computational biologist."
    keep, fallback = cs.kept(sentence, "What is David Baker known for?")
    assert [sentence[s:e] for s, e in keep] == ["biochemist", "computational", "biologist"]
    assert not fallback


def test_fallback_and_no_word() -> None:
    keep, fallback = cs.kept("Version 1.0.0 is lower.", "Is version 1.0.0 lower?")
    assert fallback
    assert [s for s, _ in keep] == [0, 8, 14, 17]
    assert cs.kept("```", "What?") == ([], False)
    keep, _ = cs.kept("The s.124 claim's time-limit", "")
    assert len(keep) == 3


def test_prompts_follow_the_template_with_the_answer_so_far() -> None:
    head = cs.prompt("Source text.", "Why?", "First sentence.")
    assert head == (
        "Consider the following context:\nContext:\nSource text.\n"
        "Please answer the following question:\nWhy?\nAnswer: First sentence. "
    )
    assert cs.prompt("", "Why?", "").startswith("Consider the following context:\nContext:\n\n")
    assert cs.prompt("", "Why?", "").endswith("Answer: ")


def _unit(key: str, value: float | None, *, right: bool, claim: bool = False) -> dict[str, Any]:
    mode = "source" if key.startswith("s") else "closed"
    return {
        "key": key,
        "value": value,
        "right": right,
        "wrong": not right,
        "claim": claim,
        "mode": mode,
    }


def test_threshold_ties_go_to_the_lower_and_claims_are_rolled_back() -> None:
    units = [
        _unit("s1", 0.9, right=True),
        _unit("s2", 0.5, right=True),
        _unit("c1", -0.2, right=False),
        _unit("c2", 0.1, right=False),
        _unit("c3", None, right=False, claim=True),
    ]
    cut = cs.threshold(units, claim=False)
    assert cut == 0.5  # rolls back the two wrong sentences only
    tied = [
        _unit("c1", 0.1, right=False),
        _unit("s1", 0.5, right=True),
        _unit("c2", 0.6, right=False),
        _unit("s2", 0.9, right=True),
    ]
    assert cs.threshold(tied, claim=False) == 0.5  # 0.5 and 0.9 both score 3 of 4
    v = cs.verdicts(units, cut, claim=True)
    assert [v[u["key"]]["verdict"] for u in units] == [
        "EMIT",
        "EMIT",
        "ROLLBACK",
        "ROLLBACK",
        "ROLLBACK",
    ]
    alone = cs.verdicts(units, cut, claim=False)
    assert alone["c3"]["verdict"] == "EMIT"  # no value: ConSens never rolls it back


def test_items_hold_no_grade_and_hash_their_inputs() -> None:
    data = {
        "units": [
            {
                "key": "gs-01:source:0",
                "sentence": "CronJob is an API object.",
                "query": "What is CronJob?",
                "prefix": "",
                "right": True,
            },
        ],
        "sources": {"gs-01:source:0": "CronJob is part of the Kubernetes REST API."},
    }
    (item,) = cs.items(data)
    assert set(item) == {"key", "with", "without", "sentence", "keep", "fallback", "sha"}
    assert item["with"].count("Kubernetes") == 1
    assert "Kubernetes" not in item["without"]
    assert cs.items(data)[0]["sha"] == item["sha"]


def test_logits_kept_match_a_full_forward_pass() -> None:
    torch = pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    tiny = "hf-internal-testing/tiny-random-LlamaForCausalLM"
    try:
        model = transformers.AutoModelForCausalLM.from_pretrained(
            tiny, local_files_only=True, dtype=torch.float32
        )
    except OSError:
        pytest.skip(f"{tiny} is not in the local cache")
    model.eval()

    class Chars:
        """One token per character after a BOS, with offsets, like a fast tokenizer."""

        def __call__(self, text: str, *, return_offsets_mapping: bool) -> dict[str, Any]:
            assert return_offsets_mapping
            ids = [1, *(3 + ord(c) % 500 for c in text)]
            return {
                "input_ids": ids,
                "offset_mapping": [(0, 0)] + [(i, i + 1) for i in range(len(text))],
            }

    head, sentence = "Context:\nabc\nAnswer: ", "Go far."
    item = {"sentence": sentence, "keep": [(3, 6)]}  # "far"
    got, n = cs._logps(model, Chars(), torch, head, item)
    ids = Chars()(head + sentence, return_offsets_mapping=True)["input_ids"]
    with torch.no_grad():
        full = torch.log_softmax(model(input_ids=torch.tensor([ids])).logits[0].float(), -1)
    start = len(head) + 1  # the BOS shifts characters by one token
    want = [float(full[i - 1, ids[i]]) for i in range(start + 3, start + 6)]
    assert n == len(ids)
    assert got == pytest.approx(want, abs=1e-5)
    row = cs.measure(
        model, Chars(), torch, {**item, "key": "k", "sha": "s", "with": head, "without": "Answer: "}
    )
    assert len(row["logp_context"]) == len(row["logp_empty"]) == 3
    assert row["ms"] > 0
