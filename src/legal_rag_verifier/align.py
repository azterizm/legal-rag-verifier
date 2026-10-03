"""Lexical alignment of a sentence to premise windows (stdlib; the NLI head re-ranks in M2).

Score = IDF-weighted overlap of content-word stems, normalised by window length. Figures and
citations are left out of the score so that a wrong figure does not pull the sentence towards
the window it was copied from.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence

__all__ = ["content_stems", "rank_windows"]

_STOP = frozenset(
    {
        "a",
        "an",
        "the",
        "of",
        "and",
        "or",
        "to",
        "in",
        "on",
        "at",
        "by",
        "for",
        "from",
        "with",
        "within",
        "without",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "their",
        "there",
        "here",
        "which",
        "who",
        "whom",
        "whose",
        "what",
        "when",
        "where",
        "how",
        "not",
        "no",
        "any",
        "all",
        "each",
        "every",
        "such",
        "other",
        "than",
        "then",
        "so",
        "if",
        "under",
        "into",
        "over",
        "per",
        "also",
        "only",
        "same",
        "may",
        "shall",
        "must",
        "can",
        "will",
        "would",
        "should",
        "could",
        "has",
        "have",
        "had",
        "do",
        "does",
        "did",
        "person",
        "persons",
    }
)
_WORD = re.compile(r"[a-z][a-z'’]+")


def _stem(word: str) -> str:
    word = word.replace("’", "'").removesuffix("'s").rstrip("'")
    for suffix in ("ations", "ation", "ments", "ment", "ings", "ing", "ies", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return word


def content_stems(text: str) -> list[str]:
    return [_stem(w) for w in _WORD.findall(text.lower()) if w not in _STOP]


def rank_windows(sentence: str, windows: Sequence[str]) -> list[tuple[int, float]]:
    """Window indices with scores, best first (ties keep document order)."""
    docs = [Counter(content_stems(w)) for w in windows]
    df: Counter[str] = Counter()
    for d in docs:
        df.update(d.keys())
    n = len(windows)
    query = set(content_stems(sentence))
    scored: list[tuple[int, float]] = []
    for i, doc in enumerate(docs):
        overlap = sum(math.log(1 + n / df[t]) for t in query if t in doc)
        length = math.sqrt(max(sum(doc.values()), 1))
        scored.append((i, overlap / length))
    return sorted(scored, key=lambda pair: (-pair[1], pair[0]))
