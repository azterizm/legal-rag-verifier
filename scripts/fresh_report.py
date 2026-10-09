"""Stop 47 scoring (docs/GRID.md § Stop 47), run once after your grades are committed.

uv run python scripts/fresh_eval.py report      # → results/fresh/report.json, errors.jsonl
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import auditor_judge as aj  # type: ignore[import-not-found]  # noqa: E402
import fresh_eval as fe  # type: ignore[import-not-found]  # noqa: E402

GATE_POINTS = 3.0
LATENCY_P95_MS = 2000
# Placements fixed in GRID § Stop 47 (the student's is read from its stop 46 dev numbers).
PLACEMENTS = {
    "gemini": "replace",
    "qwen27-low": "strict",
    "qwen27-nothink": "replace",
    "k2-low": "replace",
}
DOMAINS = {"software": "software", "legal": "statutes"}


def student_placement(student: str) -> str:
    dev = json.loads((ROOT / f"results/distill/check46-{student}.json").read_text("utf-8"))
    arms = dev["student"]
    mean = {
        p: statistics.mean(arms[f"{lv} {p}"]["accuracy"] for lv in ("A", "B"))
        for p in ("replace", "strict")
    }
    return "strict" if mean["strict"] > mean["replace"] else "replace"


def _rolled(v: Mapping[str, Any]) -> bool:
    return bool(v["verdict"] != "EMIT")


def score(
    units: Sequence[Mapping[str, Any]], verdicts: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    groups = {"total": list(units)}
    groups |= {name: [u for u in units if u["domain"] == d] for d, name in DOMAINS.items()}
    groups |= {f"{m} answers": [u for u in units if u["mode"] == m] for m in ("source", "closed")}
    for name, us in groups.items():
        rows = [{**u, "rolled": _rolled(verdicts[u["key"]]), "by_nli": False} for u in us]
        out[name] = aj.counts(rows)
    return out


def main() -> None:  # noqa: PLR0912, PLR0915 - one pass over the pre-registered readings
    graded = fe.grades()
    if not graded or any(g not in {"yes", "no", "unsure"} for g in graded.values()):
        bad = Counter(g for g in graded.values() if g not in {"yes", "no", "unsure"})
        raise RuntimeError(f"grades incomplete or not yes / no / unsure: {dict(bad)}")
    us, built, rec = fe.recorded()
    by_key = {u["key"]: u for u in us}
    units = [
        {**by_key[k], "right": g == "yes", "wrong": g == "no"}
        for k, g in graded.items()
        if g != "unsure"
    ]
    rec_by_key = {u["key"]: r for u, r in zip(us, rec, strict=True)}
    report: dict[str, Any] = {
        "graded": dict(Counter(graded.values())),
        "units": len(units),
    }
    v0 = aj.replay(
        us, built, aj.TableScorer("v0", json.loads((fe.OUT / "scores/v0.json").read_text()))
    )
    arms: dict[str, dict[str, dict[str, Any]]] = {"V0": v0}
    arms["claim check only"] = {
        k: {"verdict": "EMIT", "reasons": []} if set(v["reasons"]) <= aj.NLI_REASONS else v
        for k, v in v0.items()
    }
    arms["no auditor"] = {k: {"verdict": "EMIT", "reasons": []} for k in v0}
    placements = dict(PLACEMENTS)
    student = "k2-student"
    if fe.read(student):
        placements[student] = student_placement("k2")
    asked = aj.requests(rec)
    report["missing_labels"] = {}
    for name, placement in placements.items():
        labels = fe.read(name)
        missing = [k for k in asked if k not in labels]
        if missing:
            report["missing_labels"][name] = len(missing)
            continue
        config = aj.STRICT if placement == "strict" else aj.DEFAULT
        arms[f"{name} ({placement})"] = aj.replay(us, built, aj.JudgeScorer(name, labels), config)
    report["arms"] = {name: score(units, v) for name, v in arms.items()}
    base = report["arms"]["V0"]
    for name, s in report["arms"].items():
        if name in ("V0", "claim check only", "no auditor"):
            continue
        for group in ("software", "statutes", "total"):
            s[group]["passes_bar"] = aj.passes_bar(s[group], base[group])

    # F2 and F3: the student against its teacher and against Qwen 27B low.
    names = {n.split(" (")[0]: n for n in report["arms"]}
    if student in names and "gemini" in names:
        s, t = report["arms"][names[student]], report["arms"][names["gemini"]]
        gaps = {
            d: round(100 * (t[d]["accuracy"] - s[d]["accuracy"]), 1)
            for d in ("software", "statutes")
        }
        dev = json.loads((ROOT / "results/distill/check46-k2.json").read_text("utf-8"))
        p95 = dev["latency"]["one at a time"].get("p95_ms")
        report["F2"] = {
            "points_below_teacher": gaps,
            "p95_ms_one_at_a_time": p95,
            "success": all(g <= GATE_POINTS for g in gaps.values())
            and (p95 or 1e9) <= LATENCY_P95_MS,
        }
        if "qwen27-low" in names:
            q = report["arms"][names["qwen27-low"]]
            report["F3"] = {
                d: {"student": s[d]["accuracy"], "qwen27-low": q[d]["accuracy"]}
                for d in ("software", "statutes", "total")
            }

    # F4: latency per clause in the bulk fresh runs.
    report["F4"] = {name: aj.latency(list(fe.read(name).values())) for name in placements}

    # Wrong sentences: how often each judge says contradicted or not stated.
    wrong = [u for u in units if u["wrong"]]
    report["wrong_sentences_labels"] = {}
    for name in placements:
        labels = fe.read(name)
        seen: Counter[str] = Counter()
        for u in wrong:
            for clause, cands in rec_by_key[u["key"]]["calls"]:
                sha = aj.prompt_key(aj.user_prompt(clause, cands, rec_by_key[u["key"]]["prefix"]))
                if sha in labels:
                    seen[labels[sha]["label"]] += 1
        report["wrong_sentences_labels"][name] = dict(seen)

    # F5: every error of the teacher and the student, with the judge's reasons.
    errors = []
    for name in ("gemini", student):
        if name not in names:
            continue
        verdicts, labels = arms[names[name]], fe.read(name)
        for u in units:
            rolled = _rolled(verdicts[u["key"]])
            if (u["wrong"] and not rolled) or (u["right"] and rolled):
                r = rec_by_key[u["key"]]
                errors.append(
                    {
                        "judge": name,
                        "key": u["key"],
                        "error": "wrong passed" if u["wrong"] else "right rolled back",
                        "sentence": u["sentence"],
                        "reasons": verdicts[u["key"]]["reasons"],
                        "labels": [
                            labels[aj.prompt_key(aj.user_prompt(c, cs, r["prefix"]))]
                            for c, cs in r["calls"]
                        ],
                    }
                )
    aj.write_jsonl(fe.OUT / "errors.jsonl", errors)
    report["F5_errors"] = dict(Counter(e["judge"] for e in errors))
    (fe.OUT / "report.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    for name, s in report["arms"].items():
        cells = "  ".join(
            f"{g}: {s[g]['false_rollbacks']}/{s[g]['caught']} {s[g]['accuracy']}"
            + ("*" if s[g].get("passes_bar") else "")
            for g in ("software", "statutes", "total")
        )
        print(f"{name:28} {cells}")
    print(
        json.dumps({k: report.get(k) for k in ("graded", "F2", "F3", "missing_labels")}, indent=1)
    )


if __name__ == "__main__":
    main()
