"""Stop 47: the fresh test, scored once (docs/GRID.md § Stop 47).

The judges label the fresh clauses before your grades exist (no grade is in any prompt); this
script scores every candidate once, from the committed labels, score tables and your grades.

  uv run python scripts/fresh_eval.py record    # the clauses each fresh sentence sends to the check
  uv run python scripts/fresh_eval.py gemini    # Gemini per clause (router)
  uv run --with modal modal run scripts/modal_distill.py::fresh_judges   # V0, Qwen, K2, student
  uv run python scripts/fresh_eval.py report    # after your grades → results/fresh/report.json
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "batteries/verifier"))

import auditor_judge as aj  # type: ignore[import-not-found]  # noqa: E402
import fresh_battery as fb  # type: ignore[import-not-found]  # noqa: E402

from legal_rag_verifier.premise import Premise  # noqa: E402
from legal_rag_verifier.segmenter import split_sentences  # noqa: E402

OUT = ROOT / "results/fresh"
LABELS = OUT / "labels"


_LIST_ITEM = re.compile(r"(\d{1,3}\.)\s+(\S.*)", re.DOTALL)


def as_graded(sentence: str) -> list[str]:
    """The sentence as the sheet split it: until stop 52 the segmenter made a list number
    ("1.") a sentence of its own."""
    m = _LIST_ITEM.fullmatch(sentence)
    return [m[1], m[2]] if m else [sentence]


def units(*, merged: bool = False) -> list[dict[str, Any]]:
    """Every sentence of every fresh answer, with the answer so far; ``key`` = ``id:mode:n``.

    By default the units are the ones you graded. ``merged=True`` gives the segmenter's sentences
    since stop 52 (a list number stays with its item), each with the graded units it covers in
    ``parts``."""
    rows = {r["id"]: r for r in fb.rows()}
    out = []
    for key, a in sorted(fb.answers().items()):
        row_id, mode = key.split(":")
        base = {
            "id": row_id,
            "mode": mode,
            "domain": rows[row_id]["domain"],
            "query": rows[row_id]["query"],
        }
        done: list[str] = []
        graded = 0
        for n, s in enumerate(split_sentences(a["text"])):
            pieces = as_graded(s.text)
            parts = [f"{key}:{graded + i}" for i in range(len(pieces))]
            graded += len(pieces)
            if merged:
                unit = {"key": f"{key}:{n}", "prefix": " ".join(done), "sentence": s.text}
                out.append({**base, **unit, "parts": parts})
                done.append(s.text)
                continue
            for part, piece in zip(parts, pieces, strict=True):
                out.append({**base, "key": part, "prefix": " ".join(done), "sentence": piece})
                done.append(piece)
    return out


def premises(us: Sequence[Mapping[str, Any]]) -> dict[str, Premise]:
    rows = {r["id"]: r for r in fb.rows()}
    built = {i: fb.premise(rows[i]) for i in {u["id"] for u in us}}
    return {u["key"]: built[u["id"]] for u in us}


def recorded(
    *, merged: bool = False
) -> tuple[list[dict[str, Any]], dict[str, Premise], list[dict[str, Any]]]:
    us = units(merged=merged)
    built = premises(us)
    return us, built, aj.record(us, built)


def assert_blind(us: Sequence[Mapping[str, Any]], asked: Mapping[str, str]) -> None:
    """No prompt holds a question (or, by construction, a grade); each matches its key."""
    queries = {u["query"] for u in us}
    bad = [k for k, v in asked.items() if aj.prompt_key(v) != k or any(q in v for q in queries)]
    if bad:
        raise RuntimeError(f"{len(bad)} fresh prompts hold more than their inputs")


def read(name: str) -> dict[str, dict[str, Any]]:
    path = LABELS / f"{name}.jsonl"
    if not path.exists():
        return {}
    return {r["sha"]: r for r in map(json.loads, path.read_text(encoding="utf-8").splitlines())}


def gemini() -> None:
    import teachers  # type: ignore[import-not-found]  # noqa: PLC0415

    us, _, rec = recorded()
    asked = aj.requests(rec)
    assert_blind(us, asked)
    have = {k for k, v in read("gemini").items() if v["label"] in aj.LABELS}
    todo = {k: v for k, v in asked.items() if k not in have}
    print(f"fresh gemini: {len(asked)} prompts, {len(todo)} to ask", flush=True)
    path = LABELS / "gemini.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)

    def done(sha: str, result: Mapping[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"sha": sha, **result}, ensure_ascii=False) + "\n")

    aj.judge_all(todo, teachers.router_chat(teachers.TEACHERS["gemini"]), 6, done)


def grades() -> dict[str, str]:
    """Sentence key → yes / no / unsure, from your graded sheet and its key."""
    key = json.loads((OUT / "key.json").read_text(encoding="utf-8"))
    with (OUT / "grades.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = {}
    for r in rows:
        k = key[r["item"]]
        out[f"{k['id']}:{k['mode']}:{k['sentence']}"] = r["correct"].strip().lower()
    return out


def merged_grades(us: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """A grade per merged unit: no if any graded part is no, else unsure if any is, else yes."""
    graded = grades()
    out = {}
    for u in us:
        parts = {graded[k] for k in u["parts"]}
        out[u["key"]] = "no" if "no" in parts else "unsure" if "unsure" in parts else "yes"
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["record", "gemini", "report"])
    command = parser.parse_args().command
    if command == "record":
        us, _, rec = recorded()
        asked = aj.requests(rec)
        assert_blind(us, asked)
        print(
            json.dumps(
                {
                    "sentences": len(us),
                    "reach_entailment": sum(bool(r["calls"]) for r in rec),
                    "prompts": len(asked),
                    "pairs": len(aj.pairs(rec)),
                }
            )
        )
    elif command == "gemini":
        gemini()
    else:
        from fresh_report import main as report  # type: ignore[import-not-found]  # noqa: PLC0415

        report()


if __name__ == "__main__":
    main()
