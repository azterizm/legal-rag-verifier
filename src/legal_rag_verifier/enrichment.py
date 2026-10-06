"""Precomputed, quote-audited statements about a provision (accuracy plan step 2).

An offline model reads a provision once and writes its **elements** (each rule, condition,
exception or definition as one standalone plain-English sentence) and **thresholds** (each figure
with what it is for). Only the quotes are checkable, so every element and threshold must carry a
phrase copied verbatim from the provision; a threshold's value must also appear inside its quote.
Anything that fails is dropped and counted (approach from ephemeral-dynamic-llms
``cloud/reason.py``; no dependency on it).

The verifier uses the layer only to *support*: an element is attached to the window that contains
its quote and becomes an extra NLI candidate for that window. It cannot override a failed claim
check. Thresholds are audited and stored but not used (binding figures by the model-written
"what" lowered precision on dev, stop 11).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from legal_rag_verifier.claims import FIGURE_KINDS, extract_claims
from legal_rag_verifier.premise import Passage, PassageKind, Premise

__all__ = ["Audit", "Layer", "Threshold", "attach", "audit_entry", "from_dict", "load", "normalise"]

_MIN_QUOTE = 8


def normalise(text: str) -> str:
    """Quote comparison form: typographic quotes folded, whitespace collapsed, lower case."""
    text = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    return re.sub(r"\s+", " ", text).strip().strip(".,;:—- ").lower()


def _verbatim(quote: object, source: str) -> bool:
    q = normalise(quote) if isinstance(quote, str) else ""
    return len(q) >= _MIN_QUOTE and q in normalise(source)


def _figures(text: str) -> set[str]:
    return {f"{c.kind.value}:{c.value}" for c in extract_claims(text) if c.kind in FIGURE_KINDS}


@dataclass(frozen=True, slots=True)
class Threshold:
    """A figure in the provision and what it is for (``what`` is model-written)."""

    what: str
    value: str
    quote: str


@dataclass(frozen=True)
class Audit:
    elements: tuple[tuple[str, str], ...]  # (statement, quote)
    thresholds: tuple[Threshold, ...]
    elements_proposed: int
    thresholds_proposed: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "elements": [{"requirement": s, "quote": q} for s, q in self.elements],
            "thresholds": [
                {"what": t.what, "value": t.value, "quote": t.quote} for t in self.thresholds
            ],
            "audit": {
                "elements_proposed": self.elements_proposed,
                "elements_verified": len(self.elements),
                "thresholds_proposed": self.thresholds_proposed,
                "thresholds_verified": len(self.thresholds),
            },
        }


def audit_entry(raw: Mapping[str, Any], source: str) -> Audit:
    """Keep only elements whose quote is verbatim in ``source`` and thresholds whose value is a
    figure inside a verbatim quote."""
    elements_in = [e for e in raw.get("elements") or [] if isinstance(e, Mapping)]
    thresholds_in = [t for t in raw.get("thresholds") or [] if isinstance(t, Mapping)]
    elements = tuple(
        (str(e["requirement"]).strip(), str(e["quote"]))
        for e in elements_in
        if isinstance(e.get("requirement"), str)
        and e["requirement"].strip()
        and _verbatim(e.get("quote"), source)
    )
    thresholds = tuple(
        Threshold(str(t.get("what", "")).strip(), str(t["value"]), str(t["quote"]))
        for t in thresholds_in
        if _verbatim(t.get("quote"), source)
        and isinstance(t.get("value"), str)
        and _figures(t["value"])
        and _figures(t["value"]) <= _figures(str(t["quote"]))
    )
    return Audit(elements, thresholds, len(elements_in), len(thresholds_in))


@dataclass(frozen=True)
class Layer:
    """A loaded enrichment layer: its identity and its audited entries keyed by section."""

    layer_id: str
    entries: tuple[tuple[str, Audit], ...]  # (section coordinate, audit)

    def for_premise(self, premise: Premise) -> list[Audit]:
        sections = {e for e, _ in self.entries}
        wanted = {
            s
            for s in sections
            for p in premise.passages
            if p.coordinate and (p.coordinate == s or p.coordinate.startswith(s + "/"))
        }
        return [a for s, a in self.entries if s in wanted]


def load(directory: Path) -> Layer:
    """Read a layer written by ``scripts/enrich_premises.py`` (one JSON file per unit)."""
    files = sorted(directory.glob("*.json"))
    digest = hashlib.sha256()
    entries: list[tuple[str, Audit]] = []
    models: set[str] = set()
    for path in files:
        raw = path.read_bytes()
        digest.update(path.name.encode() + b"\0" + raw)
        entry = json.loads(raw)
        models.add(str(entry.get("model", "unknown")))
        entries.append((str(entry["section"]), from_dict(entry)))
    model = "+".join(sorted(models)) or "empty"
    return Layer(f"{model}@{digest.hexdigest()[:16]}", tuple(entries))


def attach(premise: Premise, layer: Layer) -> Premise:
    """Attach each verified element to every provision window that contains its quote."""
    items = layer.for_premise(premise)
    passages: list[Passage] = []
    for passage in premise.passages:
        if passage.kind is PassageKind.FACT:
            passages.append(passage)
            continue
        text = normalise(passage.text)
        elements = tuple(
            dict.fromkeys(s for a in items for s, q in a.elements if normalise(q) in text)
        )
        passages.append(replace(passage, elements=elements))
    return Premise(tuple(passages), premise.citations, premise.titles, layer.layer_id)


def from_dict(entry: Mapping[str, Any]) -> Audit:
    """An audited entry as written by ``scripts/enrich_premises.py``."""
    return Audit(
        tuple((e["requirement"], e["quote"]) for e in entry.get("elements", [])),
        tuple(Threshold(t["what"], t["value"], t["quote"]) for t in entry.get("thresholds", [])),
        entry.get("audit", {}).get("elements_proposed", 0),
        entry.get("audit", {}).get("thresholds_proposed", 0),
    )
