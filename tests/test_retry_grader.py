"""Stop 67 grading: replies validated and reduced to one outcome (no model)."""

from __future__ import annotations

import pytest

from scripts import retry_grader as rg


def test_each_grade_reduces_to_one_outcome() -> None:
    good = {"grounding": "supported", "on_question": "yes", "reads_on": "yes", "same_error": ""}
    assert rg.outcome(good) == "good"
    assert rg.outcome({**good, "reads_on": "no"}) == "neither"
    assert rg.outcome({**good, "grounding": "no_claim"}) == "neither"
    assert rg.outcome({**good, "grounding": "contradicted", "same_error": "yes"}) == "wrong_same"
    assert rg.outcome({**good, "grounding": "unsupported", "same_error": "no"}) == "wrong_other"


def test_a_wrong_retry_needs_same_error_and_a_carried_one_needs_only_that() -> None:
    reply = {"grounding": "unsupported", "on_question": "yes", "reads_on": "yes"}
    with pytest.raises(ValueError, match="same_error"):
        rg.check(reply, False)
    carried = rg.check({"same_error": "No"}, True)
    assert carried == {"grounding": "carried_wrong", "same_error": "no"}
    with pytest.raises(ValueError, match="not an object"):
        rg.check("yes", False)


def test_items_on_the_sheet_are_found_with_their_mark() -> None:
    block = "- **S001A.** One.\n- **S001B.** (graded wrong before) Two."
    assert rg.items_of(block) == {"S001A": False, "S001B": True}
