"""Read provision records from a local copy of the router's normalised corpus (``data/uk``)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

__all__ = ["instrument_coordinate", "instrument_path", "load_provision"]

from legal_rag_verifier.citations import instrument_depth

_CALENDAR_PARTS = 4  # uk/ukpga/1996/18; a regnal-year Act has 5 (uk/ukpga/Vict/24-25/100)


def instrument_coordinate(coordinate: str) -> str:
    """The instrument part of a coordinate (regnal-year Acts have five parts: Vict/24-25/100)."""
    return "/".join(coordinate.split("/")[: instrument_depth(coordinate)])


def instrument_path(data_root: Path, coordinate: str) -> Path:
    """``uk/ukpga/1996/18/s124`` → ``<root>/uk/ukpga/1996/uk_ukpga_1996_18.jsonl``.

    A regnal-year Act is filed under its calendar year, which the coordinate does not carry
    (``uk/ukpga/Vict/24-25/100`` → ``<root>/uk/ukpga/1861/uk_ukpga_Vict_24-25_100.jsonl``), so it is
    found by name.
    """
    parts = instrument_coordinate(coordinate).split("/")
    name = "_".join(parts) + ".jsonl"
    if len(parts) == _CALENDAR_PARTS:
        return data_root / parts[0] / parts[1] / parts[2] / name
    matches = sorted((data_root / parts[0] / parts[1]).glob(f"*/{name}"))
    if not matches:
        raise FileNotFoundError(f"{coordinate}: no {name} under {data_root / parts[0] / parts[1]}")
    return matches[0]


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
