"""Stop 74: the rewrite walk, its prompt and its readings (no model, no router call)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from legal_rag_verifier.premise import Passage, Premise
from scripts import rewrite74 as rw

ITEM_PREMISE = Premise(
    (
        Passage("A complaint must be presented within three months.", heading="s 111(2)"),
        Passage("The tribunal may extend the time limit.", heading="s 111(3)"),
        Passage("Unrelated text about fees.", heading="s 200"),
    )
)
ITEM = {"id": "q1", "query": "When must a complaint be presented?", "domain": "legal"}


def _item() -> dict[str, Any]:
    return {**ITEM, "premise": ITEM_PREMISE}


def _labels(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> rw.Labels:
    monkeypatch.setattr(rw, "OUT", tmp_path)
    return rw.Labels("fake", None)


def _ask(bad: str) -> Any:
    """A judge that finds any sentence containing ``bad`` not stated."""

    def ask(messages: list[dict[str, str]]) -> dict[str, Any]:
        sentence = messages[-1]["content"].split("Sentence to check")[-1]
        label = "not_stated" if bad in sentence else "supported"
        return {"content": json.dumps({"label": label, "passage": 1}), "ms": 1, "tokens": 1}

    return ask


def test_the_source_takes_two_windows_and_is_cut_at_a_word() -> None:
    text = rw.source_text(ITEM_PREMISE, [1, 0, 2])
    assert text.startswith("[s 111(3)]\nThe tribunal")
    assert "fees" not in text
    cut = rw.source_text(ITEM_PREMISE, [0], limit=30)
    assert cut.endswith(" …")
    assert len(cut) <= 32
    assert not cut[:-2].endswith("thr")


def test_the_turn_follows_the_kept_sentences_or_the_question() -> None:
    none = rw.rewrite_messages(_item(), [], "SRC")
    assert [m["role"] for m in none] == ["system", "user", "user"]
    assert "SRC" in none[-1]["content"]
    assert "provision relevant to the question" in none[-1]["content"]
    assert ITEM["query"] in none[-1]["content"]
    some = rw.rewrite_messages(_item(), ["One.", "Two."], "SRC")
    assert [m["role"] for m in some] == ["system", "user", "assistant", "user"]
    assert some[2]["content"] == "One. Two."


def test_first_sentence_only() -> None:
    assert rw.first_sentence("It is three months. Then more.") == "It is three months."
    assert rw.first_sentence("   ") == ""


def test_drop_mode_drops_and_rewrite_mode_replaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    labels = _labels(tmp_path, monkeypatch)
    text = "A complaint must be presented within three months. The moon is BAD cheese."
    judge = rw.Judge(labels, _ask("BAD"), "fake")
    dropped = rw.walk(_item(), text, judge, None)
    assert dropped["text"] == "A complaint must be presented within three months."
    assert [p["outcome"] for p in dropped["points"]] == ["dropped"]
    assert dropped["points"][0]["by"] == "judge"

    calls: list[tuple[list[dict[str, str]], float]] = []
    replies = iter(["Still BAD here.", "The complaint must be made within three months. Extra."])

    def rewrite(messages: list[dict[str, str]], temperature: float) -> str:
        calls.append((messages, temperature))
        return next(replies)

    out = rw.walk(_item(), text, rw.Judge(labels, _ask("BAD"), "fake"), rewrite)
    assert out["text"].endswith("The complaint must be made within three months.")
    (point,) = out["points"]
    assert point["outcome"] == "try2"
    assert [t for _, t in calls] == [0.0, 1.0]
    assert calls[0][0] == calls[1][0]  # every try sends the same turn
    assert calls[0][0][2]["content"] == "A complaint must be presented within three months."


def test_three_failed_tries_drop_the_sentence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    labels = _labels(tmp_path, monkeypatch)
    temps: list[float] = []

    def rewrite(messages: list[dict[str, str]], temperature: float) -> str:
        temps.append(temperature)
        return "" if len(temps) == 2 else "Again BAD."

    out = rw.walk(_item(), "The BAD claim here.", rw.Judge(labels, _ask("BAD"), "f"), rewrite)
    assert out["text"] == ""
    (point,) = out["points"]
    assert point["outcome"] == "dropped"
    assert temps == list(rw.TEMPERATURES)
    assert [t["text"] for t in point["tries"]] == ["Again BAD.", "", "Again BAD."]
    assert "verdict" not in point["tries"][1]  # an empty reply is a failed try, not judged


def test_a_rewrite_changes_the_prefix_for_later_sentences(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    labels = _labels(tmp_path, monkeypatch)
    prefixes: list[str] = []
    judge = rw.Judge(labels, _ask("BAD"), "f")
    real = judge.score

    def score(premises: Any, hypothesis: str) -> Any:
        prefixes.append(judge.prefix)
        return real(premises, hypothesis)

    monkeypatch.setattr(judge, "score", score)
    text = "The BAD one here. The tribunal may extend the time limit."
    rw.walk(_item(), text, judge, lambda m, t: "A complaint must be presented within three months.")
    assert prefixes[-1] == "A complaint must be presented within three months."


def test_labels_are_reused_and_offline_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    labels = _labels(tmp_path, monkeypatch)
    asked: list[int] = []
    base = _ask("BAD")

    def ask(messages: list[dict[str, str]]) -> dict[str, Any]:
        asked.append(1)
        return {**base(messages), "provider": "groq"}

    text = "A complaint must be presented within three months."
    rw.walk(_item(), text, rw.Judge(labels, ask, "q"), None)
    n = len(asked)
    rw.walk(_item(), text, rw.Judge(labels, ask, "q"), None)
    assert len(asked) == n
    stored = [json.loads(x) for x in labels.file.read_text().splitlines()]
    assert {r["provider"] for r in stored} == {"groq"}
    fresh = rw.Labels("other", None)
    with pytest.raises(rw.MissingLabelError):
        rw.walk(_item(), text, rw.Judge(fresh, None, "q"), None)


def test_no_valid_label_rotates_and_asks_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    labels = _labels(tmp_path, monkeypatch)
    rotated: list[int] = []
    replies = iter(["no", "no", "no", json.dumps({"label": "supported", "passage": 1})])

    def ask(messages: list[dict[str, str]]) -> dict[str, Any]:
        return {"content": next(replies), "ms": 1, "tokens": 1}

    judge = rw.Judge(labels, ask, "q", rotate=lambda: rotated.append(1))
    out = rw.walk(_item(), "A complaint must be presented within three months.", judge, None)
    assert rotated == [1]
    assert out["points"] == []


def _row(wrong: int, right: int, sentences: int) -> dict[str, int]:
    return {"wrong": wrong, "right": right, "sentences": sentences}


def test_readings_on_a_toy_table() -> None:
    drop = [_row(0, 1, 1)] * 200 + [_row(0, 0, 0)] * 38 + [_row(1, 1, 2)] * 2
    better = [_row(0, 2, 2)] * 200 + [_row(0, 1, 1)] * 38 + [_row(1, 1, 2)] * 2
    out = rw.compare(better, drop)
    assert out["wrong"]["keeps"]
    assert out["empty"] == {
        "rewrite": 0,
        "drop": 38,
        "only_rewrite_empty": 0,
        "only_drop_empty": 38,
        "p": out["empty"]["p"],
        "fewer": True,
    }
    assert out["right"]["more"]
    assert out["better_than_dropping"]
    worse = [_row(1, 1, 1)] * 20 + drop[20:]
    out = rw.compare(worse, drop)
    assert not out["wrong"]["keeps"]
    assert not out["better_than_dropping"]
