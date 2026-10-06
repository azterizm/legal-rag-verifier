"""Deontic class of a text: OBLIGATION, PROHIBITION or PERMISSION (English only, plan R8).

Negated forms are matched first so that "shall not" is a prohibition, not an obligation, and
"need not" / "is not required to" is a permission (no duty), not an obligation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

__all__ = ["MODAL_SURFACES", "Deontic", "DeonticMatch", "find_deontics", "licensed_classes"]


class Deontic(StrEnum):
    OBLIGATION = "OBLIGATION"
    PROHIBITION = "PROHIBITION"
    PERMISSION = "PERMISSION"


@dataclass(frozen=True, slots=True)
class DeonticMatch:
    deontic: Deontic
    text: str
    start: int
    end: int


#: Canonical surface forms per class, used as allow-list candidates after a modal shift.
MODAL_SURFACES: dict[Deontic, tuple[str, ...]] = {
    Deontic.OBLIGATION: ("must", "shall"),
    Deontic.PROHIBITION: ("must not", "shall not"),
    Deontic.PERMISSION: ("may",),
}

_BE = r"(?:is|are|was|were|be|will\s+be)"
_PATTERNS: list[tuple[Deontic, str]] = [
    (Deontic.PERMISSION, r"\b(?:need\s+not|needn['’]t)\b"),
    (Deontic.PERMISSION, rf"\b{_BE}\s+not\s+(?:required|obliged|bound)\s+to\b"),
    (Deontic.PERMISSION, r"\b(?:does|do|did)\s+not\s+(?:have|need)\s+to\b"),
    (Deontic.PROHIBITION, r"\b(?:shall|must|may|should)\s+not\b|\b(?:mustn['’]t|shan['’]t)\b"),
    # "I cannot find", "we can't say": the speaker's ability, not a duty
    (Deontic.PROHIBITION, r"(?<!\bI\s)(?<!\bwe\s)(?<!\bWe\s)\b(?:cannot|can\s+not|can['’]t)\b"),
    (
        Deontic.PROHIBITION,
        rf"\b{_BE}\s+(?:not\s+(?:permitted|allowed|entitled)|prohibited|forbidden|barred)\b",
    ),
    (Deontic.PROHIBITION, r"\bno\s+(?:\w+\s+){1,3}(?:shall|may|must)\b"),
    (Deontic.OBLIGATION, r"\b(?:shall|must)\b"),
    (Deontic.OBLIGATION, rf"\b{_BE}\s+(?:required|obliged|bound)\s+to\b"),
    (Deontic.OBLIGATION, r"\b(?:has|have|is\s+under|are\s+under)\s+(?:a\s+)?(?:duty|obligation)\b"),
    (Deontic.OBLIGATION, r"\b(?:has|have)\s+to\b"),
    (Deontic.PERMISSION, r"\bmay(?!\s+(?:be\s+able|wish|want|need|well|also\s+wish)\b)(?!\s+\d)\b"),
    (Deontic.PERMISSION, rf"\b{_BE}\s+(?:entitled|permitted|allowed)\s+to\b"),
    (Deontic.PERMISSION, r"\b(?:has|have)\s+(?:a|the)\s+right\b"),
]
_COMPILED = [(d, re.compile(p, re.IGNORECASE)) for d, p in _PATTERNS]
_MONTH_MAY = re.compile(r"\b\d{1,2}(?:st|nd|rd|th)?\s+May\b|\bMay\s+\d")


_PARENTHETICAL = re.compile(r"\([^()]{3,}\)")
_CONDITIONAL_BAR = re.compile(r"\b(?:unless|until)\b", re.IGNORECASE)


def licensed_classes(text: str) -> frozenset[Deontic]:
    """Classes a window licenses: its own, plus OBLIGATION where it bars something *unless* or
    *until* a step is taken ("No will shall be valid unless it is in writing" = it must be)."""
    found = {d.deontic for d in find_deontics(text)}
    if Deontic.PROHIBITION in found and _CONDITIONAL_BAR.search(text):
        found.add(Deontic.OBLIGATION)
    return frozenset(found)


def find_deontics(text: str) -> list[DeonticMatch]:
    """Every deontic expression in ``text``, earliest first, without overlaps.

    Parenthetical asides are blanked first (offsets kept), so "is not (subject to express
    provision to the contrary) entitled to" reads as "is not entitled to".
    """
    text = _PARENTHETICAL.sub(lambda m: " " * len(m.group(0)), text)
    blocked = [(m.start(), m.end()) for m in _MONTH_MAY.finditer(text)]
    found: list[DeonticMatch] = []
    for deontic, pattern in _COMPILED:
        for m in pattern.finditer(text):
            if any(m.start() < e and s < m.end() for s, e in blocked):
                continue
            found.append(DeonticMatch(deontic, m.group(0), m.start(), m.end()))
            blocked.append((m.start(), m.end()))
    return sorted(found, key=lambda d: d.start)
