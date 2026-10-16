"""Stop 72 (docs/GRID.md § Stop 72): the 27B as generator and judge, the source in the prompt, on
stop 71's questions; scored against stop 71's frontier arms and the 7B loop.

  uv run --with modal modal run scripts/modal_distill.py::live72
  uv run python scripts/live68_grade.py sheet --stop 72
  uv run python scripts/live68_grade.py grade opus55 --stop 72 --opus-stop 45
  uv run python scripts/live68_grade.py leftover --stop 72
  uv run python scripts/live72.py report              # → results/live72_report.json

Answers and traces quote statute text and stay git-ignored (``results/live72/``).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import live68 as l68  # type: ignore[import-not-found]  # noqa: E402

OUT = ROOT / "results/live72"
REPORT = ROOT / "results/live72_report.json"
SETS = l68.SETS
ARMS = ("none", "turn")
GENERATORS = ("qwen27",)
items = l68.items
rows = l68.rows
key = l68.key
read_jsonl = l68.read_jsonl


def path(generator: str) -> Path:
    return OUT / f"{generator}.jsonl"


def append(generator: str, records: Sequence[Mapping[str, Any]]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with path(generator).open("a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def done(generator: str) -> dict[str, dict[str, Any]]:
    return {r["key"]: r for r in read_jsonl(path(generator)) if r.get("text") is not None}


def wrong_answers(
    table: Mapping[str, Mapping[str, Any]], prefix: str, questions: Sequence[str], arm: str
) -> list[bool]:
    return [table[f"{prefix}:{q}:{arm}"]["wrong"] > 0 for q in questions]


def report() -> dict[str, Any]:
    import live68_grade as lg  # type: ignore[import-not-found]  # noqa: PLC0415
    import live70  # type: ignore[import-not-found]  # noqa: PLC0415
    import sota71  # type: ignore[import-not-found]  # noqa: PLC0415

    lg.use(72)
    grades = lg.grades_by_sentence()
    mine = lg.scored(grades)
    lg.STORE = sota71
    frontier = lg.scored(grades)
    lg.STORE = live70
    seven = {k: v for k, v in lg.scored(grades).items() if k.startswith("qwen7:")}
    questions = [f"{s}:{r['id']}" for s in SETS for r in rows(s)]
    arms = {f"27B {a}": ("qwen27", a, mine) for a in ARMS} | {
        "7B loop (stop 70)": ("qwen7", "turn", seven)
    }
    arms |= {g: (g, "none", frontier) for g in sota71.GENERATORS}
    out: dict[str, Any] = {"arms": {}, "against_frontier": {}, "secondary": {}}
    for title, (gen, arm, table) in arms.items():
        rows_ = [table[f"{gen}:{q}:{arm}"] for q in questions]
        out["arms"][title] = {**lg.summary(rows_), "empty": sum(r["sentences"] == 0 for r in rows_)}
        out["arms"][title]["rollbacks"] = sum(r["rollbacks"] or 0 for r in rows_)
    loop = wrong_answers(mine, "qwen27", questions, "turn")
    for g in sota71.GENERATORS:
        theirs = wrong_answers(frontier, g, questions, "none")
        diffs = [int(a) - int(b) for a, b in zip(loop, theirs, strict=True)]
        low, high = sota71.bootstrap(diffs)
        out["against_frontier"][g] = {
            "difference": round(sum(diffs) / len(diffs), 4),
            "interval_95": [low, high],
            "near": bool(high <= sota71.MARGIN),
            "only_27b_wrong": sum(d == 1 for d in diffs),
            "only_frontier_wrong": sum(d == -1 for d in diffs),
        }
    others = {
        "27B none": wrong_answers(mine, "qwen27", questions, "none"),
        "7B loop": wrong_answers(seven, "qwen7", questions, "turn"),
    }
    for name, theirs in others.items():
        only_loop = sum(a and not b for a, b in zip(loop, theirs, strict=True))
        only_other = sum(b and not a for a, b in zip(loop, theirs, strict=True))
        out["secondary"][f"27B turn against {name}"] = {
            "only_27b_turn_wrong": only_loop,
            "only_other_wrong": only_other,
            "p": round(lg.mcnemar(only_loop, only_other), 4),
        }
    REPORT.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    if sys.argv[1:] != ["report"]:
        raise SystemExit(__doc__)
    out = report()
    print(json.dumps({k: out[k] for k in ("against_frontier", "secondary")}, indent=1))
