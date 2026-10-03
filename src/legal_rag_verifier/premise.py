"""The premise a sentence is verified against: plain data, no router or temporal import.

A premise is a tuple of *windows* (passages): each window is one provision subsection assembled
from the provision tree (stem + children + tail, plan R10), so a qualifier and the figure it binds
stay together. Temporal metadata is linearised into declarative *fact* windows (pasted note §1),
so "Since 6 April 2026 the cap is £123,543" can be grounded. Declared citations and instrument
titles are metadata: a provision's own citation rarely appears in its text.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any

from legal_rag_verifier.citations import coordinate_tail, render_citation

__all__ = ["Passage", "PassageKind", "Premise"]

_REPEALED_TEXT = re.compile(r"^[\s.…]*$")
_DOT_RUN = re.compile(r"(?:\.\s){3,}\.?")


class PassageKind(StrEnum):
    PROVISION = "provision"
    FACT = "fact"
    TEXT = "text"


@dataclass(frozen=True, slots=True)
class Passage:
    """One premise window. ``coordinate`` is the router coordinate it was built from, if any."""

    text: str
    coordinate: str | None = None
    kind: PassageKind = PassageKind.TEXT
    heading: str | None = None

    @property
    def tail(self) -> str:
        return coordinate_tail(self.coordinate) if self.coordinate else ""


@dataclass(frozen=True)
class Premise:
    """Windows to verify against, declared citations (coordinate tails) and instrument titles."""

    passages: tuple[Passage, ...]
    citations: frozenset[str] = field(default_factory=frozenset)
    titles: tuple[str, ...] = ()

    @property
    def windows(self) -> tuple[Passage, ...]:
        return self.passages

    @property
    def facts(self) -> tuple[Passage, ...]:
        return tuple(p for p in self.passages if p.kind is PassageKind.FACT)

    # ------------------------------------------------------------------ constructors
    @classmethod
    def from_text(
        cls, text: str, *, titles: Iterable[str] = (), citations: Iterable[str] = ()
    ) -> Premise:
        """A premise of free text, one window per paragraph (blank-line separated)."""
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        return cls(
            tuple(Passage(p) for p in paragraphs),
            frozenset(_tail_or_cite(c) for c in citations),
            tuple(titles),
        )

    @classmethod
    def from_provision(
        cls,
        text: str,
        coordinate: str,
        title: str,
        *,
        in_force_from: date | None = None,
        amended_by: str | None = None,
        previous_text: str | None = None,
    ) -> Premise:
        """One provision's text plus its temporal metadata, linearised as fact windows."""
        tail = coordinate_tail(coordinate)
        heading = _heading(title, tail)
        passages = [Passage(_clean(text), coordinate, PassageKind.PROVISION, heading)]
        passages += _facts(heading, in_force_from, amended_by, previous_text)
        titles = [title]
        if amended_by:
            titles.append(amended_by)
        return cls(tuple(passages), _declared(tail), tuple(titles))

    @classmethod
    def from_records(
        cls,
        records: Iterable[Mapping[str, Any]],
        *,
        title: str | None = None,
        facts: Iterable[str] = (),
        extra_titles: Iterable[str] = (),
    ) -> Premise:
        """Assemble windows from normalised provision records (the router's ``data/uk`` rows).

        Each subsection becomes one window: its stem text, every descendant in document order and
        its ``text_after`` tail. A provision without subsections is one window. Repealed text
        (dot runs) is dropped. Every non-repealed node's coordinate is declared as a citation.
        """
        rows = [dict(r) for r in records]
        instrument_title = title
        provisions: list[dict[str, Any]] = []
        for row in rows:
            if row.get("record_type") == "instrument":
                instrument_title = instrument_title or row.get("title")
            else:
                provisions.append(row)
        provisions.sort(key=lambda r: (r.get("order", 0), r["coordinate"]))
        by_coordinate = {r["coordinate"]: r for r in provisions}
        children: dict[str, list[dict[str, Any]]] = {}
        roots: list[dict[str, Any]] = []
        for row in provisions:
            parent = str(row.get("parent", ""))
            if parent in by_coordinate:
                children.setdefault(parent, []).append(row)
            else:
                roots.append(row)

        passages: list[Passage] = []
        declared: set[str] = set()
        for row in provisions:
            if not row.get("repealed") and not _is_repealed_text(row.get("text", "")):
                declared |= _declared(coordinate_tail(row["coordinate"]))
        for root in roots:
            for node, labelled in _window_roots(root, children):
                body = _assemble(node, children, label=labelled)
                if body:
                    tail = coordinate_tail(node["coordinate"])
                    heading = _heading(instrument_title or "", tail, node_title=root.get("title"))
                    passages.append(
                        Passage(body, node["coordinate"], PassageKind.PROVISION, heading)
                    )
        passages += [Passage(f, None, PassageKind.FACT) for f in facts]
        titles = [t for t in [instrument_title, *extra_titles] if t]
        return cls(tuple(passages), frozenset(declared), tuple(titles))

    def with_facts(self, facts: Iterable[str]) -> Premise:
        extra = tuple(Passage(f, None, PassageKind.FACT) for f in facts)
        return Premise(self.passages + extra, self.citations, self.titles)


