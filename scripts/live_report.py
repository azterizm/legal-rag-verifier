"""Stop 59 readings from the traces of the live loop (docs/GRID.md § Stop 59).

T1 to T3 need only the traces. T4 needs the grades of the final answers
(``fresh_grader.py fill`` for the live set).

  FRESH_SET=fresh2-live uv run python scripts/live_report.py
  # → results/fresh2-live_arms/live.json
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "batteries/verifier"))

import fresh_battery as fb  # type: ignore[import-not-found]  # noqa: E402
import fresh_eval as fe  # type: ignore[import-not-found]  # noqa: E402
import self_judge as sj  # type: ignore[import-not-found]  # noqa: E402

ARMS = {"source": "source in the prompt", "closed": "from memory, source on rollback"}
REPAIR = 0.5  # T4: the closed arm repairs if its wrong share is at most this times the baseline's
REFUSED = 0.05  # T4: the source arm costs little if at most this share is replaced by the refusal
# The same model's answers without a loop, graded in stop 57 (wrong sentences, all sentences).
BASELINE = {"source": (0, 49), "closed": (36, 65)}


def traces() -> dict[str, dict[str, Any]]:
    """Key → the last record kept for it."""
    path = Path(fb.OUT) / "traces.jsonl"
    return {r["key"]: r for r in map(json.loads, path.read_text(encoding="utf-8").splitlines())}


def pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(q * len(ordered)))], 2) if ordered else 0.0


def mechanics(records: list[dict[str, Any]]) -> dict[str, Any]:
    points = [p for r in records for p in r["trace"]["sentences"]]
    rollbacks = [r["trace"]["totals"]["rollbacks"] for r in records]
    return {
        "answers": len(records),
        "stop_reasons": dict(Counter(r["trace"]["stop_reason"] for r in records)),
        "sentences": len(points),
        "committed_at_first_try": sum(
            p["outcome"] == "emitted" and not p["rollbacks"] for p in points
        ),
        "committed_after_a_retry": dict(
            Counter(
                p["recovered_by"] for p in points if p["outcome"] == "emitted" and p["rollbacks"]
            )
        ),
        "replaced_by_the_refusal": sum(p["outcome"] == "refused" for p in points),
        "rollbacks": sum(rollbacks),
        "answers_with_no_rollback": sum(n == 0 for n in rollbacks),
        "rollbacks_per_answer_max": max(rollbacks, default=0),
        "tokens_in_final_answers": sum(r["trace"]["answer_tokens"] for r in records),
        "tokens_discarded": sum(r["trace"]["totals"]["tokens_discarded"] for r in records),
        "injections": sum(r["trace"]["totals"]["injections"] for r in records),
        "tokens_injected": sum(r["trace"]["totals"]["tokens_injected"] for r in records),
        "first_attempt_reasons": dict(
            Counter(
                reason
                for p in points
                if p["rollbacks"]
                for reason in p["attempts"][0]["verdict"]["reasons"]
            )
        ),
    }


def cache(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Per decode call, the tokens the server reused as a share of the prompt: first attempts of
    an answer's first sentence start cold; a retry should reuse the prompt and the answer so far."""
    first, retries = [], []
    for r in records:
        prompt = r["trace"]["prompt_tokens"]
        for n, p in enumerate(r["trace"]["sentences"]):
            for k, a in enumerate(p["attempts"]):
                if not a["decode_calls"]:
                    continue
                share = a["prefix_cache_hit_tokens"] / a["decode_calls"] / prompt
                if k:
                    retries.append(share)
                elif n == 0:
                    first.append(share)
    return {
        "first_sentence_first_attempt_p50": pct(first, 0.5),
        "retry_attempts": len(retries),
        "retry_p50": pct(retries, 0.5),
        "retry_min": round(min(retries), 2) if retries else None,
    }


