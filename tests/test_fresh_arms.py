"""Stops 52 and 53: list numbers, the graded units, the claim check switch and the new prompt."""

from __future__ import annotations

import legal_rag_verifier.verifier as module
from legal_rag_verifier.claims import ClaimKind, extract_claims
from legal_rag_verifier.segmenter import find_boundary, split_sentences
from scripts import auditor_judge as aj
from scripts import fresh_arms as fa
from scripts import fresh_eval as fe


def test_a_list_number_stays_with_its_item() -> None:
    text = "It is calculated as follows:\n1. Half a week's pay per year. 2. One week's pay.\n3."
    assert [s.text for s in split_sentences(text)] == [
        "It is calculated as follows:",
        "1. Half a week's pay per year.",
        "2. One week's pay.",
        "3.",
    ]
    assert [s.text for s in split_sentences("1.\nHalf a week's pay.")] == ["1.\nHalf a week's pay."]


def test_a_list_number_is_undecided_mid_stream_and_other_numbers_still_end_sentences() -> None:
    assert find_boundary("1. ", 0) is None
    assert find_boundary("1. Half a week", 0) is None
    assert find_boundary("1. Half a week. Then", 0) == len("1. Half a week.")
    assert [s.text for s in split_sentences("The limit is 20. It applies to all.")] == [
        "The limit is 20.",
        "It applies to all.",
    ]
    assert [s.text for s in split_sentences("It rose by 2.5 days in 2019. Then it fell.")] == [
        "It rose by 2.5 days in 2019.",
        "Then it fell.",
    ]


def test_a_leading_list_number_is_not_a_claim() -> None:
    numbers = [c.value for c in extract_claims("2. The limit is 20.") if c.kind is ClaimKind.NUMBER]
    assert numbers == ["20"]
    assert [c.value for c in extract_claims("2.")] == ["2"]
    assert [c.value for c in extract_claims("20 is the limit.")] == ["20"]


def test_a_merged_sentence_maps_back_to_the_units_that_were_graded() -> None:
    assert fe.as_graded("1. For each year, half a week's pay.") == [
        "1.",
        "For each year, half a week's pay.",
    ]
    assert fe.as_graded("For 1. year") == ["For 1. year"]
    assert fe.as_graded("2.") == ["2."]


def test_the_view_prompt_holds_the_question_and_the_source_and_rule_adds_one_paragraph() -> None:
    view = fa.view_prompt("view", "It is 10 seconds.", "[H]\ndefault = 10s", "What is it?", "")
    rule = fa.view_prompt("rule", "It is 10 seconds.", "[H]\ndefault = 10s", "What is it?", "")
    assert "What is it?" in view
    assert "[H]\ndefault = 10s" in view
    assert "<<<\n(none)\n>>>" in view
    assert "list number" not in view
    assert "list number" in rule
    assert rule.replace(fa._RULE, "") == view
    assert aj.prompt_key(view) != aj.prompt_key(rule)


def test_the_claim_check_switch_is_restored() -> None:
    with fa.no_claims():
        assert module.__dict__["extract_claims"]("section 1 of the Act 2000, 20 days") == []
    assert module.__dict__["extract_claims"]("20 days")


def test_a_missing_label_counts_as_not_stated() -> None:
    scorer = fa.Scorer("judge", "p42", {}, {})
    scorer.unit = {"key": "k", "prefix": "", "query": "q"}
    probs = scorer.score(["passage one", "passage two"], "A sentence.")
    assert scorer.missing == 1
    assert [p.neutral for p in probs] == [1.0, 1.0]


def test_the_notes_sit_before_the_reply_format_and_leave_the_stop_42_prompt_intact() -> None:
    base = aj.user_prompt("It is 10 seconds.", ["default = 10s"], "")
    two = fa.notes_prompt("notes2", "It is 10 seconds.", ["default = 10s"], "")
    three = fa.notes_prompt("notes3", "It is 10 seconds.", ["default = 10s"], "")
    assert two.replace(fa._NOTES + "\n", "") == base
    assert three.replace(fa._NOTES + fa._HEDGE + "\n", "") == base
    assert "hedged" in three
    assert "hedged" not in two
    assert two.index("How to apply the labels") < two.index("Return JSON")
    assert fa.prompt("p42", "It is 10 seconds.", ["default = 10s"], {"prefix": ""}, "") == base
