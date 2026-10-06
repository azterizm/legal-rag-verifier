"""Checkable claims in a sentence: figures, citations and instrument titles, each normalised.

Two surface forms of the same claim normalise to the same value, so grounding is a set lookup:
``£68,400`` = ``£68400`` = ``£68.4k`` → ``GBP:68400``; ``three months`` = ``3 months`` →
``3:month``; ``6th April 2026`` = ``06/04/2026`` → ``2026-04-06``; ``section 124(1ZA)`` =
``s.124(1ZA)`` → ``s124/1ZA``. Modal verbs are handled by :mod:`legal_rag_verifier.deontic`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from legal_rag_verifier.citations import find_citations
from legal_rag_verifier.numbers import (
    NUMBER_WORDS_RE,
    NUMERAL_RE,
    canonical_decimal,
    parse_magnitude,
    parse_number_words,
    parse_numeral,
)

__all__ = [
    "FIGURE_KINDS",
    "Claim",
    "ClaimKind",
    "extract_claims",
    "instrument_acronym",
    "normalise_title",
]


class ClaimKind(StrEnum):
    MONEY = "MONEY"
    PERCENT = "PERCENT"
    DATE = "DATE"
    DURATION = "DURATION"
    NUMBER = "NUMBER"
    CITATION = "CITATION"
    INSTRUMENT = "INSTRUMENT"


#: Claim kinds that carry a quantity (checked for qualifiers and window alignment).
FIGURE_KINDS = frozenset(
    {ClaimKind.MONEY, ClaimKind.PERCENT, ClaimKind.DATE, ClaimKind.DURATION, ClaimKind.NUMBER}
)


@dataclass(frozen=True, slots=True)
class Claim:
    """A checkable claim: its kind, canonical value and the span of text it was read from."""

    kind: ClaimKind
    value: str
    text: str
    start: int
    end: int


_CURRENCY_SYMBOLS = {"£": "GBP", "€": "EUR", "$": "USD"}
_CURRENCY_WORDS = {
    "pound": "GBP",
    "pounds": "GBP",
    "sterling": "GBP",
    "euro": "EUR",
    "euros": "EUR",
    "dollar": "USD",
    "dollars": "USD",
}
_MAG = r"(?:k|mn|m|bn|thousand|million|billion)"
_MONEY_SYMBOL_RE = re.compile(
    rf"(?P<sym>[£€$])\s?(?P<num>{NUMERAL_RE})(?:\s?(?P<mag>{_MAG})\b)?", re.IGNORECASE
)
_MONEY_WORD_RE = re.compile(
    rf"\b(?P<num>{NUMERAL_RE})(?:\s?(?P<mag>{_MAG}))?\s(?P<cur>pounds?(?:\s+sterling)?|euros?|dollars?)\b",
    re.IGNORECASE,
)
_PERCENT_RE = re.compile(
    rf"(?P<num>{NUMERAL_RE}|{NUMBER_WORDS_RE})\s?(?:%|per\s?cent\b|percent\b)", re.IGNORECASE
)
_MONTHS = {
    m: i + 1
    for i, names in enumerate(
        [
            ("january", "jan"),
            ("february", "feb"),
            ("march", "mar"),
            ("april", "apr"),
            ("may",),
            ("june", "jun"),
            ("july", "jul"),
            ("august", "aug"),
            ("september", "sep", "sept"),
            ("october", "oct"),
            ("november", "nov"),
            ("december", "dec"),
        ]
    )
    for m in names
}
_MONTH = r"(?P<month>" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\.?"
_ORD = r"(?:st|nd|rd|th)?"
_DATE_RES = [
    re.compile(rf"\b(?P<day>\d{{1,2}}){_ORD}\s+(?:of\s+)?{_MONTH},?\s+(?P<year>\d{{4}})\b", re.I),
    re.compile(rf"\b{_MONTH}\s+(?P<day>\d{{1,2}}){_ORD},?\s+(?P<year>\d{{4}})\b", re.I),
    re.compile(r"\b(?P<year>\d{4})-(?P<mon>\d{2})-(?P<day>\d{2})\b"),
    re.compile(r"\b(?P<day>\d{1,2})/(?P<mon>\d{1,2})/(?P<year>\d{4})\b"),
    re.compile(rf"\b{_MONTH}\s+(?P<year>\d{{4}})\b", re.I),
]
_UNIT = r"(?P<unit>day|week|month|year|hour)s?(?:['’])?"
_DURATION_RE = re.compile(
    rf"\b(?P<num>{NUMERAL_RE}|{NUMBER_WORDS_RE})(?:\s|-)(?:(?:calendar|working|clear|complete)\s)?{_UNIT}(?!\w)",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(rf"(?<![\w(/.])(?P<num>{NUMERAL_RE})(?![\w)/]|\.\d)")
# A number that labels an entry ("item 7" in a schedule table) names it; it states no quantity.
_LABEL_BEFORE = re.compile(
    r"\b(?:item|entry|row|column|line|box|step|annex|appendix|table|form)\s+$", re.IGNORECASE
)

_TITLE_WORD = r"(?:[A-Z][\w'’\-]*|\([A-Z][^()]*\))"
_TITLE_LINK = r"(?:of|and|the|for|in|on|to|&|etc\.?)"
# A comma inside a title only in a list of capitalised words closed by "and" ("Companies,
# Partnerships and Groups … Regulations 2015"); a comma after an opening word is prose.
_TITLE_COMMA = r",(?=\s+[A-Z][^,.;:]*?\sand\s)"
_INSTRUMENT_RE = re.compile(
    rf"(?P<title>{_TITLE_WORD}(?:(?:{_TITLE_COMMA})?\s+(?:{_TITLE_WORD}|{_TITLE_LINK}))*?\s+"
    rf"(?:Act|Order|Regulations|Rules|Measure|Code)(?:\s+\(Northern\s+Ireland\))?)\s+(?P<year>\d{{4}})\b"
)
_SI_RE = re.compile(r"\b(?:S\.?\s?I\.?|SI)\s?(?:No\.?\s?)?(?P<year>\d{4})\s?/\s?(?P<num>\d+)\b")
_ACRONYM_RE = re.compile(r"\b(?P<acr>[A-Z]{2,7}A)\s?(?P<year>\d{4})\b")
_LEADING_NOISE = re.compile(
    r"^(?:(?:under|the|in|by|of|and|for|see|per|section|s|that|this|as|to|on|a|an|"
    r"its|their|with|within|from|both|also|regulation|article|schedule|part|chapter)\s+)+",
    re.IGNORECASE,
)
_MINOR_WORDS = {"of", "and", "the", "for", "in", "on", "to", "&", "etc", "etc."}


def normalise_title(title: str) -> str:
    """Lower-case an instrument title, drop leading prose and a leading "The", collapse spaces."""
    text = re.sub(r"\s+", " ", title.replace("’", "'")).strip()
    text = _LEADING_NOISE.sub("", text)
    return text.lower()


def instrument_acronym(title: str) -> str:
    """``Employment Rights Act 1996`` → ``ERA1996`` (major words' initials plus the year)."""
    words = re.sub(r"\([^)]*\)", " ", title).split()
    year = words[-1] if words and words[-1].isdigit() else ""
    initials = "".join(
        w[0].upper() for w in words if w.lower() not in _MINOR_WORDS and w[0].isalpha()
    )
    return initials + year


def _money_value(currency: str, number: str, magnitude: str | None) -> str | None:
    amount = parse_numeral(number)
    if amount is None:
        return None
    return f"{currency}:{canonical_decimal(amount * parse_magnitude(magnitude))}"


def _quantity(text: str) -> Decimal | None:
    numeral = parse_numeral(text)
    if numeral is not None:
        return numeral
    words = parse_number_words(text)
    return None if words is None else Decimal(words)


def _figures(text: str) -> list[Claim]:
    claims: list[Claim] = []

    def add(kind: ClaimKind, value: str | None, m: re.Match[str]) -> None:
        if value is not None:
            claims.append(Claim(kind, value, m.group(0), m.start(), m.end()))

    for m in _MONEY_SYMBOL_RE.finditer(text):
        add(ClaimKind.MONEY, _money_value(_CURRENCY_SYMBOLS[m["sym"]], m["num"], m["mag"]), m)
    for m in _MONEY_WORD_RE.finditer(text):
        currency = _CURRENCY_WORDS[m["cur"].split()[0].lower()]
        add(ClaimKind.MONEY, _money_value(currency, m["num"], m["mag"]), m)
    for m in _PERCENT_RE.finditer(text):
        q = _quantity(m["num"])
        add(ClaimKind.PERCENT, None if q is None else canonical_decimal(q), m)
    for pattern in _DATE_RES:
        for m in pattern.finditer(text):
            add(ClaimKind.DATE, _date_value(m), m)
    for m in _DURATION_RE.finditer(text):
        q = _quantity(m["num"])
        add(
            ClaimKind.DURATION,
            None if q is None else f"{canonical_decimal(q)}:{m['unit'].lower()}",
            m,
        )
    return claims


def _date_value(m: re.Match[str]) -> str | None:
    groups = m.groupdict()
    month_name = groups.get("month")
    month = _MONTHS[month_name.lower()] if month_name else int(groups["mon"])
    year = int(groups["year"])
    if not 1 <= month <= 12 or not 1000 <= year <= 2999:  # noqa: PLR2004
        return None
    day_text = groups.get("day")
    if day_text is None:
        return f"{year:04d}-{month:02d}"
    day = int(day_text)
    if not 1 <= day <= 31:  # noqa: PLR2004
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _instruments(text: str) -> list[Claim]:
    claims: list[Claim] = []
    for m in _INSTRUMENT_RE.finditer(text):
        title = normalise_title(f"{m['title']} {m['year']}")
        offset = m.group(0).lower().find(title.split()[0]) if title else 0
        start = m.start() + max(offset, 0)
        claims.append(Claim(ClaimKind.INSTRUMENT, title, text[start : m.end()], start, m.end()))
    claims += [
        Claim(ClaimKind.INSTRUMENT, f"si:{m['year']}/{int(m['num'])}", m[0], m.start(), m.end())
        for m in _SI_RE.finditer(text)
    ]
    claims += [
        Claim(ClaimKind.INSTRUMENT, f"acr:{m['acr']}{m['year']}", m[0], m.start(), m.end())
        for m in _ACRONYM_RE.finditer(text)
    ]
    return claims


def _overlaps(claim: Claim, taken: list[tuple[int, int]]) -> bool:
    return any(claim.start < end and start < claim.end for start, end in taken)


def extract_claims(text: str) -> list[Claim]:
    """All claims in ``text``, longest-first without overlaps, in reading order.

    Priority on overlap: instruments, citations, money, dates, percentages, durations, then any
    bare number left over (``52`` in "52 multiplied by a week's pay"). Numbers inside a citation
    ("section 124"), an instrument title ("Act 1996") or a date are never counted twice.
    """
    candidates: list[Claim] = _instruments(text)
    candidates += [
        Claim(ClaimKind.CITATION, c.canonical, c.text, c.start, c.end) for c in find_citations(text)
    ]
    figures = _figures(text)
    order = [ClaimKind.MONEY, ClaimKind.DATE, ClaimKind.PERCENT, ClaimKind.DURATION]
    candidates += sorted(figures, key=lambda c: (order.index(c.kind), -(c.end - c.start)))

    chosen: list[Claim] = []
    taken: list[tuple[int, int]] = []
    for claim in candidates:
        if not _overlaps(claim, taken) or (
            claim.kind is ClaimKind.CITATION and _same_span(claim, chosen)
        ):
            chosen.append(claim)
            taken.append((claim.start, claim.end))
    for m in _NUMBER_RE.finditer(text):
        number = parse_numeral(m["num"])
        claim = Claim(
            ClaimKind.NUMBER,
            canonical_decimal(number) if number is not None else m["num"],
            m.group(0),
            m.start(),
            m.end(),
        )
        if not _overlaps(claim, taken) and not _LABEL_BEFORE.search(text, 0, m.start()):
            chosen.append(claim)
    return sorted(chosen, key=lambda c: (c.start, c.kind.value, c.value))


def _same_span(claim: Claim, chosen: list[Claim]) -> bool:
    """One citation span can yield several citations ("section 117(1) and (2)")."""
    return any(
        c.kind is ClaimKind.CITATION and c.start == claim.start and c.end == claim.end
        for c in chosen
    )
