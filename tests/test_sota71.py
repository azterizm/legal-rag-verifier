"""Stop 71: the paired bootstrap and the one-grader rule (no model, no router call)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import live68_grade as lg
from scripts import sota71


def test_the_bootstrap_interval_is_stable_and_holds_the_mean() -> None:
    diffs = [1] * 20 + [-1] * 10 + [0] * 210
    low, high = sota71.bootstrap(diffs, resamples=2000)
    assert (low, high) == tuple(sota71.bootstrap(diffs, resamples=2000))
    assert low < 10 / 240 < high


def test_one_grader_settles_yes_and_no_and_leaves_unsure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "key.json").write_text(json.dumps({"Q001A1": {}, "Q001A2": {}, "Q001A3": {}}))
    monkeypatch.setattr(lg, "OUT", tmp_path)
    monkeypatch.setattr(lg, "GRADERS", ("opus55",))
    grades = {"Q001A1": "yes", "Q001A2": "unsure", "Q001A3": "no"}
    monkeypatch.setattr(lg, "done", lambda grader, again=False: {} if again else grades)
    settled = lg.consensus()
    assert settled["Q001A1"] == {"grade": "yes", "by": "first"}
    assert settled["Q001A2"] == {}
    assert settled["Q001A3"]["grade"] == "no"