def times(records: list[dict[str, Any]]) -> dict[str, Any]:
    seconds = [r["seconds"] for r in records]
    decode = [r["trace"]["totals"]["decode_latency_ns"] / 1e9 for r in records]
    judge = [r["trace"]["totals"]["nli_latency_ns"] / 1e9 for r in records]
    calls = [c["ms"] / 1000 for r in records for c in r["judge_calls"]]
    return {
        "seconds_per_answer_p50": pct(seconds, 0.5),
        "seconds_per_answer_p95": pct(seconds, 0.95),
        "generation_seconds_per_answer_p50": pct(decode, 0.5),
        "judge_seconds_per_answer_p50": pct(judge, 0.5),
        "judge_share_of_time": round(sum(judge) / max(sum(seconds), 1e-9), 3),
        "judge_calls": len(calls),
        "judge_calls_per_answer": round(len(calls) / max(len(records), 1), 1),
        "seconds_per_judge_call_p50": pct(calls, 0.5),
        "seconds_per_judge_call_p95": pct(calls, 0.95),
        "judge_labels": dict(Counter(c["label"] for r in records for c in r["judge_calls"])),
        "seconds_total": round(sum(seconds), 1),
        "mean_seconds_per_answer": round(statistics.mean(seconds), 2) if seconds else 0.0,
    }


def outcome(arm: str, records: list[dict[str, Any]]) -> dict[str, Any] | None:
    """T4, once the final answers are graded. Each graded sentence is matched to its point in the
    trace by text, in order."""
    us = fe.units(merged=True)
    graded = fe.merged_grades(us)
    if any(g not in {"yes", "no", "unsure"} for g in graded.values()):
        return None
    by_key = {r["key"]: r for r in records}
    rows = []
    for u in us:
        if u["mode"] != arm or graded[u["key"]] == "unsure":
            continue
        points = by_key[f"{u['id']}:{arm}"]["trace"]["sentences"]
        point = next((p for p in points if p["text"].strip() == u["sentence"].strip()), None)
        rows.append({"grade": graded[u["key"]], "point": point})
    wrong = sum(r["grade"] == "no" for r in rows)
    retried = [
        r
        for r in rows
        if r["point"] and r["point"]["outcome"] == "emitted" and r["point"]["rollbacks"]
    ]
    refusals = [r for r in rows if r["point"] and r["point"]["outcome"] == "refused"]
    base_wrong, base_all = BASELINE[arm]
    out: dict[str, Any] = {
        "sentences": len(rows),
        "matched_to_the_trace": sum(r["point"] is not None for r in rows),
        "wrong": wrong,
        "share_wrong": round(wrong / max(len(rows), 1), 3),
        "interval_95": sj.wilson(wrong, len(rows)),
        "baseline_without_a_loop": {
            "wrong": base_wrong,
            "sentences": base_all,
            "share_wrong": round(base_wrong / base_all, 3),
        },
        "committed_after_a_rollback": len(retried),
        "of_which_right": sum(r["grade"] == "yes" for r in retried),
        # The engine's refusal is counted apart (GRID § Stop 59): a lost point, not a wrong claim.
        "wrong_that_are_the_engine_refusal": sum(r["grade"] == "no" for r in refusals),
        "wrong_among_generated_sentences": wrong - sum(r["grade"] == "no" for r in refusals),
        "generated_sentences": len(rows) - len(refusals),
        "refusal_sentences": len(refusals),
        "refusals_graded_right": sum(r["grade"] == "yes" for r in refusals),
        "share_replaced_by_the_refusal": round(len(refusals) / max(len(rows), 1), 3),
    }
    if arm == "closed":
        out["repairs"] = bool(out["share_wrong"] <= REPAIR * base_wrong / base_all)
    else:
        out["costs_little"] = bool(out["share_replaced_by_the_refusal"] <= REFUSED)
    return out


def main() -> None:
    kept = traces()
    out: dict[str, Any] = {"set": fb.SET, "arms": {}}
    for arm, title in ARMS.items():
        records = [r for k, r in kept.items() if k.endswith(f":{arm}")]
        if not records:
            continue
        result: dict[str, Any] = {"T1_mechanics": mechanics(records), "T2_cache": cache(records)}
        result["T3_time"] = times(records)
        try:
            result["T4_outcome"] = outcome(arm, records)
        except FileNotFoundError:  # no sheet yet
            result["T4_outcome"] = None
        out["arms"][f"{arm}: {title}"] = result
    target = ROOT / "results" / f"{fb.SET}_arms"
    target.mkdir(parents=True, exist_ok=True)
    (target / "live.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
