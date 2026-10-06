"""Everything the claim check needs from a premise, extracted once per premise."""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass, field
from datetime import date

from legal_rag_verifier.citations import is_relative, resolve_relative
from legal_rag_verifier.claims import (
    Claim,
    ClaimKind,
    extract_claims,
    instrument_acronym,
    normalise_title,
)
from legal_rag_verifier.deontic import Deontic, licensed_classes
from legal_rag_verifier.numbers import NUMBER_WORDS_RE, parse_number_words
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
    heading: str = ""
    limbs: tuple[str, ...] = ()
    valid_from: date | None = None
    valid_to: date | None = None
    elements: tuple[str, ...] = ()

    @property
    def nli_text(self) -> str:
        """The window as the NLI head sees it: heading (instrument, citation, title) then text."""
        return f"{self.heading}: {self.text}" if self.heading else self.text

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
    #: Numbers the premise text writes in words or as ordinals ("forty-one", "31st").
    text_numbers: frozenset[str] = frozenset()
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
    text_numbers: set[str] = set()
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
        text_numbers |= _spelled_numbers(passage.text)
        windows.append(
            WindowIndex(
                i,
                passage.text,
                passage.kind,
                passage.tail,
                tuple(claims),
                frozenset(resolved),
                licensed_classes(passage.text),
                passage.heading or "",
                passage.limbs,
                passage.valid_from,
                passage.valid_to,
                passage.elements,
            )
        )

    titles, sis, acronyms, title_numbers = _title_sets(
        premise.titles, values.pop(ClaimKind.INSTRUMENT, set())
    )
    return PremiseIndex(
        windows=tuple(windows),
        values={k: frozenset(v) for k, v in values.items()},
        numbers=frozenset(numbers | title_numbers),
        text_citations=frozenset(text_citations),
        declared_citations=frozenset(premise.citations),
        titles=frozenset(titles),
        text_numbers=frozenset(text_numbers),
        sis=frozenset(sis),
        acronyms=frozenset(acronyms),
        declared_titles=premise.titles,
    )


_ORDINAL = re.compile(r"\b(\d+)(?:st|nd|rd|th)\b")
_SPELLED = re.compile(NUMBER_WORDS_RE, re.IGNORECASE)


def _spelled_numbers(text: str) -> set[str]:
    """Numbers written as words or ordinals, which are not claims in the premise's own text but
    ground the same number written as digits in a sentence ("aged 41" against "forty-one")."""
    out = {m.group(1).lstrip("0") or "0" for m in _ORDINAL.finditer(text)}
    for m in _SPELLED.finditer(text):
        value = parse_number_words(m.group(0))
        if value is not None:
            out.add(str(value))
    return out


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
