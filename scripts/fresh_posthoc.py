"""Stop 47, readings added after the scoring ran (docs/GRID.md § Stop 47: after the run).

Not pre-registered. They explain the scored table and change none of it.

uv run python scripts/fresh_posthoc.py      # → results/fresh/posthoc.json
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import auditor_judge as aj  # type: ignore[import-not-found]  # noqa: E402
import fresh_eval as fe  # type: ignore[import-not-found]  # noqa: E402
import fresh_report as fr  # type: ignore[import-not-found]  # noqa: E402

JUDGES = ("gemini", "qwen27-low", "qwen27-nothink", "k2-low", "k2-student")
SHEETS = {"gemini whole sheet": "gemini-grades.txt", "opus 5.5 whole sheet": "opus-grades.txt"}
_GRADE = re.compile(r'"(Q\d+[AB]\d+)":\s*(?:\{\s*correct:\s*)?"(yes|no|unsure)"')
_MARKER = re.compile(r"[^A-Za-z]*")


def sheet_grades(name: str) -> dict[str, str]:
    """Item → yes / no / unsure from a whole-sheet grading, keyed like ``fe.grades``."""
    key = json.loads((fe.OUT / "key.json").read_text(encoding="utf-8"))
    out = {}
    for item, grade in _GRADE.findall((fe.OUT / name).read_text(encoding="utf-8")):
        k = key[item]
        out[f"{k['id']}:{k['mode']}:{k['sentence']}"] = grade
    return out


def main() -> None:
    graded = fe.grades()
    us, built, rec = fe.recorded()
    by_key = {u["key"]: u for u in us}
    units = [
        {**by_key[k], "right": g == "yes", "wrong": g == "no"}
        for k, g in graded.items()
        if g != "unsure"
    ]
    report: dict[str, Any] = {}
    v0 = aj.replay(
        us, built, aj.TableScorer("v0", json.loads((fe.OUT / "scores/v0.json").read_text()))
    )
    base = fr.score(units, v0)

    # 1. Every judge under both placements, so the judge and the placement can be read apart.
    arms: dict[str, dict[str, dict[str, Any]]] = {"V0": v0}
    for name in JUDGES:
        for placement, config in (("replace", aj.DEFAULT), ("strict", aj.STRICT)):
            arms[f"{name} ({placement})"] = aj.replay(
                us, built, aj.JudgeScorer(name, fe.read(name)), config
            )
    report["both_placements"] = {}
    for name, verdicts in arms.items():
        s = fr.score(units, verdicts)
        for group in ("software", "statutes", "total"):
            s[group]["passes_bar"] = aj.passes_bar(s[group], base[group])
        report["both_placements"][name] = s

    # 2. Sentences with no letters (list numbers split off by the segmenter): no claim to check.
    markers = [u for u in units if _MARKER.fullmatch(u["sentence"])]
    keep = [u for u in units if not _MARKER.fullmatch(u["sentence"])]
    report["no_claim_sentences"] = {
        "count": len(markers),
        "graded": dict(Counter("yes" if u["right"] else "no" for u in markers)),
        "answers": sorted({f"{u['id']}:{u['mode']}" for u in markers}),
        "rolled_back": {
            name: sum(fr._rolled(verdicts[u["key"]]) for u in markers)
            for name, verdicts in arms.items()
        },
        "without_them": {
            name: fr.score(keep, verdicts)["total"] for name, verdicts in arms.items()
        },
    }

    # 3. Your side experiment: one prompt with the whole sheet, read as an auditor (no = rollback).
    report["whole_sheet"] = {}
    for name, path in SHEETS.items():
        theirs = sheet_grades(path)
        both = [k for k in graded if k in theirs]
        differ = Counter(
            f"you {graded[k]} / model {theirs[k]}" for k in both if graded[k] != theirs[k]
        )
        verdicts = {
            k: {"verdict": "EMIT" if theirs.get(k) == "yes" else "ROLLBACK", "reasons": []}
            for k in by_key
        }
        report["whole_sheet"][name] = {
            "items": len(both),
            "same": sum(graded[k] == theirs[k] for k in both),
            "differ": dict(differ),
            "as_auditor": fr.score(units, verdicts),
        }

    # 4. F4, time added per answer: the sum of an answer's clause latencies in the bulk runs.
    report["ms_added_per_answer"] = {}
    for name in JUDGES:
        labels = fe.read(name)
        per_answer: Counter[str] = Counter()
        for u, r in zip(us, rec, strict=True):
            for clause, cands in r["calls"]:
                sha = aj.prompt_key(aj.user_prompt(clause, cands, r["prefix"]))
                per_answer[f"{u['id']}:{u['mode']}"] += labels[sha].get("ms") or 0
        ms = sorted(per_answer.values())
        report["ms_added_per_answer"][name] = {
            "answers": len(ms),
            "p50_ms": round(ms[len(ms) // 2]),
            "p95_ms": round(ms[int(0.95 * len(ms))]),
        }

    (fe.OUT / "posthoc.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    for name, s in report["both_placements"].items():
        cells = "  ".join(
            f"{g}: {s[g]['false_rollbacks']}/{s[g]['caught']} {s[g]['accuracy']}"
            + ("*" if s[g].get("passes_bar") else "")
            for g in ("software", "statutes", "total")
        )
        print(f"{name:28} {cells}")
    print(json.dumps(report["ms_added_per_answer"]))
    for name, s in report["whole_sheet"].items():
        t = s["as_auditor"]["total"]
        print(name, s["same"], "of", s["items"], s["differ"], t)


if __name__ == "__main__":
    main()
