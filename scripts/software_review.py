"""Stop 37: your blind grading sheet for the software battery, and the readings (docs/GRID.md).

- **Part A**, per state 4B and 4B-inject-v2 share at their first rollback (same answer so far, same
  rejected draft): the rejected draft and the two first retries. Columns ``correct``, ``answers``,
  ``reads_well``.
- **Part B**, per question: the plain answer (4D's first draft, before any check), 4B's final answer
  and 4B-inject-v2's final answer. Columns ``correct``, ``answers``.

Within a state or question, identical texts are shown once. Questions are in a seeded random
order and each one's texts are shuffled and lettered; the key is git-ignored.

  uv run python scripts/software_review.py build      # results/software/review/: sheet, grades, key
  uv run python scripts/software_review.py report     # after your grades are committed
  uv run python scripts/software_review.py report --compare other_grades.csv   # kappa per column
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from grid_judge import kappa  # type: ignore[import-not-found]  # noqa: E402
from replay_report import holm, sig  # type: ignore[import-not-found]  # noqa: E402
from replay_states import (  # type: ignore[import-not-found]  # noqa: E402
    load,
    mcnemar,
    shared_states,
)
from rollback_review import wilson  # type: ignore[import-not-found]  # noqa: E402
from software_battery import premise, rows  # type: ignore[import-not-found]  # noqa: E402

from legal_rag_verifier.engine import render_premise  # noqa: E402

RESULTS = ROOT / "results/software"
OUT = RESULTS / "review"
SEED = 20261008
LETTERS = "ABCDEFGH"
S1_BAR = 0.8  # set before the run (GRID § Stop 37)
ALPHA = 0.05
MIN_STATES = 10  # fewer shared states: S1 and S2 reported as counts, not read
YES_NO = ("yes", "no")

INSTRUCTIONS = """\
Grade every lettered text in `grades.csv`. Judge only against the documentation shown, not what
you know about the tool. Grade each text on its own, not against the others. `note` is optional.

- `correct`: "yes" if every claim in the text matches the documentation shown; "no" if any claim is
  wrong or not in the documentation.
