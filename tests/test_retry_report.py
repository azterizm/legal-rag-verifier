"""Stop 67: the exact tests and the Holm adjustment of the readings (no model)."""

from __future__ import annotations

import pytest

from scripts import retry_report as rr


def test_mcnemar_is_exact_and_symmetric() -> None:
    assert rr.mcnemar(0, 0) == 1.0
    assert rr.mcnemar(6, 0) == pytest.approx(2 / 64)
    assert rr.mcnemar(2, 9) == rr.mcnemar(9, 2)


def test_holm_steps_down_and_stays_monotone() -> None:
    adjusted = rr.holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert adjusted == pytest.approx({"a": 0.03, "c": 0.06, "b": 0.06})


def test_six_comparisons_include_ka_against_t() -> None:
    assert ("KA", "T") in rr.COMPARISONS
    assert len(rr.COMPARISONS) == 6
