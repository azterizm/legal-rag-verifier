"""Injection v2's abstention gate: what legal-rag-router 0.1.0 actually returns for each grid query.

The grid rows carry ``route_status``, which is the concept battery's *expected* label, so it cannot
serve as the gate. This runs the released router (no model, no network) on every query of a split,
with the index from the router's own checkout, and records its status, next action and messages.
A query whose next action is ``REFUSE`` is answered with the router's message and never reaches
generation; every other status goes on to generation with the prompt's premise, as before.

  uv run --with ~/Code/legal-rag-router python scripts/grid_routes.py --split dev
  uv run --with ~/Code/legal-rag-router python scripts/grid_routes.py --split test
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROUTER = Path.home() / "Code/legal-rag-router"


def main() -> None:
    from legal_rag_router import Router  # noqa: PLC0415

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["dev", "test"], default="test")
    split = parser.parse_args().split
    rows = [
        json.loads(x)
        for x in (ROOT / f"batteries/grid/{split}.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    router = Router.from_path(ROUTER / "data/index")
    out = {}
    for row in rows:
        t0 = time.perf_counter_ns()
        result = router.route(row["query"])
        out[row["id"]] = {
            "status": str(result.status.value),
            "next_action": str(result.next_action.value),
            "messages": list(result.messages),
            "index_snapshot": result.index_snapshot,
            "latency_ns": time.perf_counter_ns() - t0,
            "expected": row["route_status"],
        }
    path = ROOT / f"batteries/grid/routes-{split}.json"
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    refused = [k for k, v in out.items() if v["next_action"] == "REFUSE"]
    print(
        json.dumps(
            {
                "split": split,
                "queries": len(out),
                "refused": len(refused),
                "refused_but_not_expected_abstention": [
                    k for k in refused if not out[k]["expected"].startswith("EPISTEMIC_ABSTENTION")
                ],
                "expected_abstention_not_refused": [
                    k
                    for k, v in out.items()
                    if v["expected"].startswith("EPISTEMIC_ABSTENTION") and k not in refused
                ],
                "status_matches_expected": sum(v["status"] == v["expected"] for v in out.values()),
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
