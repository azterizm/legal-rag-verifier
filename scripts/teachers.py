"""Stops 44 and 45: teacher labels through the router, one call per batch of clauses, resumable.

Each batch's result is written as soon as it returns (``results/distill/labels/<name>.jsonl``, one
row per clause under its stop 42 single-clause prompt key); a rerun asks only batches not done.
A batch that still fails is logged and asked again on the next run. Opus 5.5 stops cleanly at
its cap (``router.BudgetExceededError``).

  uv run python scripts/teachers.py dev gemini     # stop 44: Part A, Part B, statutes
  uv run python scripts/teachers.py dev opus46
  uv run python scripts/teachers.py dev opus55     # Part A and Part B only
  uv run python scripts/teachers.py check          # stop 44 readings → results/distill/check44.json
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import auditor_judge as aj  # type: ignore[import-not-found]  # noqa: E402
import router  # type: ignore[import-not-found]  # noqa: E402

OUT = ROOT / "results/distill"
TEACHERS = {"gemini": router.GEMINI, "opus46": router.OPUS46, "opus55": router.OPUS55}
WORKERS = {"gemini": 6, "opus46": 2, "opus55": 2}
_lock = threading.Lock()


def router_chat(model: str) -> Callable[[list[dict[str, str]]], dict[str, Any]]:
    def chat(messages: list[dict[str, str]]) -> dict[str, Any]:
        out = router.chat(model, messages)
        return {**out, "tokens": out["usage"].get("completion_tokens")}

    return chat


def label_path(name: str) -> Path:
    return OUT / "labels" / f"{name}.jsonl"


def batch_log(name: str) -> Path:
    return OUT / "labels" / f"{name}.batches.jsonl"


def done_batches(name: str) -> set[str]:
    path = batch_log(name)
    if not path.exists():
        return set()
    rows = map(json.loads, path.read_text(encoding="utf-8").splitlines())
    return {r["batch"] for r in rows if r["ok"]}


def read_labels(name: str) -> dict[str, dict[str, Any]]:
    path = label_path(name)
    if not path.exists():
        return {}
    return {r["sha"]: r for r in map(json.loads, path.read_text(encoding="utf-8").splitlines())}


def _write(name: str, batch: Mapping[str, Any], result: Mapping[str, Any]) -> None:
    ok = result.get("labels") is not None
    with _lock:
        label_path(name).parent.mkdir(parents=True, exist_ok=True)
        if ok:
            with label_path(name).open("a", encoding="utf-8") as f:
                for sha, lab in zip(batch["keys"], result["labels"], strict=True):
                    row = {"sha": sha, **lab, "batch": batch["key"], "n": len(batch["keys"])}
                    row |= {"ms": result["ms"], "attempts": result["attempts"]}
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
        with batch_log(name).open("a", encoding="utf-8") as f:
            entry = {"batch": batch["key"], "ok": ok, "clauses": len(batch["keys"])}
            entry |= {"ms": result.get("ms"), "error": result.get("error")}
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def label(name: str, teacher: str, todo_batches: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Ask every batch not yet done; stop scheduling new ones once the cap is reached."""
    done = done_batches(name)
    todo = [b for b in todo_batches if b["key"] not in done]
    print(f"{name}: {len(todo_batches)} batches, {len(done)} done, {len(todo)} to ask", flush=True)
    chat = router_chat(TEACHERS[teacher])
    stop = threading.Event()
    workers = WORKERS[teacher]
    counts = {"ok": 0, "failed": 0, "skipped_cap": 0}

    def one(batch: Mapping[str, Any]) -> None:
        if stop.is_set():
            counts["skipped_cap"] += 1
            return
        try:
            result = aj.ask_batch(chat, batch)
        except router.BudgetExceededError as exc:
            stop.set()
            counts["skipped_cap"] += 1
            print(f"{name}: cap reached ({exc})", flush=True)
            return
        except (router.RouterError, KeyError, ValueError) as exc:
            result = {"labels": None, "error": repr(exc), "ms": 0, "attempts": 0}
        _write(name, batch, result)
        counts["ok" if result.get("labels") is not None else "failed"] += 1
        n = counts["ok"] + counts["failed"]
        if n % 20 == 0:
            print(f"{name}: {n}/{len(todo)}", flush=True)

    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(one, todo))
    print(f"{name}: {counts}", flush=True)
    return counts


def label_clauses(name: str, teacher: str, requests: Mapping[str, str]) -> dict[str, int]:
    """Per-clause labels on the stop 42 prompt, written as each returns. A rerun asks only the
    prompts with no label yet or an error; it stops scheduling at a capped model's cap."""
    have = {k for k, v in read_labels(name).items() if v["label"] in aj.LABELS}
    todo = {k: v for k, v in requests.items() if k not in have}
    print(f"{name}: {len(requests)} prompts, {len(have)} done, {len(todo)} to ask", flush=True)
    chat = router_chat(TEACHERS[teacher])
    capped = threading.Event()
    counts = {"ok": 0, "failed": 0, "skipped_cap": 0}

    def guarded(messages: list[dict[str, str]]) -> dict[str, Any]:
        if capped.is_set():
            raise router.BudgetExceededError("cap reached")
        try:
            return chat(messages)
        except router.BudgetExceededError:
            capped.set()
            raise

    def done(sha: str, result: dict[str, Any]) -> None:
        ok = result.get("label") in aj.LABELS
        counts["ok" if ok else "failed"] += 1
        with _lock:
            label_path(name).parent.mkdir(parents=True, exist_ok=True)
            with label_path(name).open("a", encoding="utf-8") as f:
                f.write(json.dumps({"sha": sha, **result}, ensure_ascii=False) + "\n")

    def one(sha: str) -> None:
        try:
            result = aj.ask(guarded, todo[sha])
        except router.BudgetExceededError:
            counts["skipped_cap"] += 1
            return
        except (router.RouterError, KeyError, ValueError) as exc:
            result = {"label": "error", "passage": 0, "reason": repr(exc), "attempts": 0, "ms": 0}
        done(sha, result)
        n = counts["ok"] + counts["failed"]
        if n % 50 == 0:
            print(f"{name}: {n}/{len(todo)}", flush=True)

    with ThreadPoolExecutor(WORKERS[teacher]) as pool:
        list(pool.map(one, list(todo)))
    print(f"{name}: {counts}", flush=True)
    return counts


def dev_batches(levels: Sequence[str] = ("A", "B", "S")) -> list[dict[str, Any]]:
    """Stop 42's texts in answer order, grouped per answer (Part B) or per text."""
    texts, _, recorded = aj.recorded_sets()
    units = [
        {**r, "group": t["item"] if t["level"] == "B" else t["key"]}
        for t, r in zip(texts, recorded, strict=True)
        if t["level"] in levels
    ]
    out: list[dict[str, Any]] = aj.batches(units)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["dev", "check"])
    parser.add_argument("teacher", nargs="?", choices=list(TEACHERS))
    args = parser.parse_args()
    if args.command == "dev":
        levels = ("A", "B") if args.teacher == "opus55" else ("A", "B", "S")
        label(f"dev-{args.teacher}", args.teacher, dev_batches(levels))
    else:
        from check44 import main as check  # type: ignore[import-not-found]  # noqa: PLC0415

        check()


if __name__ == "__main__":
    main()