- `answers`: "yes" if the text helps answer the question asked; "no" if it is about something else.
- `reads_well` (Part A only): "yes" if it is a complete sentence that continues the answer so far;
  "no" for pasted labels or headings, fragments, or a repeat of the answer so far."""


def _text(retry: Mapping[str, Any] | None) -> str:
    return "" if retry is None else (retry["verdict"].get("text") or "").strip()


def _verdict(retry: Mapping[str, Any] | None) -> str:
    return "NONE" if retry is None else str(retry["verdict"]["verdict"])


def lettered(texts: Sequence[tuple[str, dict[str, Any]]]) -> list[tuple[str, list[dict[str, Any]]]]:
    """Texts with their sources; identical texts merged, empty texts dropped, order kept."""
    merged: dict[str, list[dict[str, Any]]] = {}
    for text, source in texts:
        if text:
            merged.setdefault(text, []).append(source)
    return list(merged.items())


def part_a(a: dict[str, Any], b: dict[str, Any]) -> list[dict[str, Any]]:
    """Shared first-rollback states of 4B (a) and 4B-inject-v2 (b)."""
    states, _ = shared_states(a, b)
    return [
        {
            "id": s.id,
            "prefix": s.committed.strip(),
            "texts": lettered(
                [
                    (s.rejected.strip(), {"arm": "rejected", "verdict": "ROLLBACK"}),
                    (_text(s.a_retry), {"arm": "4B", "verdict": _verdict(s.a_retry)}),
                    (_text(s.b_retry), {"arm": "v2", "verdict": _verdict(s.b_retry)}),
                ]
            ),
            "empty": [arm for arm, r in (("4B", s.a_retry), ("v2", s.b_retry)) if not _text(r)],
        }
        for s in states
    ]


def part_b(
    plain: dict[str, Any], a: dict[str, Any], b: dict[str, Any], ids: Sequence[str]
) -> list[dict[str, Any]]:
    return [
        {
            "id": key,
            "texts": lettered(
                [
                    (plain[key]["attempts"][0]["text"].strip(), {"arm": "plain"}),
                    (a[key]["answer"].strip(), {"arm": "4B"}),
                    (b[key]["answer"].strip(), {"arm": "v2"}),
                ]
            ),
        }
        for key in ids
    ]


def build() -> None:
    a = load(RESULTS / "4B.jsonl")
    b = load(RESULTS / "4B-inject-v2.jsonl")
    plain = load(RESULTS / "4D.jsonl")
    battery = {r["id"]: r for r in rows()}
    rng = random.Random(SEED)  # noqa: S311 - a reproducible order, not a secret
    states = part_a(a, b)
    questions = part_b(plain, a, b, [r["id"] for r in rows()])
    for group in (states, questions):
        rng.shuffle(group)
        for entry in group:
            rng.shuffle(entry["texts"])
    lines = ["# Stop 37 grading sheet (blind)", "", INSTRUCTIONS]
    key: list[dict[str, Any]] = []
    grades: list[list[str]] = []
    for part, group in (("A", states), ("B", questions)):
        title = (
            "Part A: one rejected sentence and its retries, each read after the answer so far"
            if part == "A"
            else "Part B: whole answers"
        )
        lines += ["", f"# {title}"]
        for n, entry in enumerate(group, 1):
            row = battery[entry["id"]]
            lines += [
                "",
                "---",
                "",
                f"## {part}{n:02d}. {row['query']}",
                "",
                "**Documentation:**",
                "",
                *[
                    f"> {line}" if line else ">"
                    for line in render_premise(premise(row)).splitlines()
                ],
                "",
            ]
            if part == "A":
                lines += [f"**Answer so far:** {entry['prefix'] or '(nothing yet)'}", ""]
            for i, (text, sources) in enumerate(entry["texts"]):
                item = f"{part}{n:02d}{LETTERS[i]}"
                lines += [f"**{item}.** {text}", ""]
                key.append({"item": item, "part": part, "id": entry["id"], "sources": sources})
                grades.append([item, "", "", "" if part == "A" else "n/a", ""])
            if part == "A" and entry["empty"]:
                key.append({"item": None, "part": "A", "id": entry["id"], "empty": entry["empty"]})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sheet.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    key_text = json.dumps(key, indent=1, ensure_ascii=False) + "\n"
    (OUT / "key.json").write_text(key_text, encoding="utf-8")
    path = OUT / "grades.csv"
    if not path.exists():  # never overwrite your grades
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["item", "correct", "answers", "reads_well", "note"])
            writer.writerows(grades)
    print(
        json.dumps(
            {
                "part_a_states": len(states),
                "part_a_items": sum(k["part"] == "A" and k["item"] is not None for k in key),
                "part_b_questions": len(questions),
                "part_b_items": sum(k["part"] == "B" for k in key),
                "key_sha256": hashlib.sha256(key_text.encode()).hexdigest(),
            },
            indent=1,
        )
    )


def read_grades(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8") as f:
        return {
            r["item"]: {k: (v or "").strip().lower() for k, v in r.items()}
            for r in csv.DictReader(f)
        }


def good_retry(g: Mapping[str, str] | None) -> bool:
    return g is not None and g["correct"] == g["answers"] == g["reads_well"] == "yes"


def good_answer(g: Mapping[str, str] | None) -> bool:
    return g is not None and g["correct"] == g["answers"] == "yes"


def per_arm(
    key: Sequence[Mapping[str, Any]], grades: Mapping[str, dict[str, str]], part: str
) -> dict[str, dict[str, dict[str, Any]]]:
    """Per state or question: each arm's grades (None for an arm with no text) and verdict."""
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for k in key:
        if k["part"] != part:
            continue
        if k["item"] is None:
            for arm in k["empty"]:
                out.setdefault(k["id"], {})[arm] = {"grade": None, "verdict": "EMPTY"}
            continue
        for source in k["sources"]:
            out.setdefault(k["id"], {})[source["arm"]] = {
                "grade": grades[k["item"]],
                "verdict": source.get("verdict"),
            }
    return out


def paired(xs: Sequence[bool], ys: Sequence[bool]) -> dict[str, Any]:
    only_x = sum(x and not y for x, y in zip(xs, ys, strict=True))
    only_y = sum(y and not x for x, y in zip(xs, ys, strict=True))
    return {
        "a": sum(xs),
        "b": sum(ys),
        "only_a": only_x,
        "only_b": only_y,
        "p": sig(mcnemar(only_x, only_y)),
    }


