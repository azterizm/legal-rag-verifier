"""The 2x2 grid's prompt set (vault 07 §5; your choice 2026-10-06): the router concept battery's
``test`` split, UK only (103 queries; the ``us_law`` area is skipped, as in plan R11).

Each prompt is a query plus its premise: the gold provisions from the copied corpus (``data/``),
with the enrichment layer attached, exactly as the verifier batteries build them. A query whose
expected route is an abstention keeps that label; one with no gold provision gets an empty
premise. Writes ``batteries/grid/test.jsonl`` (ids, queries, coordinates: no statute text).

  uv run python scripts/grid_prompts.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "batteries/verifier"))

import premises  # noqa: E402

from legal_rag_verifier.premise import Premise  # noqa: E402

SOURCE = ROOT / "batteries/router/concept/uk.jsonl"
OUT = ROOT / "batteries/grid/test.jsonl"
ENRICHMENT = ROOT / "enrichment/gemini-3.8-flash-high"
ABSTAIN = "EPISTEMIC_ABSTENTION"


def rows() -> list[dict[str, Any]]:
    """Grid rows in battery order."""
    return [json.loads(line) for line in OUT.read_text(encoding="utf-8").splitlines()]


def premise(row: dict[str, Any], *, enrichment: Path | None = ENRICHMENT) -> Premise:
    if not row["premise"]:
        return Premise.from_text("")
    built, _ = premises.build(row, ROOT / "data", enrichment)
    return built


def main() -> None:
    source = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines()]
    out = [
        {
            "id": r["id"],
            "query": r["query"],
            "area": r["area"],
            "route_status": r["route_status"],
            "expects_abstention": r["route_status"].startswith(ABSTAIN),
            "premise": r.get("gold", []),
            "split": "test",
        }
        for r in source
        if r["split"] == "test" and r["area"] != "us_law"
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out), encoding="utf-8")
    sizes = sorted(len(premise(r, enrichment=None).passages) for r in out)
    print(
        json.dumps(
            {
                "prompts": len(out),
                "expects_abstention": sum(r["expects_abstention"] for r in out),
                "empty_premise": sum(not r["premise"] for r in out),
                "windows_median": sizes[len(sizes) // 2],
                "windows_max": sizes[-1],
            }
        )
    )


if __name__ == "__main__":
    main()
