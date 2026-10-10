"""Stop 51: Opus 5.5 (high) as a per-clause judge on the fresh test, scored as stop 50.

Method in docs/GRID.md § Stop 51. The stop 42 prompt is unchanged. Each label is appended as it
returns; a rerun asks only what is missing, and the model stops cleanly at this stop's ledger stop.

  uv run python scripts/teacher_opus.py smoke     # one call
  uv run python scripts/teacher_opus.py fresh     # 323 fresh clause prompts
  uv run python scripts/teacher_opus.py report    # → results/teacher_opus/report.json
  uv run python scripts/teacher_opus.py posthoc   # readings added after the run → posthoc.json
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
import check44  # type: ignore[import-not-found]  # noqa: E402
import fresh_eval as fe  # type: ignore[import-not-found]  # noqa: E402
import fresh_posthoc as fp  # type: ignore[import-not-found]  # noqa: E402
import fresh_report as fr  # type: ignore[import-not-found]  # noqa: E402
import router  # type: ignore[import-not-found]  # noqa: E402
import teacher_pro as tp  # type: ignore[import-not-found]  # noqa: E402
import teachers  # type: ignore[import-not-found]  # noqa: E402

NAME = "opus55"
PATH = fe.LABELS / f"{NAME}.jsonl"
OUT = ROOT / "results/teacher_opus"
STAGE_STOP = 16.0  # the Opus 5.5 ledger stops here for this stop (GRID § Stop 51)
BEFORE = {"calls": 571, "input_tokens": 1247284.0, "output_tokens": 133798.0, "usd": 7.665096}
OTHERS = (tp.NAME, *fp.JUDGES)
PEERS = (tp.NAME, "gemini", "qwen27-nothink")
TOP = (
    NAME,
    tp.NAME,
    "qwen27-nothink",
)  # the three best strict judges, for the readings after the run


def better(mine: float, theirs: float, p: float) -> bool:
    """The reading fixed before the run: higher strict accuracy and p under 0.05."""
    return bool(mine > theirs and p < tp.ALPHA)


def report() -> None:
    graded = fe.grades()
    us, built, rec = fe.recorded()
    by_key = {u["key"]: u for u in us}
    units = [
        {**by_key[k], "right": g == "yes", "wrong": g == "no"}
        for k, g in graded.items()
        if g != "unsure"
    ]
    keys = list(aj.requests(rec))
    opus, missing = tp.filled(fe.read(NAME), keys)
    labels = {NAME: opus} | {name: fe.read(name) for name in OTHERS}
    v0 = aj.replay(
        us, built, aj.TableScorer("v0", json.loads((fe.OUT / "scores/v0.json").read_text()))
    )
    arms: dict[str, dict[str, dict[str, Any]]] = {"V0": v0}
    for name, table in labels.items():
        for placement, config in (("replace", aj.DEFAULT), ("strict", aj.STRICT)):
            arms[f"{name} ({placement})"] = aj.replay(
                us, built, aj.JudgeScorer(name, table), config
            )
    scores = {arm: fr.score(units, v) for arm, v in arms.items()}
    correct = {
        arm: {u["key"]: fr._rolled(v[u["key"]]) == u["wrong"] for u in units}
        for arm, v in arms.items()
    }
    mine = correct[f"{NAME} (strict)"]
    accuracy = scores[f"{NAME} (strict)"]["total"]["accuracy"]
    paired = {}
    for arm, theirs in correct.items():
        if arm.startswith(NAME) or "(replace)" in arm:
            continue
        only_opus = sum(mine[k] and not theirs[k] for k in mine)
        only_other = sum(theirs[k] and not mine[k] for k in mine)
        p = tp.sign_test(only_opus, only_other)
        paired[arm] = {
            "only_opus_right": only_opus,
            "only_other_right": only_other,
            "p": float(f"{p:.3g}"),
            "opus_better": better(accuracy, scores[arm]["total"]["accuracy"], p),
        }
    entry = router.ledger().get(router.OPUS55, {})
    calls = max(entry.get("calls", 0) - BEFORE["calls"], 1)
    spent = {k: entry.get(k, 0) - v for k, v in BEFORE.items()}
    out = {
        "model": router.OPUS55,
        "prompt_sha256": aj.PROMPT_SHA,
        "units": len(units),
        "prompts": len(keys),
        "no_valid_label": missing,
        "arms": scores,
        "opus_strict_against": paired,
        "labels": {name: tp.spread(table, keys) for name, table in labels.items()},
        "agreement": {
            f"opus55/{name}": check44.agreement(opus, labels[name], keys) for name in PEERS
        },
        "latency": aj.latency(list(fe.read(NAME).values())),
        "spend": {
            "this_stop": {**spent, "usd": round(spent["usd"], 4)},
            "usd_per_call": round(spent["usd"] / calls, 5),
            "input_tokens_per_call": round(spent["input_tokens"] / calls),
            "output_tokens_per_call": round(spent["output_tokens"] / calls),
            "ledger_usd": entry.get("usd"),
            "prices_usd_per_million": router.PRICES[router.OPUS55],
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    for arm, s in scores.items():
        cells = "  ".join(
            f"{g}: {s[g]['false_rollbacks']}/{s[g]['caught']} {s[g]['accuracy']}"
            for g in ("software", "statutes", "source answers", "closed answers", "total")
        )
        print(f"{arm:28} {cells}")
    for key in ("opus_strict_against", "labels", "agreement", "latency", "spend"):
        print(json.dumps({key: out[key]}, indent=1))
    print("no valid label:", missing)


def majority(
    labels: dict[str, dict[str, dict[str, Any]]], keys: list[str]
) -> dict[str, dict[str, Any]]:
    """The label two of the three judges give, with one of their passages; else not stated."""
    out = {}
    for k in keys:
        label, n = Counter(labels[name][k]["label"] for name in TOP).most_common(1)[0]
        if n < 2:  # noqa: PLR2004 - two of three
            out[k] = {"label": "not_stated", "passage": 0}
            continue
        source = next(name for name in TOP if labels[name][k]["label"] == label)
        out[k] = {"label": label, "passage": labels[source][k]["passage"]}
    return out


def posthoc() -> None:
    """Not pre-registered: where the three best strict judges fail together."""
    graded = fe.grades()
    us, built, rec = fe.recorded()
    by_key = {u["key"]: u for u in us}
    units = [
        {**by_key[k], "right": g == "yes", "wrong": g == "no"}
        for k, g in graded.items()
        if g != "unsure"
    ]
    keys = list(aj.requests(rec))
    labels = {name: tp.filled(fe.read(name), keys)[0] for name in TOP}
    verdicts = {
        name: aj.replay(us, built, aj.JudgeScorer(name, labels[name]), aj.STRICT) for name in TOP
    }
    by_claim_check = {r["key"] for r in rec if r["claim_rollback"]}
    out: dict[str, Any] = {"judges": list(TOP), "errors": {}}
    for name in TOP:
        rolled = {u["key"] for u in units if fr._rolled(verdicts[name][u["key"]])}
        false = [u for u in units if u["right"] and u["key"] in rolled]
        out["errors"][name] = {
            "false_rollbacks": len(false),
            "of_which_claim_check": sum(u["key"] in by_claim_check for u in false),
            "missed": sum(u["wrong"] and u["key"] not in rolled for u in units),
        }
    ok = {
        name: {u["key"]: fr._rolled(verdicts[name][u["key"]]) == u["wrong"] for u in units}
        for name in TOP
    }
    shared = [u for u in units if not any(ok[name][u["key"]] for name in TOP)]
    out["wrong_for_all_three"] = {
        "sentences": len(shared),
        "right_sentences": sum(u["right"] for u in shared),
        "wrong_sentences": sum(u["wrong"] for u in shared),
        "by_claim_check": sum(u["key"] in by_claim_check for u in shared),
    }
    any_right = sum(any(ok[name][u["key"]] for name in TOP) for u in units)
    out["at_least_one_right"] = {"sentences": any_right, "rate": round(any_right / len(units), 3)}
    vote = aj.replay(us, built, aj.JudgeScorer("vote", majority(labels, keys)), aj.STRICT)
    out["majority_of_three_strict"] = fr.score(units, vote)["total"]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "posthoc.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["smoke", "fresh", "report", "posthoc"])
    command = parser.parse_args().command
    if command == "report":
        report()
        return
    if command == "posthoc":
        posthoc()
        return
    router.CAPS[router.OPUS55] = min(router.CAPS[router.OPUS55], STAGE_STOP)
    asked = tp.fresh_prompts()
    if command == "smoke":
        first = next(iter(asked))
        asked = {first: asked[first]}
    teachers.label_clauses(NAME, "opus55", asked, PATH)
    if command == "smoke":
        print(json.dumps(fe.read(NAME).get(next(iter(asked))), ensure_ascii=False)[:600])
    print(json.dumps(router.ledger().get(router.OPUS55, {})))


if __name__ == "__main__":
    main()
