"""Stop 58: a refusal rule on the judge's side (docs/GRID.md § Stop 58).

Reads the tables of the two sets (``fresh_arms.py table`` under each FRESH_SET), after the labels
of stop 58 are in. Qwen 27B's own answers are graded as in stop 57; the 7B's by your grades.

  FRESH_SET=fresh2     uv run python scripts/fresh_arms.py table
  FRESH_SET=fresh2-q27 uv run python scripts/fresh_arms.py table
  uv run python scripts/refusal_rule.py      # → results/fresh2-q27_arms/refusal.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import self_judge as sj  # type: ignore[import-not-found]  # noqa: E402

JUDGE = "qwen27-ar4"
BASE = "p42"
ALPHA = 0.05
MARGIN = 0.015  # S3: no harm if at most this much lower and not told apart


def column(kind: str) -> str:
    return f"{JUDGE}|{kind}|figures"


def against(units: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    new, old = sj.flags(units, column(kind)), sj.flags(units, column(BASE))
    test = sj.paired(units, new, old)
    a, b = sj.score(units, new), sj.score(units, old)
    return {
        "stop 42 prompt": b,
        kind: a,
        "against_stop_42_prompt": test,
        "change_in_points": round(100 * (a["accuracy"] - b["accuracy"]), 1),
        "gain": bool(a["accuracy"] > b["accuracy"] and test["p"] < ALPHA),
        "no_harm": bool(b["accuracy"] - a["accuracy"] <= MARGIN and test["p"] >= ALPHA),
    }


def main() -> None:
    own = sj.rows("fresh2-q27")
    other = sj.rows("fresh2", by="you")
    out: dict[str, Any] = {"judge": JUDGE, "S1_refusal_sentences": {}, "S2_own_answers": {}}
    refusals = [u for u in own if u["refusal"]]
    for kind in (BASE, "rule", "refusal"):
        rolled = sj.flags(own, column(kind))
        out["S1_refusal_sentences"][kind] = {
            "right": sum(u["right"] for u in refusals),
            "wrong": sum(u["wrong"] for u in refusals),
            "right_passed": sum(u["right"] and not rolled[u["key"]] for u in refusals),
            "wrong_caught": sum(u["wrong"] and rolled[u["key"]] for u in refusals),
        }
    for kind in ("rule", "refusal"):
        result = against(own, kind)
        rest = [u for u in own if not u["refusal"]]
        result["without_refusal_sentences"] = {
            k: sj.score(rest, sj.flags(rest, column(k))) for k in (BASE, kind)
        }
        for mode, title in sj.MODES.items():
            group = [u for u in own if u["mode"] == mode]
            result[title] = {k: sj.score(group, sj.flags(group, column(k))) for k in (BASE, kind)}
        out["S2_own_answers"][kind] = result
    out["S3_the_7b_answers"] = against(other, "refusal")
    target = ROOT / "results/fresh2-q27_arms"
    (target / "refusal.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
