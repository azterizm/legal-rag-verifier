"""Sentence boundaries that survive legal abbreviations and figures.

A candidate boundary is ``.``, ``;``, ``:`` before a newline, a newline, or end of stream. A ``.``
is *not* a boundary when it closes a known abbreviation ("s.", "art.", "Ltd.", "e.g."), sits inside
a number ("£68.4k", "12.5%"), or is not followed by whitespace or the end of the text. In
streaming use a ``.`` at the very end of the text is undecided until the next character arrives
(or the stream ends): a false stop only extends the same sentence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["ABBREVIATIONS", "BOUNDARY_STOPS", "Sentence", "find_boundary", "split_sentences"]

#: Stop strings a backend decodes up to; each candidate is then confirmed by :func:`find_boundary`.
BOUNDARY_STOPS: tuple[str, ...] = (".", ";", "\n")

#: Lower-cased abbreviations whose closing ``.`` never ends a sentence.
ABBREVIATIONS = frozenset(
    {
        "s",
        "ss",
        "sec",
        "art",
        "arts",
        "reg",
        "regs",
        "para",
        "paras",
        "sch",
        "pt",
        "ch",
        "no",
        "nos",
        "ltd",
        "plc",
        "co",
        "v",
        "vs",
        "e.g",
        "i.e",
        "cf",
        "etc",
        "viz",
        "ibid",
        "op",
        "cit",
        "mr",
        "mrs",
        "ms",
        "dr",
        "prof",
        "st",
        "jan",
        "feb",
        "mar",
        "apr",
        "jun",
        "jul",
        "aug",
        "sep",
        "sept",
        "oct",
        "nov",
        "dec",
        "approx",
        "inc",
        "corp",
        "c",
        "subs",
        "subss",
        "s.i",
        "si",
        "u.k",
        "p",
        "pp",
    }
)
# Abbreviations that precede a number ("s. 124", "No. 5"): elsewhere their "." ends the sentence.
_NUMERIC_ABBREVIATIONS = frozenset(
    {
        "s",
        "ss",
        "sec",
        "art",
        "arts",
        "reg",
        "regs",
        "para",
        "paras",
        "sch",
        "pt",
        "ch",
        "no",
        "nos",
    }
    | {"p", "pp", "c", "subs", "subss"}
)
# Abbreviations that also end sentences: a boundary when a capital letter follows.
_TERMINAL_ABBREVIATIONS = frozenset({"etc", "ltd", "plc", "inc", "corp", "co"})

_WORD_BEFORE_DOT = re.compile(r"((?:[A-Za-z]\.)*[A-Za-z]+)$")


@dataclass(frozen=True, slots=True)
class Sentence:
    """A sentence and its character span in the source text (span excludes surrounding spaces)."""

    text: str
    start: int
    end: int


def _is_abbreviation(text: str, dot: int) -> bool:
    match = _WORD_BEFORE_DOT.search(text[:dot])
    if match is None:
        return False
    start = match.start(1)
    if start > 0 and (text[start - 1].isalnum() or text[start - 1] in "'’"):
        return False
    word = match.group(1).lower()
    if word not in ABBREVIATIONS:
        return False
    following = text[dot + 1 :].lstrip(" \t")
    if word in _NUMERIC_ABBREVIATIONS:
        return following[:1].isdigit() or following[:1] == "("
    if word in _TERMINAL_ABBREVIATIONS:
        return bool(following) and not following[:1].isupper() and following[:1] != "\n"
    return True


def _is_boundary_at(text: str, i: int, *, final: bool) -> bool | None:
    """Decide whether ``text[i]`` ends a sentence. ``None``: undecided until more text arrives."""
    ch = text[i]
    nxt = text[i + 1] if i + 1 < len(text) else None
    if ch in "\n;":
        return True
    if ch == ":":
        return nxt == "\n"
    if ch != ".":
        return False
    if nxt is None:
        # A trailing "." is undecided mid-stream; at the end it ends the sentence.
        return True if final else None
    if not nxt.isspace() and nxt not in "\"'’”)]":
        return False  # "£68.4k", "e.g.", "S.I." mid-token
    prev = text[i - 1] if i > 0 else ""
    return not (prev.isdigit() and nxt.isdigit()) and not _is_abbreviation(text, i)


def find_boundary(text: str, start: int = 0, *, final: bool = False) -> int | None:
    """Index just past the first confirmed boundary at or after ``start``; ``None`` if none yet.

    With ``final=True`` (end of stream) a trailing ``.`` counts and, if nothing else does, the end
    of the text is the boundary.
    """
    for i in range(start, len(text)):
        if text[i] not in ".;:\n":
            continue
        decided = _is_boundary_at(text, i, final=final)
        if decided is None:
            return None
        if decided:
            j = i + 1
            while j < len(text) and text[j] in "\"'’”)]":
                j += 1
            return j
    if final and text[start:].strip():
        return len(text)
    return None


def split_sentences(text: str) -> list[Sentence]:
    """Split a complete text into sentences (post-hoc; streaming uses :func:`find_boundary`)."""
    out: list[Sentence] = []
    pos = 0
    while pos < len(text):
        end = find_boundary(text, pos, final=True)
        if end is None:
            break
        raw = text[pos:end]
        stripped = raw.strip()
        if stripped:
            lead = len(raw) - len(raw.lstrip())
            out.append(Sentence(stripped, pos + lead, pos + lead + len(stripped)))
        pos = end
    return out
