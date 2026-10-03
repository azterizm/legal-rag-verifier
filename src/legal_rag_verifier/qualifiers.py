"""Qualifiers that bind a figure in the source ("the lower of— (a) £123,543"), plan R2.

A figure stated without the qualifier its source binds it with is a different legal claim: "the
cap is £123,543" drops "the lower of £123,543 and 52 weeks' pay". Binding is figure-scoped: the
qualifier must sit close before the figure (or just after it: "£X, whichever is lower"), in the
same clause. A sentence keeps the qualifier when it carries any marker of the same class.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

__all__ = ["Qualifier", "QualifierMatch", "find_bound_qualifier", "sentence_qualifiers"]


class Qualifier(StrEnum):
    COMPARATIVE = "COMPARATIVE"  # the lower / higher of, whichever is …
    UPPER_LIMIT = "UPPER_LIMIT"  # not exceeding, up to, maximum
    LOWER_LIMIT = "LOWER_LIMIT"  # not less than, at least, minimum
    CONDITION = "CONDITION"  # subject to, unless, except, save


@dataclass(frozen=True, slots=True)
class QualifierMatch:
    qualifier: Qualifier
    text: str
    start: int
    end: int


_SOURCE: list[tuple[Qualifier, str]] = [
    (Qualifier.COMPARATIVE, r"\bthe\s+(?:lower|lesser|higher|greater|smaller|larger)\s+of\b"),
    (Qualifier.COMPARATIVE, r"\bwhichever\s+is\b"),
    (
        Qualifier.UPPER_LIMIT,
        r"\b(?:not|does\s+not|shall\s+not|must\s+not)\s+(?:exceed|exceeding|more\s+than)\b",
    ),
    (Qualifier.UPPER_LIMIT, r"\b(?:up\s+to|at\s+most|no\s+more\s+than|a\s+maximum\s+of|maximum)\b"),
    (
        Qualifier.LOWER_LIMIT,
        r"\b(?:not|no)\s+less\s+than\b|\bat\s+least\b|\b(?:a\s+)?minimum(?:\s+of)?\b",
    ),
    (
        Qualifier.CONDITION,
        r"\bsubject\s+to\b|\bunless\b|\bexcept\b|\bsave\s+(?:as|where|that|in)\b",
    ),
]
_SENTENCE: dict[Qualifier, str] = {
    Qualifier.COMPARATIVE: (
        r"\b(?:lower|lowest|lesser|less|smaller|higher|highest|greater|larger|whichever)\b"
    ),
    Qualifier.UPPER_LIMIT: (
        r"\b(?:cap|caps|capped|limit|limits|limited|maximum|max|ceiling|up\s+to|exceed|exceeding|"
        r"no\s+more\s+than|not\s+more\s+than|at\s+most)\b"
    ),
    Qualifier.LOWER_LIMIT: (
        r"\b(?:minimum|min|floor|at\s+least|no\s+less\s+than|not\s+less\s+than)\b"
    ),
    Qualifier.CONDITION: (
        r"\b(?:subject\s+to|unless|except|save|provided|if|where|when|condition|conditions)\b"
    ),
}
_SOURCE_RE = [(q, re.compile(p, re.IGNORECASE)) for q, p in _SOURCE]
_SENTENCE_RE = {q: re.compile(p, re.IGNORECASE) for q, p in _SENTENCE.items()}
_CLAUSE_BREAK = re.compile(r"[.;]\s|\n")
_MAX_WORDS_BEFORE = 12
_MAX_WORDS_AFTER = 6


def _words(text: str) -> int:
    return len(re.findall(r"[\w£€$%]+", text))


def find_bound_qualifier(window: str, start: int, end: int) -> QualifierMatch | None:
    """The qualifier in ``window`` that binds the figure at ``window[start:end]``, if any."""
    best: QualifierMatch | None = None
    for qualifier, pattern in _SOURCE_RE:
        for m in pattern.finditer(window):
            if m.end() <= start:
                between = window[m.end() : start]
                limit = _MAX_WORDS_BEFORE
            elif m.start() >= end:
                between = window[end : m.start()]
                limit = _MAX_WORDS_AFTER
            else:
                continue
            if _CLAUSE_BREAK.search(between) or _words(between) > limit:
                continue
            candidate = QualifierMatch(qualifier, m.group(0), m.start(), m.end())
            if best is None or abs(m.start() - start) < abs(best.start - start):
                best = candidate
    return best


def sentence_qualifiers(sentence: str) -> frozenset[Qualifier]:
    """Qualifier classes a sentence expresses (any marker of the class counts)."""
    return frozenset(q for q, pattern in _SENTENCE_RE.items() if pattern.search(sentence))
