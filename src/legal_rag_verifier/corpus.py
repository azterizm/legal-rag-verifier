"""Read provision records from a local copy of the router's normalised corpus (``data/uk``)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

__all__ = ["instrument_path", "load_provision"]


def instrument_path(data_root: Path, coordinate: str) -> Path:
    """``uk/ukpga/1996/18/s124`` → ``<root>/uk/ukpga/1996/uk_ukpga_1996_18.jsonl``."""
    jurisdiction, kind, year, number = coordinate.split("/")[:4]
    return data_root / jurisdiction / kind / year / f"{jurisdiction}_{kind}_{year}_{number}.jsonl"


def load_provision(data_root: Path, coordinate: str) -> list[dict[str, Any]]:
    """The instrument record plus the provision at ``coordinate`` and all its descendants."""
    path = instrument_path(data_root, coordinate)
    prefix = coordinate + "/"
    out: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            row: dict[str, Any] = json.loads(line)
            c = row.get("coordinate", "")
            if row.get("record_type") == "instrument" or c == coordinate or c.startswith(prefix):
                out.append(row)
    if not any(r.get("coordinate") == coordinate for r in out):
        raise KeyError(f"{coordinate} not found in {path}")
    return out
