"""Stops 48 and 49: folds, the five summaries, AUROC, thresholds, the keep rule, prompt spans."""

from __future__ import annotations

from typing import Any

import pytest

from scripts import auditor_judge as aj
from scripts import awareness as aw
from scripts import modal_ledger


def _rows() -> list[dict[str, Any]]:
    return [
        {"id": f"{d[:2]}-{n:02d}", "domain": d} for d in ("software", "legal") for n in range(40)
    ]


def test_folds_split_each_domain_in_half_and_are_stable() -> None:
    rows = _rows()
    fold = aw.folds(rows)
    assert fold == aw.folds(list(reversed(rows)))
    for domain in ("software", "legal"):
        ids = [r["id"] for r in rows if r["domain"] == domain]
        assert sum(fold[i] for i in ids) == 20
    assert set(fold.values()) == {0, 1}


def test_tokens_go_to_the_sentence_in_which_they_start() -> None:
    #          "One two. Three."   sentence ends at 8 and 15; a last token starts after the text
    offsets = [(0, 3), (3, 7), (7, 8), (8, 14), (14, 15), (15, 16)]
    assert aw.partition(offsets, [8, 15]) == [[0, 1, 2], [3, 4]]
    assert aw.token_spans(offsets, [(4, 9)]) == [[1, 4]]


def test_summaries_by_layer_third_and_dependence_per_token() -> None:
    m = {
        "tokens": 4,
        "logp": -2.0,
        "logp_without": -10.0,
        "attention": [0.1, 0.1, 0.4, 0.4, 0.7, 0.7],
    }
    out = aw.summarise(m)
    assert out["att_low"] == pytest.approx(0.1)
    assert out["att_mid"] == pytest.approx(0.4)
    assert out["att_high"] == pytest.approx(0.7)
    assert out["att_all"] == pytest.approx(0.4)
    assert out["dep"] == pytest.approx(2.0)
    spans = {"passages": [0.1, 0.2, 0.3], "sentence": [0.1, 0.1, 0.1], "other": [0.5, 0.5, 0.5]}
    by_span = aw.summarise({"tokens": 0, "attention": spans})
    assert by_span["att_all"] == pytest.approx(0.3)
    assert by_span["dep"] is None
    assert aw.summarise({"tokens": 3, "logp": -1.0, "logp_without": -4.0, "attention": None}) == {
        "att_all": None,
        "att_low": None,
        "att_mid": None,
        "att_high": None,
        "dep": pytest.approx(1.0),
    }


def test_auroc_counts_ties_half_and_can_stay_within_strata() -> None:
    assert aw.auroc([3, 2], [1, 0]) == 1.0
    assert aw.auroc([1], [1]) == 0.5
    assert aw.auroc([], [1]) is None
    # across strata the right items score lower; within each stratum they score higher
    strata = [([2.0], [1.0]), ([20.0], [10.0])]
    assert aw.auroc_within(strata) == 1.0
    assert aw.auroc([2.0, 20.0], [1.0, 10.0]) == 0.75


def test_candidate_ties_go_to_the_earlier_and_the_gate_needs_both_folds() -> None:
    assert aw.choose_candidate({"att_all": 0.7, "dep": 0.7, "att_low": 0.6}) == "att_all"
    assert aw.choose_candidate({"att_all": None, "dep": 0.55}) == "dep"
    assert aw.choose_candidate({}) is None
    assert aw.gate([0.66, 0.74])
    assert not aw.gate([0.64, 0.90])
    assert not aw.gate([0.66, 0.70])
    assert not aw.gate([0.9, None])


def test_threshold_maximises_the_gain_and_a_tie_goes_lower() -> None:
    items = [(0.1, False), (0.2, False), (0.3, True), (0.4, True)]

    def correct(flagged: list[bool], kept: list[bool]) -> float:
        return sum(not right for right in flagged) + sum(kept)

    assert aw.choose_threshold(items, correct) == 0.3
    assert aw.choose_threshold([(0.1, True), (0.2, True)], correct) == float("-inf")
    assert aw.choose_threshold([(0.1, False), (0.2, False)], correct) == float("inf")


def test_keep_takes_the_first_over_the_threshold_else_the_most_aware() -> None:
    attempts = [
        {"attempt": 0, "awareness": 0.1, "label": "supported"},
        {"attempt": 1, "awareness": 0.5, "label": "not_stated"},
        {"attempt": 2, "awareness": 0.9, "label": "supported"},
    ]
    kept = aw.keep(attempts, 0.4)
    assert (kept["attempt"], kept["exhausted"]) == (1, False)
    kept = aw.keep(attempts[:2], 0.6)
    assert (kept["attempt"], kept["exhausted"]) == (1, True)
    unparsed = [
        *attempts[:1],
        {"attempt": 1, "awareness": 0.9, "label": "not_stated", "unparsed": True},
    ]
    kept = aw.keep(unparsed, 0.4)
    assert (kept["attempt"], kept["exhausted"]) == (0, True)


def test_an_attempt_is_its_first_parsed_sample_else_not_stated() -> None:
    rows = [
        {"sha": "a", "attempt": 0, "seed": 0, "label": "error", "passage": 0},
        {"sha": "a", "attempt": 0, "seed": 100, "label": "supported", "passage": 2},
        {"sha": "a", "attempt": 1, "seed": 1, "label": "error", "passage": 0},
        {"sha": "a", "attempt": 1, "seed": 201, "label": "error", "passage": 0},
    ]
    out = aw.attempts_of(rows)["a"]
    assert (out[0]["label"], out[0]["seed"], out[0]["unparsed"]) == ("supported", 100, False)
    assert (out[1]["label"], out[1]["seed"], out[1]["unparsed"]) == ("not_stated", 201, True)


def test_judge_item_spans_cover_the_passages_and_the_sentence() -> None:
    item = aw.judge_item(aj, "It is {12} days.", ["First passage.", "Second."], "")
    user = item["user"]
    start, end = item["spans"]["passages"]
    assert user[start:end] == "[1] First passage.\n\n[2] Second."
    start, end = item["spans"]["sentence"]
    assert user[start:end] == "It is {12} days."
    assert item["sha"] == aj.prompt_key(
        aj.user_prompt("It is {12} days.", ["First passage.", "Second."], "")
    )
    assert "First passage" not in item["blank"]
    assert "Passages:\n(none)" in item["blank"]
    assert "It is {12} days." in item["blank"]


def test_stage_stop_refuses_a_chunk_that_would_pass_it(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(modal_ledger, "LEDGER", tmp_path / "ledger.json")
    modal_ledger.record("stop48 k2-low", "L40S", 3600)
    modal_ledger.record("stop47 fresh", "H100", 3600)
    assert modal_ledger.stage_spent("stop48") == pytest.approx(2.2425)
    modal_ledger.check_stage("stop48", 12.0, "L40S", 900)
    with pytest.raises(modal_ledger.ModalBudgetError, match="stop48"):
        modal_ledger.check_stage("stop48", 2.5, "L40S", 900)
