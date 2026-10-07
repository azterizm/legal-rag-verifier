"""Independent judge for the 2x2 grid (docs/GRID.md): ``gpt-oss-120b-medium`` via the router.

Rule A's grounding test is the detector's own claim check; this model is not, so it can catch what
the shared detector (and therefore every cell's remediation) misses. Blind: one answer at a time,
in a fixed random order across cells, with only the query and the provisions; never the cell, the
generator or the detector's verdicts. Temperature 0. Paid: run only on a go, after rule A and the
blind human labels.

  uv run python scripts/grid_judge.py            # every final answer → results/grid/judge.jsonl
  uv run python scripts/grid_judge.py --agreement results/grid/review_labels.csv
  uv run python scripts/grid_judge.py --split dev --cells 4B-inject-turn 4B-inject-v2   # stop 30

Resumable: answers already judged (same cell, id and answer text) are skipped.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "batteries/verifier"))

from enrich_premises import ROUTER_URL, _key  # type: ignore[import-not-found]  # noqa: E402
from grid_prompts import premise, rows  # type: ignore[import-not-found]  # noqa: E402
from grid_score import (  # type: ignore[import-not-found]  # noqa: E402
    ALL_CELLS,
    CELLS,
    GRID,
    SEED,
    load,
)

from legal_rag_verifier.engine import render_premise  # noqa: E402

MODEL = "gpt-oss-120b-medium"  # named by you, 2026-10-06; no other model is called
OUT = GRID / "judge.jsonl"
SYSTEM = (
    "You are a careful UK legal reviewer. You check an answer against the statutory provisions "
    "it was written from. Judge only against the provisions given, not outside knowledge. Reply "
    "with a single JSON object."
)
USER = """Question: {query}

Provisions:
<<<
{provisions}
>>>

Answer to review:
<<<
{answer}
>>>

