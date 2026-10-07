"""Stop 27, the injection A/B: what happens at each rollback point, per in-flight cell.

A rollback point is a sentence position where the verifier rejected at least one draft. Points are
grouped by what rejected the first draft: the claim check (figures, citations, instruments,
qualifiers, deontics, versions) or the NLI head alone. Per group: how often the first retry passed,
how many points recovered (a later draft was emitted) and how many ended in the refusal sentence.

Stop 29 adds, for 4B against 4B-inject on test, the states both arms reached at their first
rollback (``replay_states.py``): first-retry pass from the same state, paired, and how many first
drafts passed in the sentences after that point.

  uv run python scripts/grid_inject.py > results/grid/inject_ab.json   # test: 4B vs 4B-inject
  uv run python scripts/grid_inject.py --split dev --cells 4B-inject-note 4B-inject-turn
"""

from __future__ import annotations

import argparse
import collections
import json
import statistics
from pathlib import Path
from typing import Any

from replay_states import downstream, load, paired, shared_states  # type: ignore[import-not-found]

ROOT = Path(__file__).resolve().parent.parent
GRID = ROOT / "results/grid"
NLI = {"NLI_CONTRADICTION", "NLI_NOT_ENTAILED", "NEUTRAL_STRICT"}


def group(point: dict[str, Any]) -> str:
    reasons = set(point["attempts"][0]["verdict"]["reasons"])
    return "nli" if reasons <= NLI else "claim_check"


def _rate(hit: int, total: int) -> str:
    return f"{hit}/{total} ({hit / total:.0%})" if total else "0/0"


def points_summary(points: list[dict[str, Any]]) -> dict[str, Any]:
    retried = [p for p in points if len(p["attempts"]) > 1]
    first_ok = sum(p["attempts"][1]["verdict"]["verdict"] == "EMIT" for p in retried)
    return {
        "points": len(points),
        "first_retry_passed": _rate(first_ok, len(retried)),
        "recovered": sum(p["outcome"] == "emitted" for p in points),
        "refused": sum(p["outcome"] == "refused" for p in points),
        "recovered_by": dict(
            collections.Counter(p["recovered_by"] for p in points if p["outcome"] == "emitted")
        ),
    }


def summary(path: Path, ids: set[str] | None = None) -> dict[str, Any]:
    records = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    records = [r for r in records if ids is None or r["id"] in ids]
    points = [s for r in records for s in r["trace"]["sentences"] if s["rollbacks"]]
    injected = [
        a for p in points for a in p["attempts"] if a.get("injected")
    ]  # absent in traces written before stop 27
    by_group = {g: [p for p in points if group(p) == g] for g in ("claim_check", "nli")}
    return {
        "answers": len(records),
        "answers_with_a_refusal": sum(r["refusals"] > 0 for r in records),
        "all": points_summary(points),
        **{g: points_summary(ps) for g, ps in by_group.items()},
        "injections": len(injected),
        "tokens_injected_median": statistics.median(a["injected"]["tokens"] for a in injected)
        if injected
        else None,
        "injected_retries_with_prefix_cache_hit": _rate(
            sum(a["prefix_cache_hit_tokens"] > 0 for a in injected), len(injected)
        ),
        "time_to_first_output_s_median": round(
            statistics.median(
                r["time_to_first_output_ns"] / 1e9 for r in records if r["time_to_first_output_ns"]
            ),
            2,
        ),
        "wall_s_median": round(statistics.median(r["wall_ns"] / 1e9 for r in records), 2),
        "tokens_discarded_mean": round(statistics.mean(r["tokens_discarded"] for r in records), 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", default="test")
    parser.add_argument("--cells", nargs="+", default=["4B", "4B-inject"])
    args = parser.parse_args()
    root = GRID if args.split == "test" else GRID / args.split
    paths = {c: root / f"{c}.jsonl" for c in args.cells if (root / f"{c}.jsonl").exists()}
    shared = set.intersection(
        *({json.loads(x)["id"] for x in p.read_text().splitlines()} for p in paths.values())
    )
    out: dict[str, Any] = {
        "split": args.split,
        "prompts": len(shared),
        "cells": {cell: summary(path, shared) for cell, path in paths.items()},
    }
    if args.split == "test" and set(paths) == {"4B", "4B-inject"}:
        a, b = load(paths["4B"]), load(paths["4B-inject"])
        states, _ = shared_states(a, b)
        ids = [s.id for s in states]
        out["shared_first_rollback_states"] = paired(states)
        out["after_first_rollback"] = {"4B": downstream(a, ids), "4B-inject": downstream(b, ids)}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
