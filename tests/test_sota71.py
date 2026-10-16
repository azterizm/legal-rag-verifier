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


def test_agreement_counts_matches_and_leaves_unsure_apart() -> None:
    key = {
        "Q001A1": {"id": "a", "text": "s1", "answers": ["qwen7:turn"]},
        "Q001A2": {"id": "a", "text": "s2", "answers": ["qwen7:none"]},
        "Q001A3": {"id": "a", "text": "s3", "answers": ["qwen7:turn", "minicpm1:none"]},
        "Q001A4": {"id": "a", "text": "s4", "answers": ["minicpm1:none"]},
    }
    first = {"Q001A1": "yes", "Q001A2": "no", "Q001A3": "unsure", "Q001A4": "yes"}
    final = {("a", "s1"): "yes", ("a", "s2"): "yes", ("a", "s3"): "no", ("a", "s4"): "no"}
    out = sota71.agreement(first, key, final)
    assert out["qwen7"] == {
        "sentences": 3,
        "unsure": 1,
        "match": 1,
        "match_share": 0.5,
        "wrong_by_opus_right_final": 1,
        "right_by_opus_wrong_final": 0,
    }
    assert out["qwen7 turn"]["sentences"] == 2
    assert out["qwen7 turn"]["match_share"] == 1.0
