"""Stop 36: items for the blind review, and the judge reply parser."""

from __future__ import annotations

from typing import Any

import pytest

from scripts.rollback_review import Item, dedupe, parse, state_items, trace_items


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
