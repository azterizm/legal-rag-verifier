"""Stop 68: the pool draw, grade replies, and the paired reading (no model)."""

from __future__ import annotations

import pytest

from scripts import live68 as l68
from scripts import live68_grade as lg


def test_the_pool_draw_is_stable_and_balanced() -> None:
    pool = [{"id": f"l{n:03d}", "domain": "legal"} for n in range(90)]
    pool += [{"id": f"s{n:03d}", "domain": "software"} for n in range(70)]
    ids = l68.draw(pool, n=10)
    assert ids == l68.draw(list(reversed(pool)), n=10)
    assert sum(i.startswith("l") for i in ids) == sum(i.startswith("s") for i in ids) == 10


def test_a_reply_must_grade_every_item() -> None:
    assert lg.parse({"Q001A1": "Yes", "Q001A2": "no"}, ["Q001A1", "Q001A2"], again=False) == {
        "Q001A1": "yes",
        "Q001A2": "no",
    }
    again = {"Q001A1": {"reason": "r", "grade": "unsure"}}
    assert lg.parse(again, ["Q001A1"], again=True) == {"Q001A1": "unsure"}
    with pytest.raises(ValueError, match="Q001A2"):
        lg.parse({"Q001A1": "yes"}, ["Q001A1", "Q001A2"], again=False)


def test_answers_with_a_wrong_sentence_are_paired_by_question() -> None:
    def row(wrong: int) -> dict[str, int]:
        return {"wrong": wrong}

    by = {
        "g:s:1:plain": row(0),
        "g:s:1:turn": row(1),
        "g:s:2:plain": row(0),
        "g:s:2:turn": row(2),
        "g:s:3:plain": row(1),
        "g:s:3:turn": row(1),
    }
    out = lg.paired(by, "g", "plain", "turn", ["s:1", "s:2", "s:3"])
    assert (out["only_a_wrong"], out["only_b_wrong"]) == (0, 2)
    assert out["p"] == pytest.approx(0.5)


def test_the_wilson_interval_holds_the_share() -> None:
    low, high = lg.wilson(6, 50)
    assert low < 0.12 < high
    assert lg.wilson(0, 0) == [0.0, 0.0]
