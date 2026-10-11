"""Stop 57: Qwen 27B as generator and judge, beside the 7B generator (docs/GRID.md § Stop 57).

Reads the tables of the two sets (``fresh_arms.py table`` under each FRESH_SET). A sentence's grade
is the two graders' where they settle it, and yours for the rest.

  FRESH_SET=fresh2     uv run python scripts/fresh_arms.py table
  FRESH_SET=fresh2-q27 uv run python scripts/fresh_arms.py table
  uv run python scripts/self_judge.py      # → results/fresh2-q27_arms/selfjudge.json
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from teacher_pro import sign_test  # type: ignore[import-not-found]  # noqa: E402

SETS = {"Qwen 2.5 7B": "fresh2", "Qwen 27B 4-bit": "fresh2-q27"}
QWEN, PRO = "qwen27-ar4", "gemini-pro-low"
MODES = {"source": "with source", "closed": "closed-book"}
ALPHA = 0.05
MIN_OWN = 5  # R3: Qwen 27B must pass at least this many of its own errors that Pro catches


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [0.0, 1.0]
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / (1 + z * z / n)
    return [round(centre - half, 3), round(centre + half, 3)]


def rows(name: str, *, by: str = "graders") -> list[dict[str, Any]]:
    """The graded sentences of a set. ``by="graders"``: the two graders' grade, yours where they
    leave it open. ``by="you"``: the grades file as it stands."""
    table = json.loads((ROOT / f"results/{name}_arms/table.json").read_text(encoding="utf-8"))
    out = []
    for key, r in table["rows"].items():
        grade = (r["graders"] or r["grade"]) if by == "graders" else r["grade"]
        if grade in {"yes", "no"}:
            out.append({**r, "key": key, "right": grade == "yes", "wrong": grade == "no"})
    return out


def score(units: list[dict[str, Any]], rolled: Mapping[str, bool]) -> dict[str, Any]:
    right, wrong = sum(u["right"] for u in units), sum(u["wrong"] for u in units)
    false = sum(u["right"] and rolled[u["key"]] for u in units)
    caught = sum(u["wrong"] and rolled[u["key"]] for u in units)
    n = max(right + wrong, 1)
    return {
        "sentences": right + wrong,
        "right": right,
        "wrong": wrong,
        "false_rollbacks": false,
        "caught": caught,
        "accuracy": round((right - false + caught) / n, 3),
        "interval_95": wilson(right - false + caught, right + wrong),
    }


def by_group(units: list[dict[str, Any]], rolled: Mapping[str, bool]) -> dict[str, Any]:
    out = {"total": score(units, rolled)}
    for mode, title in MODES.items():
        out[title] = score([u for u in units if u["mode"] == mode], rolled)
    return out


def flags(units: list[dict[str, Any]], column: str) -> dict[str, bool]:
    return {u["key"]: bool(u[column]) for u in units}


def _ok(rolled: Mapping[str, bool], unit: Mapping[str, Any]) -> bool:
    return bool(rolled[unit["key"]] == unit["wrong"])


def paired(
    units: list[dict[str, Any]], a: Mapping[str, bool], b: Mapping[str, bool]
) -> dict[str, Any]:
    """Sentences only the first, only the second gets right, and the sign test."""
    only_a = sum(_ok(a, u) and not _ok(b, u) for u in units)
    only_b = sum(_ok(b, u) and not _ok(a, u) for u in units)
    p = float(f"{sign_test(only_a, only_b):.3g}")
    return {"only_first": only_a, "only_second": only_b, "p": p}


def main() -> None:
    out: dict[str, Any] = {"grades": "Opus 5.5 and Gemini 3.1 Pro, open sentences by you"}
    out |= {"R1_generator": {}, "R2_own_text": {}, "R3_self_judging": {}, "R4_pair": {}}
    for title, name in SETS.items():
        units = rows(name)
        nobody = {u["key"]: False for u in units}
        # R1: how often each generator is wrong.
        r1 = {}
        for mode, label in (*MODES.items(), (None, "total")):
            group = [u for u in units if mode is None or u["mode"] == mode]
            wrong = sum(u["wrong"] for u in group)
            r1[label] = {
                "sentences": len(group),
                "wrong": wrong,
                "share_wrong": round(wrong / max(len(group), 1), 3),
                "interval_95": wilson(wrong, len(group)),
            }
        out["R1_generator"][title] = r1
        # R2: the Qwen 27B judge on this generator's text (stop 42 prompt).
        out["R2_own_text"][title] = {
            "no auditor": by_group(units, nobody),
            "figures to the judge": by_group(units, flags(units, f"{QWEN}|p42|figures")),
            "claim check rolling back": by_group(units, flags(units, f"{QWEN}|p42|claim")),
        }
        # R3: the wrong sentences each judge passes (both with notes2, figures to the judge).
        q, p = flags(units, f"{QWEN}|notes2|figures"), flags(units, f"{PRO}|notes2|figures")
        wrong = [u for u in units if u["wrong"]]
        only_pro = sum(p[u["key"]] and not q[u["key"]] for u in wrong)  # Qwen passes, Pro catches
        only_qwen = sum(q[u["key"]] and not p[u["key"]] for u in wrong)
        test = sign_test(only_pro, only_qwen)
        out["R3_self_judging"][title] = {
            "wrong_sentences": len(wrong),
            "passed_by_qwen27": sum(not q[u["key"]] for u in wrong),
            "passed_by_pro": sum(not p[u["key"]] for u in wrong),
            "qwen27_passes_pro_catches": only_pro,
            "pro_passes_qwen27_catches": only_qwen,
            "p": float(f"{test:.3g}"),
            "self_judging_limit": bool(only_pro >= MIN_OWN and test < ALPHA),
        }
        # R4: rolled back only if both roll back, against Qwen 27B alone.
        both = {k: q[k] and p[k] for k in q}
        test4 = paired(units, both, q)
        pair, alone = by_group(units, both), by_group(units, q)
        gain = pair["total"]["accuracy"] > alone["total"]["accuracy"] and test4["p"] < ALPHA
        out["R4_pair"][title] = {
            "qwen27 alone (notes2)": alone,
            "pro alone (notes2)": by_group(units, p),
            "both must roll back": pair,
            "pair_against_qwen27": {**test4, "gain": bool(gain)},
        }
    # Added after the scoring (not a fixed reading): refusals and requests for context.
    out["after_refusals"] = {}
    for title, name in SETS.items():
        units = rows(name)
        rolled = flags(units, f"{QWEN}|p42|figures")
        refusals = [u for u in units if u["refusal"]]
        rest = [u for u in units if not u["refusal"]]
        out["after_refusals"][title] = {
            "refusal_sentences": len(refusals),
            "graded_right": sum(u["right"] for u in refusals),
            "graded_wrong": sum(u["wrong"] for u in refusals),
            "rolled_back": sum(rolled[u["key"]] for u in refusals),
            "false_rollbacks_that_are_refusals": sum(
                u["right"] and rolled[u["key"]] for u in refusals
            ),
            "without_refusal_sentences": score(rest, rolled),
        }
    out["R1_generator"]["Qwen 2.5 7B, by your grades"] = {
        label: sum(
            u["wrong"] for u in rows("fresh2", by="you") if mode is None or u["mode"] == mode
        )
        for mode, label in (*MODES.items(), (None, "total"))
    }
    target = ROOT / "results/fresh2-q27_arms"
    target.mkdir(parents=True, exist_ok=True)
    (target / "selfjudge.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
