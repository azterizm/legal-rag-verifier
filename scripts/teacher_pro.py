"""Stop 50: Gemini 3.1 Pro (low) as a per-clause judge, beside Flash and Opus 5.5.

Method in docs/GRID.md § Stop 50. The stop 42 prompt is unchanged. Each label is appended as it
returns; a rerun asks only what is missing, and the model stops cleanly at its ledger cap.

  uv run python scripts/teacher_pro.py smoke     # one call: the model id routes and reports usage
  uv run python scripts/teacher_pro.py fresh     # 323 fresh clause prompts
  uv run python scripts/teacher_pro.py dev       # 280 stop 42 clause prompts
  uv run python scripts/teacher_pro.py audit     # the 500 clauses Opus 5.5 audited in stop 45
  uv run python scripts/teacher_pro.py report    # → results/teacher_pro/report.json
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from math import comb
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import auditor_judge as aj  # type: ignore[import-not-found]  # noqa: E402
import check44  # type: ignore[import-not-found]  # noqa: E402
import distill_data as dd  # type: ignore[import-not-found]  # noqa: E402
import fresh_eval as fe  # type: ignore[import-not-found]  # noqa: E402
import fresh_posthoc as fp  # type: ignore[import-not-found]  # noqa: E402
import fresh_report as fr  # type: ignore[import-not-found]  # noqa: E402
import router  # type: ignore[import-not-found]  # noqa: E402
import teachers  # type: ignore[import-not-found]  # noqa: E402

NAME = "gemini-pro-low"
OUT = ROOT / "results/teacher_pro"
PATHS = {
    "fresh": fe.LABELS / f"{NAME}.jsonl",
    "dev": aj.OUT / "labels" / f"{NAME}.jsonl",
    "audit": teachers.label_path(f"pool-{NAME}-audit"),
}
ALPHA = 0.05  # reading fixed in GRID § Stop 50


def fresh_prompts() -> dict[str, str]:
    us, _, rec = fe.recorded()
    asked: dict[str, str] = aj.requests(rec)
    fe.assert_blind(us, asked)
    return asked


def dev_prompts() -> dict[str, str]:
    texts, _, recorded = aj.recorded_sets()
    asked: dict[str, str] = aj.requests(recorded)
    aj.assert_prompts_clean(texts, asked)
    return asked


def audit_prompts() -> dict[str, str]:
    """The same 500 training clauses ``distill_data.label_all`` drew for Opus 5.5."""
    asked = aj.requests(dd.units())
    rng = random.Random(dd.SEED)  # noqa: S311 - a sample, not a secret
    sample = rng.sample(sorted(asked), min(dd.AUDIT, len(asked)))
    audited = set(teachers.read_labels("pool-opus55-audit"))
    if not audited <= set(sample):
        raise RuntimeError("the audit sample is not the one Opus 5.5 labelled")
    return {k: asked[k] for k in sample}


PROMPTS = {"fresh": fresh_prompts, "dev": dev_prompts, "audit": audit_prompts}


def sign_test(only_a: int, only_b: int) -> float:
    """Exact two-sided sign test on the items only one of two arms gets right."""
    n, k = only_a + only_b, min(only_a, only_b)
    if n == 0:
        return 1.0
    return float(min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2**n))


def sides(
    pro: Mapping[str, Mapping[str, Any]],
    flash: Mapping[str, Mapping[str, Any]],
    opus: Mapping[str, Mapping[str, Any]],
    keys: Sequence[str],
) -> dict[str, int]:
    """Where Flash and Opus 5.5 differ, which of the two Pro's label equals."""
    out = {"differ": 0, "with opus55": 0, "with flash": 0, "neither": 0}
    for k in keys:
        if k not in pro or k not in flash or k not in opus:
            continue
        f, o, p = flash[k]["label"], opus[k]["label"], pro[k]["label"]
        if f == o:
            continue
        out["differ"] += 1
        out["with opus55" if p == o else "with flash" if p == f else "neither"] += 1
    return out


def filled(
    labels: Mapping[str, Mapping[str, Any]], keys: Sequence[str]
) -> tuple[dict[str, dict[str, Any]], int]:
    """Labels for ``keys``; a clause with no valid label counts as not stated."""
    out = {k: dict(labels[k]) for k in keys if labels.get(k, {}).get("label") in aj.LABELS}
    missing = [k for k in keys if k not in out]
    out |= {k: {"label": "not_stated", "passage": 0} for k in missing}
    return out, len(missing)


def spread(labels: Mapping[str, Mapping[str, Any]], keys: Sequence[str]) -> dict[str, int]:
    return dict(Counter(labels[k]["label"] for k in keys if k in labels))