# ---------------------------------------------------------------------- helpers
def _tail_or_cite(value: str) -> str:
    return coordinate_tail(value) if value.startswith(("uk/", "es/")) else value


def _declared(tail: str) -> frozenset[str]:
    return frozenset({tail}) if tail else frozenset()


def _heading(title: str, tail: str, *, node_title: str | None = None) -> str:
    cite = render_citation(tail) if tail else ""
    parts = [p for p in (title, cite) if p]
    heading = ", ".join(parts)
    if node_title:
        heading += f" ({node_title.rstrip('.')})"
    return heading


def _clean(text: str) -> str:
    text = _DOT_RUN.sub(" ", text.replace("—", "— ").replace(" ", " "))
    return re.sub(r"\s+", " ", text).strip()


def _is_repealed_text(text: str) -> bool:
    return bool(text) and _REPEALED_TEXT.match(text) is not None


def _window_roots(
    root: dict[str, Any], children: Mapping[str, list[dict[str, Any]]]
) -> list[tuple[dict[str, Any], bool]]:
    """Subsections of a section are separate windows; otherwise the root is one window."""
    kids = children.get(root["coordinate"], [])
    if kids and all(str(k.get("number_label", ""))[:1].isdigit() for k in kids):
        out: list[tuple[dict[str, Any], bool]] = []
        if root.get("text") and not _is_repealed_text(root["text"]):
            out.append(({**root, "text_after": ""}, False))
        out += [(k, True) for k in kids]
        return out
    return [(root, False)]


def _assemble(
    node: dict[str, Any], children: Mapping[str, list[dict[str, Any]]], *, label: bool
) -> str:
    if node.get("repealed"):
        return ""
    parts: list[str] = []
    if label and node.get("number_label"):
        parts.append(f"({node['number_label']})")
    text = node.get("text") or ""
    if text and not _is_repealed_text(text):
        parts.append(text)
    for child in children.get(node["coordinate"], []):
        sub = _assemble(child, children, label=True)
        if sub:
            parts.append(sub)
    after = node.get("text_after") or ""
    if after and not _is_repealed_text(after):
        parts.append(after)
    body = _clean(" ".join(parts))
    return "" if _REPEALED_TEXT.match(re.sub(r"\(\w+\)", "", body)) else body


def _facts(
    heading: str,
    in_force_from: date | None,
    amended_by: str | None,
    previous_text: str | None,
) -> list[Passage]:
    out: list[str] = []
    when = f"{in_force_from.day} {in_force_from:%B %Y}" if in_force_from else None
    if when and amended_by:
        out.append(
            f"{heading} has had its current text since {when}, as amended by the {amended_by}."
        )
    elif when:
        out.append(f"{heading} has had its current text since {when}.")
    elif amended_by:
        out.append(f"{heading} was amended by the {amended_by}.")
    if previous_text and when:
        out.append(f"Before {when}, {heading} read: {_clean(previous_text)}")
    return [Passage(f, None, PassageKind.FACT, heading) for f in out]
