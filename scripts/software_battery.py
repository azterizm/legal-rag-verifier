"""Stop 37: the software battery's rows and premises (``batteries/software/test.jsonl``).

Each row's passages become the premise windows, each under its heading; no enrichment layer, no
declared citations or instrument titles.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from legal_rag_verifier.premise import Passage, Premise  # noqa: E402

BATTERY = ROOT / "batteries/software/test.jsonl"


def rows() -> list[dict[str, Any]]:
    """Battery rows in file order."""
    return [json.loads(line) for line in BATTERY.read_text(encoding="utf-8").splitlines()]


def premise(row: dict[str, Any]) -> Premise:
    return Premise(tuple(Passage(p["text"], heading=p["heading"]) for p in row["passages"]))
