"""Build a battery row's premise, shared by ``build_dev.py`` and ``scripts/run_battery.py``.

A row names its premise in one of three ways:

* ``premise`` (list of coordinates) and no ``premise_spec``: those provisions from the copied
  corpus, assembled by ``Premise.from_records`` (concept-query gold, or provisions named by hand);
* ``premise_spec = "anchor:<id>@<as_at>"``: one point-in-time version of an anchor provision (CLML
  under ``anchors_xml/``), plus a fact window giving its validity range;
* ``premise_spec = "anchor:<id>@timeline"``: the provision as it stands (corpus), plus fact windows
  giving when the current text started and what each dated version read — the shape a temporal
  resolver hands to generation (plan decision 4).
"""

from __future__ import annotations

import sys
import tomllib
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from clml import records as clml_records  # noqa: E402

from legal_rag_verifier import enrichment as enrichment_layer  # noqa: E402
from legal_rag_verifier.citations import coordinate_tail, render_citation  # noqa: E402
from legal_rag_verifier.corpus import load_provision  # noqa: E402
from legal_rag_verifier.premise import Passage, PassageKind, Premise  # noqa: E402

ANCHORS_FILE = Path(__file__).with_name("anchors.toml")


def _day(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} {d:%B %Y}"


@lru_cache(maxsize=1)
def anchors() -> dict[str, dict[str, Any]]:
    with ANCHORS_FILE.open("rb") as handle:
        return tomllib.load(handle)


def _version(anchor: dict[str, Any], as_at: str) -> dict[str, Any]:
    for version in anchor["versions"]:
        if version["as_at"] == as_at:
            return dict(version)
    raise KeyError(f"no version as at {as_at}")


def _version_records(version: dict[str, Any]) -> list[dict[str, Any]]:
    return clml_records(ROOT / version["file"])


def _figure_text(anchor: dict[str, Any], version: dict[str, Any]) -> tuple[str, str]:
    """(citation, text) of the window in this version that states the anchor figure."""
    premise = Premise.from_records(_version_records(version))
    for passage in premise.passages:
        if version["figure"] in passage.text:
            return render_citation(passage.tail), passage.text
    raise ValueError(f"{anchor['coordinate']}: {version['figure']} not found in {version['file']}")


@lru_cache(maxsize=64)
def _build(key: str, data_root: str) -> tuple[Premise, dict[str, dict[str, Any]]]:
    kind, _, value = key.partition(":")
    if kind == "corpus":
        rows: list[dict[str, Any]] = []
        for coordinate in value.split("|"):
            rows += load_provision(Path(data_root), coordinate)
        return Premise.from_records(rows), {r["coordinate"]: r for r in rows}

    anchor_id, _, point = value.partition("@")
    anchor = anchors()[anchor_id]
    title = anchor["title"]
    section = render_citation(coordinate_tail(anchor["coordinate"]))
    if point != "timeline":
        version = _version(anchor, point)
        rows = _version_records(version)
        fact = (
            f"{title}, {section} as in force on {_day(version['as_at'])}: this text applied from "
            f"{_day(version['from'])} until it was replaced on {_day(version['to'])}."
        )
        premise = Premise.from_records(
            rows,
            facts=[fact],
            valid_from=date.fromisoformat(version["from"]),
            valid_to=date.fromisoformat(version["to"]),
        )
        return premise, {r["coordinate"]: r for r in rows}

    rows = load_provision(Path(data_root), anchor["coordinate"])
    since = _day(anchor["current_from"])
    facts: list[str | Passage] = [
        f"{title}, {section} has had its current text since {since}, as amended by the "
        + anchor["current_amended_by"]
        + "."
    ]
    for version in sorted(anchor["versions"], key=lambda v: v["from"]):
        cite, text = _figure_text(anchor, version)
        span = f"From {_day(version['from'])} until it was replaced on {_day(version['to'])}"
        facts.append(
            Passage(
                f"{span}, {title}, {cite} read: {text}",
                None,
                PassageKind.FACT,
                valid_from=date.fromisoformat(version["from"]),
                valid_to=date.fromisoformat(version["to"]),
            )
        )
    premise = Premise.from_records(
        rows,
        facts=facts,
        extra_titles=[anchor["current_amended_by"]],
        valid_from=date.fromisoformat(anchor["current_from"]),
    )
    return premise, {r["coordinate"]: r for r in rows}


def premise_key(row: dict[str, Any]) -> str:
    spec = row.get("premise_spec")
    return spec if spec else "corpus:" + "|".join(row["premise"])


def build(
    row: dict[str, Any], data_root: Path, enrichment: Path | None = None
) -> tuple[Premise, dict[str, dict[str, Any]]]:
    """The premise for a row, and its records by coordinate (for ``source_url``).

    With ``enrichment`` (a directory written by ``scripts/enrich_premises.py``), the audited
    elements and thresholds of every unit whose source text matches are attached.
    """
    premise, records = _build(premise_key(row), str(data_root))
    if enrichment is None:
        return premise, records
    return enrichment_layer.attach(premise, _layer(enrichment)), records


@lru_cache(maxsize=4)
def _layer(directory: Path) -> enrichment_layer.Layer:
    return enrichment_layer.load(directory)
