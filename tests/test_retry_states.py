"""Stop 67: the states' first rollback, the copy rule and the choice of KA's factor (no model)."""

from __future__ import annotations

from scripts import retry_states as rs


def test_the_first_rolled_back_unit_of_each_answer_is_the_state() -> None:
    units = [
        {"key": "q1:source:0", "id": "q1", "mode": "source"},
        {"key": "q1:source:1", "id": "q1", "mode": "source"},
        {"key": "q1:source:2", "id": "q1", "mode": "source"},
        {"key": "q1:closed:0", "id": "q1", "mode": "closed"},
    ]
    verdicts = {
        "q1:source:0": {"verdict": "EMIT"},
        "q1:source:1": {"verdict": "ROLLBACK"},
        "q1:source:2": {"verdict": "ROLLBACK"},
        "q1:closed:0": {"verdict": "EMIT"},
    }
    assert rs.first_rollbacks(units, verdicts) == {"q1:source": "q1:source:1"}


def test_a_retry_copies_when_most_of_its_five_grams_are_in_the_passage() -> None:
    passage = "An employee is entitled to a written statement of reasons for dismissal on request."
    assert rs.copies("An employee is entitled to a written statement of reasons.", passage)
    assert not rs.copies("The employer must pay the employee within fourteen days.", passage)
    assert not rs.copies("An employee is entitled.", passage)  # under five words


def test_the_factor_is_the_most_passed_then_the_smallest() -> None:
    assert rs.choose_factor({1.5: 20, 2.0: 24, 4.0: 22}) == 2.0
    assert rs.choose_factor({1.5: 24, 2.0: 24, 4.0: 10}) == 1.5


def test_state_hashes_are_stable_and_differ_by_set() -> None:
    assert rs.state_hash("fresh", "a:closed:1") == rs.state_hash("fresh", "a:closed:1")
    assert rs.state_hash("fresh", "a:closed:1") != rs.state_hash("fresh2", "a:closed:1")


def test_retries_and_follow_ons_become_units_with_their_answer_so_far() -> None:
    states = [{"hash": "h", "query": "q?", "prefix": "First."}]
    retries = [
        {
            "hash": "h",
            "arms": {
                "K": {"retry": "Second.", "follow": "Third."},
                "B": {"retry": "", "follow": "Ignored."},
            },
        }
    ]
    units = {u["key"]: u for u in rs.sentence_units(states, retries)}
    assert set(units) == {"h:K:retry", "h:K:follow"}
    assert units["h:K:retry"]["prefix"] == "First."
    assert units["h:K:follow"]["prefix"] == "First. Second."