def score(key: Sequence[Mapping[str, Any]], grades: Mapping[str, dict[str, str]]) -> dict[str, Any]:
    states = per_arm(key, grades, "A")
    questions = per_arm(key, grades, "B")
    n = len(states)
    wrong = sum(s["rejected"]["grade"]["correct"] == "no" for s in states.values())
    s2 = paired(
        [good_retry(s["v2"]["grade"]) for s in states.values()],
        [good_retry(s["4B"]["grade"]) for s in states.values()],
    )
    s3 = {
        f"{cell}_vs_plain": paired(
            [good_answer(q[cell]["grade"]) for q in questions.values()],
            [good_answer(q["plain"]["grade"]) for q in questions.values()],
        )
        for cell in ("4B", "v2")
    }
    adjusted = holm({k: v["p"] for k, v in s3.items()})
    retries: dict[str, Any] = {}
    for arm in ("rejected", "4B", "v2"):
        entries = [s[arm] for s in states.values()]
        graded = [e["grade"] for e in entries if e["grade"] is not None]
        accepted = [e["grade"] for e in entries if e["verdict"] == "EMIT"]
        retries[arm] = {
            "no_text": n - len(graded),
            "correct": sum(g["correct"] == "yes" for g in graded),
            "answers": sum(g["answers"] == "yes" for g in graded),
            "reads_well": sum(g["reads_well"] == "yes" for g in graded),
            "good": sum(good_retry(g) for g in graded),
            "auditor_accepted": len(accepted),
            "accepted_not_good": sum(not good_retry(g) for g in accepted),
            "accepted_not_correct": sum(g["correct"] == "no" for g in accepted),
        }
    answers = {
        arm: {
            "correct": sum(q[arm]["grade"]["correct"] == "yes" for q in questions.values()),
            "answers": sum(q[arm]["grade"]["answers"] == "yes" for q in questions.values()),
            "good": sum(good_answer(q[arm]["grade"]) for q in questions.values()),
        }
        for arm in ("plain", "4B", "v2")
    }
    return {
        "shared_states": n,
        "S1_rejections_real": {
            "wrong": wrong,
            "share": round(wrong / n, 4) if n else None,
            "wilson95": wilson(wrong, n),
            "holds": bool(n) and wrong / n >= S1_BAR,
            "readable": n >= MIN_STATES,
        },
        "S2_good_retry_v2_vs_4B": {
            **s2,
            "holds": s2["a"] > s2["b"] and s2["p"] < ALPHA,
            "readable": n >= MIN_STATES,
        },
        "S3_good_answer_vs_plain_holm": {
            name: {**s3[name], **adj, "holds": s3[name]["a"] > s3[name]["b"] and adj["holds"]}
            for name, adj in adjusted.items()
        },
        "part_a": retries,
        "part_b": answers,
    }


def compare(
    mine: Mapping[str, dict[str, str]], other: Mapping[str, dict[str, str]]
) -> dict[str, Any]:
    """Cohen's kappa per column between two sets of grades on the same items."""
    out: dict[str, Any] = {}
    for column in ("correct", "answers", "reads_well"):
        pairs = [
            (mine[i][column] == "yes", other[i][column] == "yes")
            for i in mine
            if i in other and mine[i][column] in YES_NO and other[i][column] in YES_NO
        ]
        out[column] = {
            "pairs": len(pairs),
            "agreement": round(sum(x == y for x, y in pairs) / len(pairs), 4) if pairs else None,
            "kappa": kappa(pairs),
        }
    return out


def report(other: Path | None) -> dict[str, Any]:
    key = json.loads((OUT / "key.json").read_text(encoding="utf-8"))
    grades = read_grades(OUT / "grades.csv")
    missing = [k["item"] for k in key if k["item"] and not grades.get(k["item"], {}).get("correct")]
    if missing:
        raise ValueError(f"ungraded items: {missing[:5]}")
    out: dict[str, Any] = {"grades": "results/software/review/grades.csv", **score(key, grades)}
    if other is not None:
        out["agreement_with"] = {"grades": str(other), **compare(grades, read_grades(other))}
    (OUT / "report.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build")
    rep = sub.add_parser("report")
    rep.add_argument("--compare", type=Path, default=None)
    args = parser.parse_args()
    if args.command == "build":
        build()
    else:
        print(json.dumps(report(args.compare), indent=1))


if __name__ == "__main__":
    main()
