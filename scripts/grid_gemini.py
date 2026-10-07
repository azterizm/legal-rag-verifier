"""Grid cells 4A (full retry) and 4C (sentence continuation) on Gemini via the router (paid: run
only on a go). The verifier runs here (Apple M4, MPS); its time is reported apart from generation.

  uv run python scripts/grid_gemini.py --cells 4A 4C [--limit N]

Router: the user-named endpoint and model only (``localhost:8317``, ``gemini-3.8-flash-high``),
temperature 0, no other parameters. Resumable: rows already in ``results/grid/<cell>.jsonl`` are
skipped.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from enrich_premises import MODEL, ROUTER_URL, _key  # type: ignore[import-not-found]  # noqa: E402
from grid_cells import (  # type: ignore[import-not-found]  # noqa: E402
    Messages,
    Reply,
    continuation,
    full_retry,
)
from grid_prompts import premise, rows  # type: ignore[import-not-found]  # noqa: E402

from legal_rag_verifier.engine import SYSTEM_PROMPT  # noqa: E402
from legal_rag_verifier.verifier import Verifier  # noqa: E402

OUT = ROOT / "results/grid"


def chat(messages: Messages) -> Reply:
    body = json.dumps({"model": MODEL, "messages": messages, "temperature": 0}).encode()
    request = urllib.request.Request(  # noqa: S310 - the fixed localhost router URL
        ROUTER_URL,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {_key()}"},
    )
    t0 = time.perf_counter_ns()
    with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310
        reply = json.loads(response.read())
    latency = time.perf_counter_ns() - t0
    usage = reply.get("usage") or {}
    return Reply(
        reply["choices"][0]["message"].get("content") or "",
        int(usage.get("completion_tokens", 0)),
        int(usage.get("prompt_tokens", 0)),
        latency,
        usage=usage,
    )


def done_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {json.loads(line)["id"] for line in path.read_text(encoding="utf-8").splitlines()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cells", nargs="+", choices=["4A", "4C"], default=["4A", "4C"])
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    from legal_rag_verifier.nli import SentenceNLIVerifier  # noqa: PLC0415

    verifier = Verifier(SentenceNLIVerifier("cross-encoder/nli-deberta-v3-base"))
    run = {"4A": full_retry, "4C": continuation}
    OUT.mkdir(parents=True, exist_ok=True)
    for cell in args.cells:
        path = OUT / f"{cell}.jsonl"
        done = done_ids(path)
        for row in rows()[: args.limit]:
            if row["id"] in done:
                continue
            record = run[cell](chat, verifier, row["query"], premise(row), SYSTEM_PROMPT)
            record = {"cell": cell, "id": row["id"], "generator": MODEL, **record}
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(
                f"{cell} {row['id']}: retries {record['retries']}, refusals {record['refusals']}, "
                f"resolved {record['resolved']}, {record['wall_ns'] / 1e9:.1f} s",
                flush=True,
            )


if __name__ == "__main__":
    main()