def fresh_report() -> dict[str, Any]:
    graded = fe.grades()
    us, built, rec = fe.recorded()
    by_key = {u["key"]: u for u in us}
    units = [
        {**by_key[k], "right": g == "yes", "wrong": g == "no"}
        for k, g in graded.items()
        if g != "unsure"
    ]
    keys = list(aj.requests(rec))
    pro, missing = filled(fe.read(NAME), keys)
    labels = {NAME: pro} | {name: fe.read(name) for name in fp.JUDGES}
    v0 = aj.replay(
        us, built, aj.TableScorer("v0", json.loads((fe.OUT / "scores/v0.json").read_text()))
    )
    arms: dict[str, dict[str, dict[str, Any]]] = {"V0": v0}
    for name, table in labels.items():
        for placement, config in (("replace", aj.DEFAULT), ("strict", aj.STRICT)):
            arms[f"{name} ({placement})"] = aj.replay(
                us, built, aj.JudgeScorer(name, table), config
            )
    correct = {
        arm: {u["key"]: fr._rolled(v[u["key"]]) == u["wrong"] for u in units}
        for arm, v in arms.items()
    }
    mine = correct[f"{NAME} (strict)"]
    paired = {}
    for arm, theirs in correct.items():
        if arm.startswith(NAME) or "(replace)" in arm:
            continue
        only_pro = sum(mine[k] and not theirs[k] for k in mine)
        only_other = sum(theirs[k] and not mine[k] for k in mine)
        paired[arm] = {
            "only_pro_right": only_pro,
            "only_other_right": only_other,
            "p": round(sign_test(only_pro, only_other), 4),
        }
    scores = {arm: fr.score(units, v) for arm, v in arms.items()}
    pro_acc = scores[f"{NAME} (strict)"]["total"]["accuracy"]
    flash_acc = scores["gemini (strict)"]["total"]["accuracy"]
    return {
        "units": len(units),
        "prompts": len(keys),
        "no_valid_label": missing,
        "arms": scores,
        "pro_strict_against": paired,
        "better_than_flash": bool(pro_acc > flash_acc and paired["gemini (strict)"]["p"] < ALPHA),
        "labels": {name: spread(table, keys) for name, table in labels.items()},
        "agreement": {"pro/flash": check44.agreement(pro, labels["gemini"], keys)},
        "latency": aj.latency(list(fe.read(NAME).values())),
    }


def dev_report() -> dict[str, Any]:
    texts, built, recorded = aj.recorded_sets()
    rec = {t["key"]: r for t, r in zip(texts, recorded, strict=True)}
    check44._REC.update(rec)
    by_level = {
        lv: list(aj.requests([rec[t["key"]] for t in texts if t["level"] == lv]))
        for lv in check44.LEVELS
    }
    keys = [k for lv in check44.LEVELS for k in by_level[lv]]
    ab = by_level["A"] + by_level["B"]
    pro, missing = filled(aj.read_labels(NAME), keys)
    v0 = aj.replay(texts, built, aj.TableScorer("v0", aj.read_table("v0")))
    flash = aj.read_labels("gemini")
    return {
        "prompts": len(keys),
        "no_valid_label": missing,
        "arm": check44.arm(texts, built, pro, v0, check44.LEVELS),
        "labels": {NAME: spread(pro, keys), "gemini": spread(flash, keys)},
        "agreement": {
            "pro/flash": check44.agreement(pro, flash, keys),
            "pro/opus55 batched (A, B)": check44.agreement(
                pro, teachers.read_labels("dev-opus55"), ab
            ),
            "pro/opus46 batched": check44.agreement(pro, teachers.read_labels("dev-opus46"), keys),
        },
        "latency": aj.latency(list(aj.read_labels(NAME).values())),
    }


def audit_report() -> dict[str, Any]:
    opus = teachers.read_labels("pool-opus55-audit")
    keys = sorted(opus)
    flash = teachers.read_labels("pool-gemini")
    raw = teachers.read_labels(NAME, PATHS["audit"])
    pro = {k: v for k, v in raw.items() if v["label"] in aj.LABELS}
    return {
        "clauses": len(keys),
        "no_valid_label": sum(k not in pro for k in keys),
        "labels": {
            NAME: spread(pro, keys),
            "gemini": spread(flash, keys),
            "opus55": spread(opus, keys),
        },
        "agreement": {
            "pro/opus55": check44.agreement(pro, opus, keys),
            "pro/flash": check44.agreement(pro, flash, keys),
            "flash/opus55": check44.agreement(flash, opus, keys),
        },
        "where_flash_and_opus55_differ": sides(pro, flash, opus, keys),
        "latency": aj.latency(list(raw.values())),
    }


def report() -> None:
    out: dict[str, Any] = {"model": router.PRO, "prompt_sha256": aj.PROMPT_SHA}
    out["fresh"] = fresh_report()
    out["dev"] = dev_report()
    out["audit"] = audit_report()
    entry = router.ledger().get(router.PRO, {})
    calls = max(entry.get("calls", 0), 1)
    out["spend"] = {
        **entry,
        "usd_per_call": round(entry.get("usd", 0.0) / calls, 5),
        "input_tokens_per_call": round(entry.get("input_tokens", 0) / calls),
        "output_tokens_per_call": round(entry.get("output_tokens", 0) / calls),
        "prices_usd_per_million": router.PRICES[router.PRO],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    for arm, s in out["fresh"]["arms"].items():
        cells = "  ".join(
            f"{g}: {s[g]['false_rollbacks']}/{s[g]['caught']} {s[g]['accuracy']}"
            for g in ("software", "statutes", "source answers", "closed answers", "total")
        )
        print(f"{arm:28} {cells}")
    print(json.dumps(out["fresh"]["pro_strict_against"], indent=1))
    print("better than flash:", out["fresh"]["better_than_flash"])
    print(json.dumps({k: v for k, v in out["dev"].items() if k != "arm"}, indent=1))
    for k, v in out["dev"]["arm"].items():
        row = f"{v['false_rollbacks']}/{v['caught']} {v['accuracy']}" if isinstance(v, dict) else v
        print(f"dev {k}: {row}")
    print(json.dumps(out["audit"], indent=1))
    print(json.dumps(out["spend"], indent=1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["smoke", *PROMPTS, "report"])
    command = parser.parse_args().command
    if command == "report":
        report()
        return
    if command == "smoke":
        asked = fresh_prompts()
        first = next(iter(asked))
        teachers.label_clauses(NAME, "pro", {first: asked[first]}, PATHS["fresh"])
        print(json.dumps(fe.read(NAME).get(first), ensure_ascii=False)[:600])
    else:
        teachers.label_clauses(NAME, "pro", PROMPTS[command](), PATHS[command])
    print(json.dumps(router.ledger().get(router.PRO, {})))


if __name__ == "__main__":
    main()
