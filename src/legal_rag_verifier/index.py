"""Everything the claim check needs from a premise, extracted once per premise."""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass, field

from legal_rag_verifier.citations import is_relative, resolve_relative
from legal_rag_verifier.claims import (
    Claim,
    ClaimKind,
    extract_claims,
    instrument_acronym,
    normalise_title,
)
from legal_rag_verifier.deontic import Deontic, find_deontics
from legal_rag_verifier.premise import PassageKind, Premise

__all__ = ["PremiseIndex", "WindowIndex", "build_index", "numeric_part"]

_SI_IN_TITLE = re.compile(r"\bS\.?\s?I\.?\s?(\d{4})\s?/\s?(\d+)")


def numeric_part(claim: Claim) -> str | None:
    """The bare quantity of a figure claim: ``GBP:68400`` → ``68400``, ``3:month`` → ``3``."""
    if claim.kind is ClaimKind.MONEY:
        return claim.value.split(":", 1)[1]
    if claim.kind is ClaimKind.DURATION:
        return claim.value.split(":", 1)[0]
    if claim.kind in {ClaimKind.PERCENT, ClaimKind.NUMBER}:
        return claim.value
    if claim.kind is ClaimKind.DATE:
        return str(int(claim.value[:4]))
    return None


@dataclass(frozen=True)
class WindowIndex:
    """One window's text, kind, claims, resolved citations and deontic classes."""

    position: int
    text: str
    kind: PassageKind
    tail: str
    claims: tuple[Claim, ...]
    citations: frozenset[str]
    deontics: frozenset[Deontic]

    def values(self, kind: ClaimKind) -> list[Claim]:
        return [c for c in self.claims if c.kind is kind]


@dataclass(frozen=True)
class PremiseIndex:
    """Grounding sets over the whole premise plus a per-window index."""

    windows: tuple[WindowIndex, ...]
    values: dict[ClaimKind, frozenset[str]] = field(default_factory=dict)
    numbers: frozenset[str] = frozenset()
    text_citations: frozenset[str] = frozenset()
    declared_citations: frozenset[str] = frozenset()
    titles: frozenset[str] = frozenset()
    sis: frozenset[str] = frozenset()
    acronyms: frozenset[str] = frozenset()
    declared_titles: tuple[str, ...] = ()

    @property
    def citations(self) -> frozenset[str]:
        return self.text_citations | self.declared_citations


@functools.lru_cache(maxsize=256)
def build_index(premise: Premise) -> PremiseIndex:
    windows: list[WindowIndex] = []
    values: dict[ClaimKind, set[str]] = {k: set() for k in ClaimKind}
    numbers: set[str] = set()
    text_citations: set[str] = set()
    for i, passage in enumerate(premise.passages):
        claims = extract_claims(passage.text)
        heading_claims = extract_claims(passage.heading) if passage.heading else []
        resolved: set[str] = set()
        for claim in [*claims, *heading_claims]:
            if claim.kind is ClaimKind.CITATION:
                value = claim.value
                if is_relative(value) and passage.tail:
                    value = resolve_relative(value, passage.tail)
                resolved.add(value)
            else:
                values[claim.kind].add(claim.value)
            number = numeric_part(claim)
            if number is not None:
                numbers.add(number)
        text_citations |= resolved
        windows.append(
            WindowIndex(
                i,
                passage.text,
                passage.kind,
                passage.tail,
                tuple(claims),
                frozenset(resolved),
                frozenset(d.deontic for d in find_deontics(passage.text)),
            )
        )

    titles, sis, acronyms, title_numbers = _title_sets(
        premise.titles, values.pop(ClaimKind.INSTRUMENT, set())
    )
    return PremiseIndex(
        tuple(windows),
        {k: frozenset(v) for k, v in values.items()},
        frozenset(numbers | title_numbers),
        frozenset(text_citations),
        frozenset(premise.citations),
        frozenset(titles),
        frozenset(sis),
        frozenset(acronyms),
        premise.titles,
    )


def _title_sets(
    declared: tuple[str, ...], mentioned: set[str]
) -> tuple[set[str], set[str], set[str], set[str]]:
    """Normalised titles, S.I. numbers, acronyms and years from declared and mentioned titles."""
    titles = {normalise_title(t) for t in declared}
    sis: set[str] = set()
    acronyms: set[str] = set()
    numbers: set[str] = set()
    for title in declared:
        sis |= {f"si:{year}/{int(num)}" for year, num in _SI_IN_TITLE.findall(title)}
        numbers |= set(re.findall(r"\b\d{4}\b", title))
        acronyms.add(instrument_acronym(title))
    for value in mentioned:
        if value.startswith("si:"):
            sis.add(value)
        elif value.startswith("acr:"):
            acronyms.add(value[4:])
        else:
            titles.add(value)
    acronyms |= {instrument_acronym(t.title()) for t in titles}
    return titles, sis, acronyms, numbers
