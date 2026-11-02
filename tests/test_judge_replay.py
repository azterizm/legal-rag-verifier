"""Stop 77: the package judge replays the recorded labels of both fresh tests exactly.

A fake endpoint serves the label recorded for each prompt (``prompt_key``); the verifier is the
package's ``JudgedVerifier`` with ``STRICT_FIGURES``, run post-hoc on every answer. The counts are
stop 61's (``results/fresh_arms/short.json`` and ``results/fresh2_arms/short.json``).

``scripts/fresh_battery.py`` reads the set from ``FRESH_SET`` at import, so each set gets its own
private copies of ``fresh_battery`` and ``fresh_eval``; the shared modules are never reloaded.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from legal_rag_verifier.corpus import instrument_path
from legal_rag_verifier.judge import STRICT_FIGURES, Judge, JudgedVerifier, prompt_key
from legal_rag_verifier.verifier import SentenceVerdict, Verdict

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ENRICHMENT = ROOT / "enrichment" / "gemini-3.8-flash-high"
LABEL_FILE = "labels/qwen27-ar4.short.jsonl"
DOMAINS = {"software": "software", "legal": "statutes"}

# set → (total cell, software cell, statutes cell); "correct" = right - false rollbacks + caught.
EXPECTED: dict[str, dict[str, dict[str, int]]] = {
    "fresh2": {
        "total": {"units": 151, "correct": 136, "false_rollbacks": 8, "caught": 60},
        "software": {"units": 78, "false_rollbacks": 5, "caught": 23},
        "statutes": {"units": 73, "false_rollbacks": 3, "caught": 37},
    },
    "fresh": {
        "total": {"units": 354, "correct": 332, "false_rollbacks": 7, "caught": 133},
        "software": {"units": 170, "false_rollbacks": 4, "caught": 49},
        "statutes": {"units": 184, "false_rollbacks": 3, "caught": 84},
    },
}
# Unique prompts sent by check_text under STRICT_FIGURES (GRID stop 77, step 0 check).
SENT = {"fresh2": 140, "fresh": 347}


def _missing_inputs(name: str) -> list[str]:
    results, battery = ROOT / "results" / name, ROOT / "batteries" / name
    files = [results / f for f in ("answers.jsonl", "key.json", "grades.csv", LABEL_FILE)]
    files += [battery / "software.jsonl", battery / "statutes.jsonl"]
    missing = [str(f.relative_to(ROOT)) for f in files if not f.is_file()]
    if not ENRICHMENT.is_dir():
        missing.append(str(ENRICHMENT.relative_to(ROOT)))
    statutes = battery / "statutes.jsonl"
    if statutes.is_file():
        for line in statutes.read_text(encoding="utf-8").splitlines():
            for coordinate in json.loads(line)["premise"]:
                try:
                    present = instrument_path(DATA, coordinate).is_file()
                except FileNotFoundError:
                    present = False
                if not present:
                    missing.append(f"data/ file for {coordinate}")
    return missing


def _private(module: str, name: str, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """A fresh copy of ``scripts/<module>.py`` under a private name, removed after the test."""
    alias = f"_judge_replay_{name}_{module}"
    spec = importlib.util.spec_from_file_location(alias, ROOT / "scripts" / f"{module}.py")
    assert spec is not None
    assert spec.loader is not None
    copy = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, alias, copy)
    spec.loader.exec_module(copy)
    return copy


def _load(name: str, monkeypatch: pytest.MonkeyPatch) -> tuple[ModuleType, ModuleType]:
    """``fresh_battery`` and ``fresh_eval`` for one set. ``fresh_eval`` imports ``fresh_battery``
    by name, so that name points at the private copy while it runs; monkeypatch restores it."""
    monkeypatch.setenv("FRESH_SET", name)
    monkeypatch.setattr(sys, "path", list(sys.path))
    fb = _private("fresh_battery", name, monkeypatch)
    assert name == fb.SET
    monkeypatch.setitem(sys.modules, "fresh_battery", fb)
    fe = _private("fresh_eval", name, monkeypatch)
    assert ROOT / "results" / name == fe.OUT
    return fb, fe


class Recorded:
    """The endpoint: the recorded label and passage for each prompt. Unknown prompts are kept
    and fail the test; they are answered not stated only so the run can finish."""

    def __init__(self, labels: Mapping[str, Mapping[str, Any]]) -> None:
        self.labels = labels
        self.sent: set[str] = set()
        self.unknown: set[str] = set()

    def __call__(self, messages: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        key = prompt_key(str(messages[1]["content"]))
        self.sent.add(key)
        row = self.labels.get(key)
        if row is None:
            self.unknown.add(key)
            row = {"label": "not_stated", "passage": 0}
        content = json.dumps({"label": row["label"], "passage": row["passage"]})
        return {"content": content, "ms": 1.0, "tokens": 1, "finish": "stop"}


def _cell(units: Sequence[Mapping[str, Any]], verdicts: Mapping[str, SentenceVerdict]) -> Any:
    rolled = [u for u in units if verdicts[u["key"]].verdict is not Verdict.EMIT]
    right, wrong = sum(u["right"] for u in units), sum(u["wrong"] for u in units)
    false_rollbacks = sum(u["right"] for u in rolled)
    caught = sum(u["wrong"] for u in rolled)
    assert right + wrong == len(units)
    return {
        "units": len(units),
        "correct": right - false_rollbacks + caught,
        "false_rollbacks": false_rollbacks,
        "caught": caught,
    }


@pytest.mark.full_data
@pytest.mark.parametrize("name", ["fresh2", "fresh"])
def test_the_package_judge_reproduces_the_recorded_fresh_scores(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = _missing_inputs(name)
    if missing:
        pytest.skip(f"{name}: {len(missing)} inputs absent, first {missing[0]}")
    fb, fe = _load(name, monkeypatch)
    lines = (fe.OUT / LABEL_FILE).read_text(encoding="utf-8").splitlines()
    labels = {r["sha"]: r for r in map(json.loads, lines)}

    rows = {r["id"]: r for r in fb.rows()}
    built: dict[str, Any] = {}
    chat = Recorded(labels)
    verifier = JudgedVerifier(Judge(chat))
    assert verifier.config == STRICT_FIGURES
    verdicts: dict[str, SentenceVerdict] = {}
    errors = 0
    for answer_key, answer in sorted(fb.answers().items()):
        row = rows[answer_key.split(":")[0]]
        if row["id"] not in built:
            built[row["id"]] = fb.premise(row)
        out = verifier.check_text(built[row["id"]], answer["text"], query=row["query"])
        verdicts |= {f"{answer_key}:{n}": v for n, v in enumerate(out)}
        errors += sum(c["error"] is not None for c in verifier.calls)

    assert sorted(chat.unknown) == []
    assert len(chat.sent) == SENT[name]
    assert errors == 0

    us = fe.units(merged=True)
    graded = fe.merged_grades(us)
    unmatched = [
        u["key"] for u in us if u["key"] not in verdicts or verdicts[u["key"]].text != u["sentence"]
    ]
    assert unmatched == []
    assert len(verdicts) == len(us)
    units = [
        {**u, "right": graded[u["key"]] == "yes", "wrong": graded[u["key"]] == "no"} for u in us
    ]
    units = [u for u in units if u["right"] or u["wrong"]]
    cells = {"total": _cell(units, verdicts)}
    for domain, cell in DOMAINS.items():
        part = _cell([u for u in units if u["domain"] == domain], verdicts)
        cells[cell] = {k: part[k] for k in ("units", "false_rollbacks", "caught")}
    assert cells == EXPECTED[name]