Return JSON with keys:
  "sentences": one entry per sentence of the answer, in order, each
     {{"sentence": the sentence, "label": "supported" | "unsupported" | "contradicted" | "no_claim",
       "error": null | "wrong_figure" | "wrong_citation" | "wrong_instrument" |
                "dropped_qualifier" | "fabricated" | "other"}},
  "answers_question": true if the answer addresses what was asked, else false,
  "should_abstain": true if the provisions do not contain the answer to the question,
  "abstains": true if the answer says it cannot answer from the provisions,
  "verdict": "correct" if every claim is supported by the provisions and the answer either answers
     the question or, where the provisions do not contain the answer, correctly says so;
     otherwise "incorrect",
  "reason": one sentence."""
PROMPT_SHA = hashlib.sha256((SYSTEM + USER).encode()).hexdigest()


def chat(messages: list[dict[str, str]]) -> tuple[str, dict[str, Any], int]:
    body = json.dumps({"model": MODEL, "messages": messages, "temperature": 0}).encode()
    request = urllib.request.Request(  # noqa: S310 - the fixed localhost router URL
        ROUTER_URL,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {_key()}"},
    )
    t0 = time.perf_counter_ns()
    with urllib.request.urlopen(request, timeout=600) as response:  # noqa: S310
        reply = json.loads(response.read())
    content = reply["choices"][0]["message"].get("content") or ""
    return content, reply.get("usage") or {}, time.perf_counter_ns() - t0


def _json(text: str) -> dict[str, Any]:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in output")
    parsed: dict[str, Any] = json.loads(text[start : end + 1])
    if parsed.get("verdict") not in {"correct", "incorrect"}:
        raise ValueError(f"bad verdict: {parsed.get('verdict')!r}")
    return parsed


def judge(row: dict[str, Any], answer: str) -> dict[str, Any]:
    """One verdict; re-asks (at most twice) only when the reply is not the JSON asked for."""
    user = USER.format(
        query=row["query"],
        provisions=render_premise(premise(row, enrichment=None)) or "(none)",
        answer=answer or "(empty answer)",
    )
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    out, latency = "", 0
    usage: dict[str, Any] = {}
    for attempt in range(1, 4):
        out, usage, latency = chat(messages)
        try:
            return {**_json(out), "attempts": attempt, "usage": usage, "latency_ns": latency}
        except ValueError:
            messages = [
                *messages[:2],
                {"role": "assistant", "content": out},
                {"role": "user", "content": "Reply with ONLY the JSON object asked for."},
            ]
    return {"verdict": None, "error": f"no JSON after 3 attempts: {out[:200]!r}", "usage": usage}


def _answer_sha(answer: str) -> str:
    return hashlib.sha256(answer.encode()).hexdigest()


def _load(cell: str, split: str) -> dict[str, dict[str, Any]]:
    if split == "test":
        loaded: dict[str, dict[str, Any]] = load(cell)
        return loaded
    path = GRID / split / f"{cell}.jsonl"
    records = (json.loads(x) for x in path.read_text(encoding="utf-8").splitlines())
    return {r["id"]: r for r in records}


def run(split: str = "test", cells: tuple[str, ...] = ALL_CELLS) -> None:
    by_id = {r["id"]: r for r in rows(split)}
    out = OUT if split == "test" else GRID / split / "judge.jsonl"
    items = [(cell, r) for cell in cells for r in _load(cell, split).values()]
    random.Random(SEED + 1).shuffle(items)  # noqa: S311 - a reproducible order, not a secret
    done: set[tuple[str, str, str]] = set()
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            j = json.loads(line)
            done.add((j["cell"], j["id"], j["answer_sha256"]))
    for n, (cell, r) in enumerate(items, 1):
        sha = _answer_sha(r["answer"])
        if (cell, r["id"], sha) in done:
            continue
        verdict = judge(by_id[r["id"]], r["answer"])
        record = {
            "cell": cell,
            "id": r["id"],
            "answer_sha256": sha,
            "judge": MODEL,
            "prompt_sha256": PROMPT_SHA,
            **verdict,
        }
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"{n}/{len(items)} {cell} {r['id']}: {verdict.get('verdict')}", flush=True)


def kappa(pairs: list[tuple[bool, bool]]) -> float | None:
    n = len(pairs)
    if not n:
        return None
    observed = sum(a == b for a, b in pairs) / n
    pa, pb = sum(a for a, _ in pairs) / n, sum(b for _, b in pairs) / n
    expected = pa * pb + (1 - pa) * (1 - pb)
    return round((observed - expected) / (1 - expected), 4) if expected < 1 else None


def agreement(labels_path: Path) -> dict[str, Any]:
    """Judge vs your blind labels, per cell and overall (agreement and Cohen's kappa)."""
    key = {k["item"]: k for k in json.loads((GRID / "review_key.json").read_text())}
    with labels_path.open(encoding="utf-8") as f:
        labels = {int(r["item"]): r["label"].strip().lower() for r in csv.DictReader(f)}
    verdicts = {
        (j["cell"], j["id"]): j["verdict"]
        for j in (json.loads(x) for x in OUT.read_text(encoding="utf-8").splitlines())
    }
    pairs_by_cell: dict[str, list[tuple[bool, bool]]] = {c: [] for c in CELLS}
    for item, k in key.items():
        human, judged = labels.get(item), verdicts.get((k["cell"], k["id"]))
        if human in {"correct", "incorrect"} and judged in {"correct", "incorrect"}:
            pairs_by_cell[k["cell"]].append((human == "correct", judged == "correct"))
    out: dict[str, Any] = {}
    everything = [p for pairs in pairs_by_cell.values() for p in pairs]
    for cell, pairs in [*pairs_by_cell.items(), ("all", everything)]:
        out[cell] = {
            "pairs": len(pairs),
            "agreement": round(sum(a == b for a, b in pairs) / len(pairs), 4) if pairs else None,
            "kappa": kappa(pairs),
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agreement", type=Path, default=None)
    parser.add_argument("--split", choices=["test", "dev"], default="test")
    parser.add_argument("--cells", nargs="+", default=list(ALL_CELLS))
    args = parser.parse_args()
    if args.agreement:
        print(json.dumps(agreement(args.agreement), indent=1))
    else:
        run(args.split, tuple(args.cells))


if __name__ == "__main__":
    main()
