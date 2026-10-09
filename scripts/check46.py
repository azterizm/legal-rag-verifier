"""Stop 46 readings (docs/GRID.md § Stop 46): the student against its teacher, and the gate.

uv run python scripts/check46.py [k2]     # → results/distill/check46-<student>.json
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
import check44  # type: ignore[import-not-found]  # noqa: E402

OUT = ROOT / "results/distill"
GATE_POINTS = 3.0  # GRID § Stop 46
LATENCY_P95_MS = 2000


def main() -> None:
    student = sys.argv[1] if len(sys.argv) > 1 else "k2"
    name = f"{student}-student"
    texts, built, recorded = aj.recorded_sets()
    check44._REC.update({t["key"]: r for t, r in zip(texts, recorded, strict=True)})
    v0 = aj.replay(texts, built, aj.TableScorer("v0", aj.read_table("v0")))
    report: dict[str, Any] = {}

    rows = (OUT / "validation.jsonl").read_text(encoding="utf-8").splitlines()
    teacher = {r["sha"]: json.loads(r["messages"][2]["content"]) for r in map(json.loads, rows)}
    got = aj.read_labels(f"{name}-validation")
    both = [k for k in teacher if k in got]
    same = sum(teacher[k]["label"] == got[k]["label"] for k in both)
    report["validation_agreement"] = {
        "same": same,
        "of": len(both),
        "rate": round(same / max(len(both), 1), 3),
        "errors": sum(got[k]["label"] == "error" for k in both),
        "differ": {
            f"teacher {a} / student {b}": n
            for (a, b), n in Counter(
                (teacher[k]["label"], got[k]["label"])
                for k in both
                if teacher[k]["label"] != got[k]["label"]
            ).items()
        },
    }
    levels = ("A", "B", "S")
    report["student"] = check44.arm(texts, built, aj.read_labels(name), v0, levels)
    report["teacher (gemini per clause)"] = check44.arm(
        texts, built, aj.read_labels("gemini"), v0, levels
    )
    report["latency"] = {
        "bulk": aj.latency(list(aj.read_labels(name).values())),
        "one at a time": aj.latency(list(aj.read_labels(f"{name}-sequential").values())),
    }
    gaps = {
        lv: round(
            100
            * (
                report["teacher (gemini per clause)"][f"{lv} strict"]["accuracy"]
                - report["student"][f"{lv} strict"]["accuracy"]
            ),
            1,
        )
        for lv in ("A", "B")
    }
    report["gate"] = {
        "points_below_teacher": gaps,
        "halt_for_review": any(g > GATE_POINTS for g in gaps.values()),
        "p95_ms": report["latency"]["one at a time"].get("p95_ms"),
        "meets_latency": (report["latency"]["one at a time"].get("p95_ms") or 1e9)
        <= LATENCY_P95_MS,
    }
    import modal_ledger  # type: ignore[import-not-found]  # noqa: PLC0415
    import router  # type: ignore[import-not-found]  # noqa: PLC0415

    report["spend"] = {"modal": modal_ledger.spent(), "router": router.ledger()}
    path = OUT / f"check46-{student}.json"
    path.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for arm_name in ("student", "teacher (gemini per clause)"):
        for k, v in report[arm_name].items():
            if isinstance(v, dict):
                print(
                    f"{arm_name:28} {k:10} FR {v['false_rollbacks']:3} caught {v['caught']:3}"
                    f" acc {v['accuracy']} bar {v['passes_bar']}"
                )
    print(json.dumps({k: report[k] for k in ("validation_agreement", "latency", "gate")}, indent=1))


if __name__ == "__main__":
    main()
