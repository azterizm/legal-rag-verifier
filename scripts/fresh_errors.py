"""Where the judges fail on the fresh test (docs/GRID.md § Where the judges fail).

Not pre-registered. The units and labels are the ones stops 47 to 51 were scored from, under
Replace strict. Sentences the claim check rolls back before the judge are left out.

uv run python scripts/fresh_errors.py      # → results/fresh_arms/errors.json
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import auditor_judge as aj  # type: ignore[import-not-found]  # noqa: E402
import fresh_eval as fe  # type: ignore[import-not-found]  # noqa: E402
import fresh_posthoc as fp  # type: ignore[import-not-found]  # noqa: E402
import fresh_report as fr  # type: ignore[import-not-found]  # noqa: E402
import teacher_pro as tp  # type: ignore[import-not-found]  # noqa: E402

JUDGES = ("opus55", "gemini-pro-low", "gemini", "qwen27-nothink")
FRONTIER = JUDGES[:3]
OUT = ROOT / "results/fresh_arms"


def main() -> None:
    graded = fe.grades()
    us, built, rec = fe.recorded()
    by_key = {u["key"]: u for u in us}
    calls = {r["key"]: r for r in rec}
    units = {
        k: {**by_key[k], "right": g == "yes", "wrong": g == "no"}
        for k, g in graded.items()
        if g != "unsure" and not calls[k]["claim_rollback"]
    }
    keys = list(aj.requests(rec))
    report: dict[str, Any] = {"sentences": len(units), "judges": {}}
    errors: dict[str, set[str]] = {}
    for name in JUDGES:
        labels = tp.filled(fe.read(name), keys)[0]
        verdicts = aj.replay(us, built, aj.JudgeScorer(name, labels), aj.STRICT)
        false = [k for k, u in units.items() if u["right"] and fr._rolled(verdicts[k])]
        missed = [k for k, u in units.items() if u["wrong"] and not fr._rolled(verdicts[k])]
        errors[name] = set(false) | set(missed)

        def given(k: str, labels: dict[str, dict[str, Any]] = labels) -> list[str]:
            r = calls[k]
            return [
                labels[aj.prompt_key(aj.user_prompt(c, cands, r["prefix"]))]["label"]
                for c, cands in r["calls"]
            ]

        report["judges"][name] = {
            "false_rollbacks": len(false),
            "missed": len(missed),
            # a sentence can hold more than one clause; each label that is not "supported" counts
            "false_rollback_labels": dict(
                Counter(lab for k in false for lab in given(k) if lab != "supported")
            ),
            "missed_closed_book": sum(units[k]["mode"] == "closed" for k in missed),
            "missed_with_source": sum(units[k]["mode"] == "source" for k in missed),
        }
    wrong_for = Counter(sum(k in errors[j] for j in FRONTIER) for k in units)
    shared = sorted(k for k in units if all(k in errors[j] for j in FRONTIER))
    report["frontier_overlap"] = {
        "wrong_for_one": wrong_for[1],
        "wrong_for_two": wrong_for[2],
        "wrong_for_three": wrong_for[3],
        "three_right_sentences": sum(units[k]["right"] for k in shared),
        "three_wrong_sentences": sum(units[k]["wrong"] for k in shared),
        "pro_and_flash_not_opus": len(
            (errors["gemini-pro-low"] & errors["gemini"]) - errors["opus55"]
        ),
    }
    # Wrong sentences every frontier judge passes or that Opus 5.5 and Pro both pass, beside the
    # whole-sheet graders of stop 47: a grade to check when those also say yes.
    both = (errors["opus55"] & errors["gemini-pro-low"]) | set(shared)
    sheets = {name: fp.sheet_grades(path) for name, path in fp.SHEETS.items()}
    report["grades_to_check"] = {
        k: {"you": "no", **{name: g.get(k) for name, g in sheets.items()}}
        for k in sorted(both)
        if units[k]["wrong"] and any(g.get(k) != "no" for g in sheets.values())
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "errors.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
