"""Stop 63: smaller judges trained on Qwen 27B's short-reply labels (docs/GRID.md § Stop 63).

The training pool is stop 45's (472 sources disjoint from every test). The teacher labels each
clause with the ``short`` prompt of stop 61; a student learns the prompt → reply mapping.

  uv run --with modal modal run scripts/modal_distill.py::pool_labels      # the teacher (Modal)
  uv run python scripts/students.py dataset     # → results/distill/students/
  uv run --with modal modal run scripts/modal_distill.py::train_small --student minicpm5-1b
  uv run python scripts/students.py validation  # → results/distill/students/validation.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import auditor_judge as aj  # type: ignore[import-not-found]  # noqa: E402
import distill_data as dd  # type: ignore[import-not-found]  # noqa: E402
import teachers  # type: ignore[import-not-found]  # noqa: E402

TEACHER = "qwen27-ar4"
STUDENTS = ("minicpm5-1b-student", "minicpm5-1b-student2", "gemma4-e4b-student")
POOL2_UNITS = ROOT / "results/distill/pool2/units.jsonl"  # stop 64; every clause of it trains
OUT = ROOT / "results/distill/students"


def label_path(name: str) -> Path:
    """Labels of one model on the pool's short prompts."""
    return Path(teachers.label_path(f"pool-short-{name}"))


def clauses() -> list[dict[str, str]]:
    """Every pool clause once: its short prompt, the prompt's hash, its source and its split."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    second = []
    if POOL2_UNITS.exists():
        second = [json.loads(x) for x in POOL2_UNITS.read_text(encoding="utf-8").splitlines()]
    for pool, units in (("first", dd.units()), ("second", second)):
        for u in units:
            split = dd.split_of(u["id"]) if pool == "first" else "train"
            for clause, candidates in u["calls"]:
                user = aj.short_prompt(clause, candidates, u["prefix"])
                sha = aj.prompt_key(user)
                if sha not in seen:
                    seen.add(sha)
                    row = {"sha": sha, "user": user, "source": u["id"], "split": split}
                    out.append({**row, "pool": pool})
    return out


def requests(split: str = "") -> dict[str, str]:
    """``{sha: short prompt}`` for the pool, or for one split of it."""
    return {c["sha"]: c["user"] for c in clauses() if not split or c["split"] == split}


def labels(name: str) -> dict[str, dict[str, Any]]:
    """Valid labels of one model, the last kept per prompt."""
    path = label_path(name)
    if not path.exists():
        return {}
    rows = map(json.loads, path.read_text(encoding="utf-8").splitlines())
    return {r["sha"]: r for r in rows if r["label"] in aj.LABELS}


def todo(name: str, split: str = "") -> dict[str, str]:
    have = labels(name)
    return {k: v for k, v in requests(split).items() if k not in have}


def reply(label: dict[str, Any]) -> str:
    """The target a student writes: the teacher's label and passage, as the short reply asks."""
    return json.dumps({"label": label["label"], "passage": int(label.get("passage") or 0)})


def dataset() -> dict[str, Any]:
    teacher = labels(TEACHER)
    rows: dict[str, list[dict[str, Any]]] = {"train": [], "validation": []}
    stats: Counter[str] = Counter()
    for c in clauses():
        label = teacher.get(c["sha"])
        if label is None:
            stats["no teacher label"] += 1
            continue
        rows[c["split"]].append(
            {
                "sha": c["sha"],
                "source": c["source"],
                "messages": [
                    {"role": "system", "content": aj.SYSTEM},
                    {"role": "user", "content": c["user"]},
                    {"role": "assistant", "content": reply(label)},
                ],
            }
        )
        stats[f"{c['split']} {label['label']}"] += 1
        stats[f"{c['split']} from the {c['pool']} pool"] += 1
    OUT.mkdir(parents=True, exist_ok=True)
    for split, examples in rows.items():
        text = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in examples)
        (OUT / f"{split}.jsonl").write_text(text, encoding="utf-8")
        stats[f"{split} examples"] = len(examples)
        stats[f"{split} sources"] = len({e["source"] for e in examples})
    out = {"teacher": TEACHER, "prompt": "short", **dict(sorted(stats.items()))}
    (OUT / "dataset.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return out


def validation() -> dict[str, Any]:
    """Y1: on the validation clauses, how often each student gives its teacher's label."""
    teacher = labels(TEACHER)
    keys = [k for k in requests("validation") if k in teacher]
    out: dict[str, Any] = {"validation_clauses": len(keys)}
    out["teacher_labels"] = dict(Counter(teacher[k]["label"] for k in keys))
    for name in STUDENTS:
        mine = labels(name)
        both = [k for k in keys if k in mine]
        if not both:
            continue
        out[name] = {
            "labelled": len(both),
            "same_label": sum(mine[k]["label"] == teacher[k]["label"] for k in both),
            "same_label_and_passage": sum(
                mine[k]["label"] == teacher[k]["label"]
                and int(mine[k].get("passage") or 0) == int(teacher[k].get("passage") or 0)
                for k in both
            ),
            "labels": dict(Counter(mine[k]["label"] for k in both)),
            "differ": dict(
                Counter(
                    f"teacher {teacher[k]['label']} / student {mine[k]['label']}"
                    for k in both
                    if mine[k]["label"] != teacher[k]["label"]
                )
            ),
        }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "validation.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["count", "dataset", "validation"])
    command = parser.parse_args().command
    if command == "count":
        split = Counter(c["split"] for c in clauses())
        print(json.dumps({"clauses": sum(split.values()), **split, "to label": len(todo(TEACHER))}))
    elif command == "dataset":
        print(json.dumps(dataset(), indent=1))
    else:
        print(json.dumps(validation(), indent=1))


if __name__ == "__main__":
    main()
