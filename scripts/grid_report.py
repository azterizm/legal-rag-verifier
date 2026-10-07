"""Grid results with the independent judge (docs/GRID.md): per-cell correctness, judge validity
against the blind labels, and the detector's misses on released sentences (refinement hypotheses,
to be tested on the dev split only).

  uv run python scripts/grid_report.py   # → results/grid/report.json
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "batteries/verifier"))

from grid_judge import OUT as JUDGE  # type: ignore[import-not-found]  # noqa: E402
from grid_judge import agreement  # noqa: E402
from grid_prompts import rows  # type: ignore[import-not-found]  # noqa: E402
from grid_score import CELLS, GRID, load  # type: ignore[import-not-found]  # noqa: E402

from legal_rag_verifier.engine import DEFAULT_REFUSAL  # noqa: E402

BAD = {"unsupported", "contradicted"}


def main() -> None:
    by_id = {r["id"]: r for r in rows()}
    judged = {
        (j["cell"], j["id"]): j
        for j in (json.loads(x) for x in JUDGE.read_text(encoding="utf-8").splitlines())
    }
    cells: dict[str, Any] = {}
    misses: list[dict[str, Any]] = []
    for cell in CELLS:
        records = load(cell)
        verdicts = [judged.get((cell, i)) for i in records]
        ok = [v for v in verdicts if v and v.get("verdict") in {"correct", "incorrect"}]
        split: dict[str, list[bool]] = {"answerable": [], "abstention": []}
        for i in records:
            v = judged.get((cell, i))
            if v and v.get("verdict") in {"correct", "incorrect"}:
                kind = "abstention" if by_id[i]["expects_abstention"] else "answerable"
                split[kind].append(v["verdict"] == "correct")
        errors: collections.Counter[str] = collections.Counter()
        for i, r in records.items():
            v = judged.get((cell, i))
            if not v or not r["resolved"]:
                continue  # an unresolved 4A/4D answer was released with the detector's flags on it
            for s in v.get("sentences") or []:
                text = str(s.get("sentence", ""))
                if s.get("label") in BAD and DEFAULT_REFUSAL not in text:
                    errors[s.get("error") or "other"] += 1
                    misses.append({"cell": cell, "id": i, **s})
        cells[cell] = {
            "judged": len(ok),
            "judge_correct": sum(v["verdict"] == "correct" for v in ok),
            "judge_correct_rate": round(sum(v["verdict"] == "correct" for v in ok) / len(ok), 4)
            if ok
            else None,
            "answerable_correct": f"{sum(split['answerable'])}/{len(split['answerable'])}",
            "abstention_correct": f"{sum(split['abstention'])}/{len(split['abstention'])}",
            "judge_failures": len(verdicts) - len(ok),
            "detector_passed_but_judge_flagged_sentences": dict(errors),
        }
    report = {
        "judge": next(iter(judged.values()))["judge"] if judged else None,
        "cells": cells,
        "judge_vs_labels": agreement(GRID / "review_labels.csv"),
        "detector_misses": misses,
    }
    (GRID / "report.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in report.items() if k != "detector_misses"}, indent=1))
    print(f"detector misses on released sentences: {len(misses)}")


if __name__ == "__main__":
    main()
