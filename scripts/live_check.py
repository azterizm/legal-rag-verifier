"""Stop 78: live check of the released package against a real judge server.

Loads fresh2's 151 graded units and runs JudgedVerifier with the measured preset qwen27-ar4,
evaluating accuracy, validity and timing against the rules fixed in GRID.md Stop 78.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

from legal_rag_verifier.judge import STRICT_FIGURES, Judge, JudgedVerifier
from legal_rag_verifier.verifier import SentenceVerdict, Verdict

ROOT = Path(__file__).resolve().parent.parent
LABEL_FILE = "labels/qwen27-ar4.short.jsonl"
DOMAINS = {"software": "software", "legal": "statutes"}

# Rules fixed in GRID.md Stop 78
A1_CORRECT_MIN = 132
A1_CORRECT_MAX = 140
A2_MAX_ERROR_RATE = 0.05
A3_MAX_SERVER_P50_S = 0.81


# Verbatim from tests/test_judge_replay.py:117-128
def _cell(
    units: Sequence[Mapping[str, Any]], verdicts: Mapping[str, SentenceVerdict]
) -> dict[str, int]:
    rolled = [u for u in units if verdicts[u["key"]].verdict is not Verdict.EMIT]
    right, wrong = sum(int(u["right"]) for u in units), sum(int(u["wrong"]) for u in units)
    false_rollbacks = sum(int(u["right"]) for u in rolled)
    caught = sum(int(u["wrong"]) for u in rolled)
    assert right + wrong == len(units)  # noqa: S101
    return {
        "units": len(units),
        "correct": right - false_rollbacks + caught,
        "false_rollbacks": false_rollbacks,
        "caught": caught,
    }


def _p95(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]


def _private(module: str, name: str) -> ModuleType:
    alias = f"_live_check_{name}_{module}"
    spec = importlib.util.spec_from_file_location(alias, ROOT / "scripts" / f"{module}.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load scripts/{module}.py")
    copy = importlib.util.module_from_spec(spec)
    sys.modules[alias] = copy
    spec.loader.exec_module(copy)
    return copy


def _load(name: str = "fresh2") -> tuple[ModuleType, ModuleType]:
    prev_fresh_set = os.environ.get("FRESH_SET")
    os.environ["FRESH_SET"] = name
    try:
        fb = _private("fresh_battery", name)
        assert name == fb.SET  # noqa: S101
        sys.modules["fresh_battery"] = fb
        fe = _private("fresh_eval", name)
        assert ROOT / "results" / name == fe.OUT  # noqa: S101
        return fb, fe
    finally:
        if prev_fresh_set is None:
            os.environ.pop("FRESH_SET", None)
        else:
            os.environ["FRESH_SET"] = prev_fresh_set


def _ping_models(url: str, api_key_env: str | None, count: int = 20) -> list[float]:
    base = url.rstrip("/")
    models_url = f"{base}/v1/models"
    headers: dict[str, str] = {}
    if api_key_env:
        key = os.environ.get(api_key_env, "").strip()
        if key:
            headers["Authorization"] = f"Bearer {key}"
    latencies_ms: list[float] = []
    for _ in range(count):
        req = urllib.request.Request(models_url, headers=headers, method="GET")  # noqa: S310
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=30.0) as resp:  # noqa: S310
            resp.read()
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)
    return latencies_ms


def _score_units(
    fe: ModuleType, verdicts: Mapping[str, SentenceVerdict]
) -> dict[str, dict[str, int]]:
    us = fe.units(merged=True)
    graded = fe.merged_grades(us)
    units = [
        {**u, "right": graded[u["key"]] == "yes", "wrong": graded[u["key"]] == "no"} for u in us
    ]
    units = [u for u in units if u["right"] or u["wrong"]]
    cells: dict[str, dict[str, int]] = {"total": _cell(units, verdicts)}
    for domain, cell_name in DOMAINS.items():
        part = _cell([u for u in units if u["domain"] == domain], verdicts)
        cells[cell_name] = {k: part[k] for k in ("units", "correct", "false_rollbacks", "caught")}
    return cells


def _check_agreement(
    all_calls: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, int], dict[str, int]]:
    label_path = ROOT / "results" / "fresh2" / LABEL_FILE
    recorded_labels: dict[str, str] = {}
    if label_path.is_file():
        for raw_line in label_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line:
                entry = json.loads(line)
                recorded_labels[entry["sha"]] = entry["label"]

    # Unique prompts
    unique_calls: dict[str, str] = {}
    for call in all_calls:
        sha = str(call["sha"])
        if sha not in unique_calls:
            unique_calls[sha] = str(call["label"])

    matched_u = sum(1 for sha in unique_calls if sha in recorded_labels)
    same_u = sum(
        1
        for sha, lbl in unique_calls.items()
        if sha in recorded_labels and lbl == recorded_labels[sha]
    )
    diff_u = sum(
        1
        for sha, lbl in unique_calls.items()
        if sha in recorded_labels and lbl != recorded_labels[sha]
    )
    not_found_u = sum(1 for sha in unique_calls if sha not in recorded_labels)

    # All calls
    matched_all = sum(1 for call in all_calls if str(call["sha"]) in recorded_labels)
    same_all = sum(
        1
        for call in all_calls
        if (sha := str(call["sha"])) in recorded_labels and call["label"] == recorded_labels[sha]
    )
    diff_all = sum(
        1
        for call in all_calls
        if (sha := str(call["sha"])) in recorded_labels and call["label"] != recorded_labels[sha]
    )
    not_found_all = sum(1 for call in all_calls if str(call["sha"]) not in recorded_labels)

    return (
        {
            "matched": matched_u,
            "same_label": same_u,
            "different_label": diff_u,
            "not_found": not_found_u,
        },
        {
            "matched": matched_all,
            "same_label": same_all,
            "different_label": diff_all,
            "not_found": not_found_all,
        },
    )


def _run_verifier(
    fb: ModuleType, url: str, api_key_env: str | None
) -> tuple[dict[str, SentenceVerdict], list[dict[str, Any]]]:
    rows: dict[str, Any] = {r["id"]: r for r in fb.rows()}
    built: dict[str, Any] = {}
    judge = Judge.from_preset("qwen27-ar4", url, api_key_env=api_key_env)
    verifier = JudgedVerifier(judge, STRICT_FIGURES)
    assert verifier.config == STRICT_FIGURES  # noqa: S101

    verdicts: dict[str, SentenceVerdict] = {}
    all_calls: list[dict[str, Any]] = []

    for answer_key, answer in sorted(fb.answers().items()):
        row = rows[answer_key.split(":")[0]]
        if row["id"] not in built:
            built[row["id"]] = fb.premise(row)
        out = verifier.check_text(built[row["id"]], answer["text"], query=row["query"])
        verdicts |= {f"{answer_key}:{n}": v for n, v in enumerate(out)}
        all_calls.extend({**call, "answer_key": answer_key} for call in verifier.calls)

    return verdicts, all_calls


def _print_report(
    summary: Mapping[str, Any],
) -> None:
    rules = summary["rules"]
    cells = summary["cells"]
    timing = summary["timing"]
    agreement = summary["agreement"]
    a1 = rules["A1"]
    a2 = rules["A2"]
    a3 = rules["A3"]

    unique_agree = agreement["unique_prompts"]
    all_agree = agreement["all_calls"]
    total_calls = a2["total_calls"]
    unique_prompts = summary["calls_unique"]

    print("--- Live Check Summary ---")
    print(
        f"Fresh2 units: {a1['units']} | Correct: {a1['correct']} "
        f"({a1['accuracy_pct']:.1f} %) | "
        f"False rollbacks: {cells['total']['false_rollbacks']} | "
        f"Caught: {cells['total']['caught']}"
    )
    for dom_name in ("software", "statutes"):
        c = cells[dom_name]
        print(
            f"  {dom_name.capitalize()}: {c['units']} units, {c['correct']} correct, "
            f"{c['false_rollbacks']} false rollbacks, {c['caught']} caught"
        )
    print(f"Judge calls: {total_calls} ({unique_prompts} unique, {a2['error_calls']} errors)")
    print(
        f"Label agreement: {unique_agree['matched']}/{unique_prompts} matched "
        f"({unique_agree['same_label']} same, {unique_agree['different_label']} different, "
        f"{unique_agree['not_found']} not found) [{all_agree['matched']}/{total_calls} calls]"
    )
    print(
        f"Latency: server-side p50 = {timing['server_side_p50_s']:.3f} s "
        f"(client p50 = {timing['client_p50_ms'] / 1000.0:.3f} s, "
        f"client p95 = {timing['client_p95_ms'] / 1000.0:.3f} s, "
        f"models p50 = {timing['models_p50_ms'] / 1000.0:.3f} s)"
    )
    print("--- Rules ---")
    print(
        f"A1 accuracy: {'PASS' if a1['passed'] else 'FAIL'} "
        f"({a1['correct']}/{a1['units']} correct, {a1['accuracy_pct']:.1f} %, "
        f"range [{A1_CORRECT_MIN}, {A1_CORRECT_MAX}])"
    )
    print(
        f"A2 validity: {'PASS' if a2['passed'] else 'FAIL'} "
        f"({a2['error_calls']}/{a2['total_calls']} errors, {a2['error_rate_pct']:.1f} %, "
        f"threshold < {A2_MAX_ERROR_RATE * 100:.0f} %)"
    )
    print(
        f"A3 time:     {'PASS' if a3['passed'] else 'FAIL'} "
        f"(server p50 = {timing['server_side_p50_s']:.3f} s <= {A3_MAX_SERVER_P50_S} s)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Live check for legal-rag-verifier stop 78")
    parser.add_argument("--url", required=True, help="Base URL of the judge server")
    parser.add_argument(
        "--api-key-env",
        default="LIVE_JUDGE_API_KEY",
        help="Environment variable name holding the API key",
    )
    parser.add_argument(
        "--out",
        default="results/fresh2-live78",
        help="Output directory for calls.jsonl and summary.json",
    )
    args = parser.parse_args()

    # 1. 20 sequential round trips to /v1/models
    models_latencies_ms = _ping_models(args.url, args.api_key_env, count=20)

    # 2. Run verifier
    fb, fe = _load("fresh2")
    verdicts, all_calls = _run_verifier(fb, args.url, args.api_key_env)

    # 3. Score with _cell
    cells = _score_units(fe, verdicts)

    # 4. Label agreement
    unique_agree, all_agree = _check_agreement(all_calls)

    # 5. Latency metrics
    client_latencies_ms = [float(c["ms"]) for c in all_calls]
    client_p50_ms = statistics.median(client_latencies_ms) if client_latencies_ms else 0.0
    client_p95_ms = _p95(client_latencies_ms) if client_latencies_ms else 0.0
    models_p50_ms = statistics.median(models_latencies_ms) if models_latencies_ms else 0.0
    server_side_p50_s = (client_p50_ms - models_p50_ms) / 1000.0

    # 6. Rules evaluation
    total_units = cells["total"]["units"]
    correct = cells["total"]["correct"]
    a1_pct = (correct / total_units) * 100.0 if total_units > 0 else 0.0
    a1_pass = A1_CORRECT_MIN <= correct <= A1_CORRECT_MAX

    total_calls = len(all_calls)
    unique_prompts = len({str(c["sha"]) for c in all_calls})
    error_calls = sum(1 for c in all_calls if c.get("label") == "error")
    error_rate = (error_calls / total_calls) if total_calls > 0 else 0.0
    a2_pass = error_rate < A2_MAX_ERROR_RATE

    a3_pass = server_side_p50_s <= A3_MAX_SERVER_P50_S

    # 7. Write outputs
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "calls.jsonl").open("w", encoding="utf-8") as f:
        for call in all_calls:
            f.write(json.dumps(call, ensure_ascii=False) + "\n")

    summary = {
        "calls_total": total_calls,
        "calls_unique": unique_prompts,
        "rules": {
            "A1": {
                "name": "A1 accuracy",
                "passed": a1_pass,
                "correct": correct,
                "units": total_units,
                "accuracy_pct": round(a1_pct, 1),
                "threshold": f"{A1_CORRECT_MIN} to {A1_CORRECT_MAX} [87.1 %, 93.1 %]",
            },
            "A2": {
                "name": "A2 validity",
                "passed": a2_pass,
                "error_calls": error_calls,
                "total_calls": total_calls,
                "error_rate_pct": round(error_rate * 100.0, 2),
                "threshold": f"< {A2_MAX_ERROR_RATE * 100:.0f} % errors",
            },
            "A3": {
                "name": "A3 time",
                "passed": a3_pass,
                "server_side_p50_s": round(server_side_p50_s, 4),
                "client_p50_s": round(client_p50_ms / 1000.0, 4),
                "client_p95_s": round(client_p95_ms / 1000.0, 4),
                "models_p50_s": round(models_p50_ms / 1000.0, 4),
                "threshold": f"<= {A3_MAX_SERVER_P50_S} s",
            },
        },
        "cells": cells,
        "agreement": {
            "matched": unique_agree["matched"],
            "same_label": unique_agree["same_label"],
            "different_label": unique_agree["different_label"],
            "not_found": unique_agree["not_found"],
            "unique_prompts": unique_agree,
            "all_calls": all_agree,
        },
        "timing": {
            "models_roundtrips_ms": [round(m, 2) for m in models_latencies_ms],
            "client_p50_ms": round(client_p50_ms, 2),
            "client_p95_ms": round(client_p95_ms, 2),
            "models_p50_ms": round(models_p50_ms, 2),
            "server_side_p50_s": round(server_side_p50_s, 4),
        },
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # 8. Print report
    _print_report(summary)


if __name__ == "__main__":
    main()
