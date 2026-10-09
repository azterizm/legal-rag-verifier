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


def units() -> list[dict[str, Any]]:
    """Every sentence of every fresh answer, with the answer so far; ``key`` = ``id:mode:n``."""
    rows = {r["id"]: r for r in fb.rows()}
    out = []
    for key, a in sorted(fb.answers().items()):
        row_id, mode = key.split(":")
        done: list[str] = []
        for n, s in enumerate(split_sentences(a["text"])):
            out.append(
                {
                    "key": f"{key}:{n}",
                    "id": row_id,
                    "mode": mode,
                    "domain": rows[row_id]["domain"],
                    "query": rows[row_id]["query"],
                    "prefix": " ".join(done),
                    "sentence": s.text,
                }
            )
            done.append(s.text)
    return out


def premises(us: Sequence[Mapping[str, Any]]) -> dict[str, Premise]:
    rows = {r["id"]: r for r in fb.rows()}
    built = {i: fb.premise(rows[i]) for i in {u["id"] for u in us}}
    return {u["key"]: built[u["id"]] for u in us}


def recorded() -> tuple[list[dict[str, Any]], dict[str, Premise], list[dict[str, Any]]]:
    us = units()
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
