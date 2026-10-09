"""Stop 44 readings (docs/GRID.md § Stop 44): batching, teachers, consensus, untrained baselines.

uv run python scripts/teachers.py check      # → results/distill/check44.json
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import auditor_judge as aj  # type: ignore[import-not-found]  # noqa: E402
import teachers  # type: ignore[import-not-found]  # noqa: E402

OUT = ROOT / "results/distill"
LEVELS = ("A", "B", "S")
BATCH_AGREE = 0.90  # rules fixed in GRID § Stop 44
BATCH_DROP = 1


def arm(
    texts: Sequence[Mapping[str, Any]],
    built: Mapping[str, Any],
    labels: Mapping[str, Mapping[str, Any]],
    v0: Mapping[str, Mapping[str, Any]],
    levels: Sequence[str],
) -> dict[str, Any]:
    """Replace and Replace strict on each level, with the stop 40 bar against V0."""
    out: dict[str, Any] = {}
    for level in levels:
        level_texts = [t for t in texts if t["level"] == level]
        base = aj.counts(aj._units(level_texts, v0, level))
        for name, config in (("replace", aj.DEFAULT), ("strict", aj.STRICT)):
            verdicts = aj.replay(level_texts, built, aj.JudgeScorer(name, labels), config)
            c = aj.counts(aj._units(level_texts, verdicts, level))
            c["passes_bar"] = aj.passes_bar(c, base)
            out[f"{level} {name}"] = c
    return out


def _correct(c: Mapping[str, Any]) -> int:
    """Texts the arm gets right: right texts emitted plus wrong texts caught."""
    return int(c["right"] - c["false_rollbacks"] + c["caught"])


def agreement(a: Mapping[str, Any], b: Mapping[str, Any], keys: Sequence[str]) -> dict[str, Any]:
    both = [k for k in keys if k in a and k in b]
    same = sum(a[k]["label"] == b[k]["label"] for k in both)
    pairs = Counter((a[k]["label"], b[k]["label"]) for k in both if a[k]["label"] != b[k]["label"])
    return {
        "same": same,
        "of": len(both),
        "rate": round(same / max(len(both), 1), 3),
        "differ": {f"{x}/{y}": n for (x, y), n in pairs.items()},
    }


def main() -> None:
    texts, built, recorded = aj.recorded_sets()
    rec = {t["key"]: r for t, r in zip(texts, recorded, strict=True)}
    keys_by_level = {
        lv: list(aj.requests([rec[t["key"]] for t in texts if t["level"] == lv])) for lv in LEVELS
    }
    all_keys = [k for lv in LEVELS for k in keys_by_level[lv]]
    ab_keys = keys_by_level["A"] + keys_by_level["B"]
    v0 = aj.replay(texts, built, aj.TableScorer("v0", aj.read_table("v0")))
    single = aj.read_labels("gemini")
    gem = teachers.read_labels("dev-gemini")
    o46 = teachers.read_labels("dev-opus46")
    o55 = teachers.read_labels("dev-opus55")
    report: dict[str, Any] = {"batched_prompt_sha256": aj.BATCH_SHA}
    report["coverage"] = {
        "gemini batched": f"{sum(k in gem for k in all_keys)}/{len(all_keys)}",
        "opus46": f"{sum(k in o46 for k in all_keys)}/{len(all_keys)}",
        "opus55": f"{sum(k in o55 for k in ab_keys)}/{len(ab_keys)}",
    }
    report["arms"] = {"gemini per clause (stop 42)": arm(texts, built, single, v0, LEVELS)}
    report["arms"]["gemini batched"] = arm(texts, built, gem, v0, LEVELS)
    report["arms"]["opus46 batched"] = arm(texts, built, o46, v0, LEVELS)
    report["arms"]["opus55 batched"] = arm(texts, built, o55, v0, ("A", "B"))

    # Batching rule.
    agree = agreement(gem, single, all_keys)
    drop_texts = {}
    for lv in ("A", "B"):
        b = report["arms"]["gemini batched"][f"{lv} strict"]
        g = report["arms"]["gemini per clause (stop 42)"][f"{lv} strict"]
        drop_texts[lv] = _correct(g) - _correct(b)
    batching_ok = agree["rate"] >= BATCH_AGREE and all(d <= BATCH_DROP for d in drop_texts.values())
    report["batching"] = {"agreement": agree, "drop_in_texts": drop_texts, "used": batching_ok}

    # Consensus (Part A and B): Gemini and Opus 4.6 agree, kept; else Opus 5.5 decides.
    gemini = gem if batching_ok else single
    consensus: dict[str, dict[str, Any]] = {}
    for k in ab_keys:
        if k in gemini and k in o46 and gemini[k]["label"] == o46[k]["label"]:
            consensus[k] = dict(gemini[k])
        elif k in o55:
            consensus[k] = dict(o55[k])
    report["teacher_agreement"] = {
        "gemini/opus46": agreement(gemini, o46, all_keys),
        "gemini/opus55 (A, B)": agreement(gemini, o55, ab_keys),
        "opus46/opus55 (A, B)": agreement(o46, o55, ab_keys),
    }
    report["arms"]["consensus"] = arm(texts, built, consensus, v0, ("A", "B"))
    worse = [
        report["arms"]["consensus"][f"{lv} strict"]["accuracy"]
        < report["arms"]["gemini batched" if batching_ok else "gemini per clause (stop 42)"][
            f"{lv} strict"
        ]["accuracy"]
        for lv in ("A", "B")
    ]
    report["students_train_on"] = "gemini alone" if all(worse) else "consensus"

    # Untrained baselines (Modal), if present.
    for name in ("qwen27-nothink", "k2-low"):
        labels = aj.read_labels(name)
        if labels:
            report["arms"][f"{name} (untrained)"] = arm(texts, built, labels, v0, LEVELS)
            report.setdefault("latency", {})[name] = aj.latency(list(labels.values()))
            seq = aj.read_labels(f"{name}-sequential")
            if seq:
                report["latency"][f"{name} one at a time"] = aj.latency(list(seq.values()))
    import router  # type: ignore[import-not-found]  # noqa: PLC0415

    report["router_ledger"] = router.ledger()
    path = OUT / "check44.json"
    path.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for name, a in report["arms"].items():
        row = "  ".join(
            f"{k}: {v['false_rollbacks']}/{v['caught']} {v['accuracy']}"
            + ("*" if v["passes_bar"] else "")
            for k, v in a.items()
        )
        print(f"{name:28} {row}")
    print(
        json.dumps({k: report[k] for k in ("coverage", "batching", "students_train_on")}, indent=1)
    )
    print(json.dumps(report["teacher_agreement"], indent=1))


if __name__ == "__main__":
    main()
