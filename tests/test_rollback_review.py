"""Stop 36: items for the blind review, and the judge reply parser."""

from __future__ import annotations

from typing import Any

import pytest

from scripts.rollback_review import (
    Item,
    dedupe,
    parse,
    score,
    state_items,
    trace_items,
    wilson,
)


def attempt(text: str, verdict: str) -> dict[str, Any]:
    return {"verdict": {"text": text, "verdict": verdict}}


def test_dedupe_merges_exact_duplicates_and_keeps_sources() -> None:
    items = [
        Item("q1", "", "Same.", [{"arm": "X"}]),
        Item("q1", "", "Other.", [{"arm": "R1"}]),
        Item("q1", "", "Same.", [{"arm": "R4"}]),
        Item("q1", "Before.", "Same.", [{"arm": "R0"}]),  # another answer so far: kept apart
    ]
    out = dedupe(items)
    assert [i.sentence for i in out] == ["Same.", "Other.", "Same."]
    assert out[0].sources == [{"arm": "X"}, {"arm": "R4"}]


def test_state_items_skip_empty_retries_and_mark_x_rejected() -> None:
    record = {
        "id": "q1",
        "X": {"text": "Wrong."},
        "R0": {"text": "", "verdict": "REFUSED"},
        "R1": {"text": "Right.", "verdict": "EMIT"},
        "R3": {"text": "Wrong.", "verdict": "ROLLBACK"},
        "R4": {"text": " Also. ", "verdict": "EMIT"},
    }
    items, empty = state_items(record, "Before.")
    assert empty == ["R0"]
    assert [i.sentence for i in items] == ["Wrong.", "Right.", "Also."]
    assert items[0].sources == [
        {"arm": "X", "verdict": "ROLLBACK"},
        {"arm": "R3", "verdict": "ROLLBACK"},
    ]
    assert {i.prefix for i in items} == {"Before."}


def test_trace_items_take_rejected_drafts_and_released_sentences() -> None:
    record = {
        "id": "q1",
        "answer": "First. Fixed.",
        "trace": {
            "sentences": [
                {"text": "First.", "outcome": "emitted", "attempts": [attempt("First.", "EMIT")]},
                {
                    "text": "Fixed.",
                    "outcome": "emitted",
                    "attempts": [attempt("Bad.", "ROLLBACK"), attempt("Fixed.", "EMIT")],
                },
            ]
        },
    }
    items = trace_items(record, "4B")
    assert [(i.prefix, i.sentence, i.sources[0]["kind"]) for i in items] == [
        ("", "First.", "released"),
        ("First.", "Bad.", "rejected"),
        ("First.", "Fixed.", "released"),
    ]
    assert trace_items({"id": "q2", "answer": "Refused.", "trace": None}, "4B-inject-v2") == []


def test_parse_accepts_the_labels_and_rejects_anything_else() -> None:
    reply = (
        'Here: {"grounding": "supported", "error": "typo", "on_question": true, "reads_on": "no"}'
    )
    parsed = parse(reply)
    assert (parsed["on_question"], parsed["reads_on"], parsed["error"]) == ("yes", "no", "other")
    with pytest.raises(ValueError, match="grounding"):
        parse('{"grounding": "fine", "on_question": "yes", "reads_on": "yes"}')
    with pytest.raises(ValueError, match="reads_on"):
        parse('{"grounding": "no_claim", "on_question": "yes", "reads_on": "maybe"}')
    with pytest.raises(ValueError, match="no JSON"):
        parse("no object here")


def lab(grounding: str, on_question: str = "yes", reads_on: str = "yes") -> dict[str, str]:
    return {"grounding": grounding, "on_question": on_question, "reads_on": reads_on}


def test_score_reads_the_preset_measures() -> None:
    def state(x: str, r0: dict[str, str] | None, r1: dict[str, str]) -> dict[str, Any]:
        arm = {"label": lab("supported"), "verdict": "EMIT"}
        return {
            "X": {"label": lab(x), "verdict": "ROLLBACK"},
            "R0": {"label": r0, "verdict": "EMIT" if r0 else "EMPTY"},
            "R1": {"label": r1, "verdict": "EMIT"},
            "R3": arm,
            "R4": arm,
        }

    states = {
        "a": state("unsupported", None, lab("supported")),
        "b": state("contradicted", lab("unsupported"), lab("supported", reads_on="no")),
        "c": state("supported", lab("supported"), lab("supported", on_question="no")),
    }
    out = score(states)
    assert out["P1_rejected_drafts_real_errors"]["real_errors"] == 2
    assert (out["P2_good_retry_R1_vs_R0"]["R1_good"], out["P2_good_retry_R1_vs_R0"]["R0_good"]) == (
        1,
        1,
    )
    assert out["arms"]["R0"]["no_text"] == 1
    assert out["arms"]["R1"]["supported_off_question"] == 1
    assert out["arms"]["R1"]["accepted_not_good"] == 2
    assert out["descriptive_not_preset"]["supported_R1_vs_R0"]["only_R1"] == 2
    assert wilson(0, 0) == (0.0, 0.0)
    low, high = wilson(18, 46)
    assert low < 18 / 46 < high
