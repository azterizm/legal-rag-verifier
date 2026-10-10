"""Stop 50: the paired test and the three-way reading used to compare teachers."""

from __future__ import annotations

import pytest

from scripts import teacher_opus as to
from scripts import teacher_pro as tp


def test_sign_test_is_exact_and_two_sided() -> None:
    assert tp.sign_test(0, 0) == 1.0
    assert tp.sign_test(5, 5) == 1.0
    assert tp.sign_test(0, 5) == pytest.approx(2 / 32)
    assert tp.sign_test(15, 6) == pytest.approx(tp.sign_test(6, 15))
    assert tp.sign_test(15, 6) == pytest.approx(0.0784, abs=1e-4)


def test_sides_counts_only_clauses_where_the_two_teachers_differ() -> None:
    def lab(x: str) -> dict[str, str]:
        return {"label": x}

    flash = {"a": lab("supported"), "b": lab("not_stated"), "c": lab("not_stated"), "d": lab("x")}
    opus = {"a": lab("supported"), "b": lab("supported"), "c": lab("contradicted")}
    opus |= {"d": lab("supported")}
    pro = {"a": lab("not_stated"), "b": lab("supported"), "c": lab("not_stated")}
    out = tp.sides(pro, flash, opus, ["a", "b", "c", "d"])
    assert out == {"differ": 2, "with opus55": 1, "with flash": 1, "neither": 0}


def test_a_clause_without_a_valid_label_counts_as_not_stated() -> None:
    labels = {"a": {"label": "supported", "passage": 1}, "b": {"label": "error", "passage": 0}}
    out, missing = tp.filled(labels, ["a", "b", "c"])
    assert missing == 2
    assert [out[k]["label"] for k in "abc"] == ["supported", "not_stated", "not_stated"]


def test_better_needs_higher_accuracy_and_a_significant_sign_test() -> None:
    assert to.better(0.90, 0.88, 0.01)
    assert not to.better(0.90, 0.88, 0.20)
    assert not to.better(0.88, 0.90, 0.01)
    assert to.router.CAPS[to.router.OPUS55] > to.STAGE_STOP
