"""Provision citations normalised to the router's coordinate tail.

``section 124(1ZA)(a)``, ``s.124(1ZA)(a)`` and ``s 124 (1ZA) (a)`` all become ``s124/1ZA/a``, the
same path that follows the instrument in a coordinate (``uk/ukpga/1996/18/s124/1ZA/a``). A
reference without a provision number ("subsection (1ZA)", "paragraph (a)") is *relative*: it is
written ``~/1ZA`` and resolved against the coordinate of the passage it appears in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "CitationMatch",
    "coordinate_tail",
    "find_citations",
    "is_relative",
    "render_citation",
    "resolve_relative",
]

# Kind words → coordinate prefix. Plural and abbreviated forms map to the same prefix.
_KINDS: dict[str, str] = {
    "section": "s",
    "sections": "s",
    "s": "s",
    "ss": "s",
    "sec": "s",
    "article": "art",
    "articles": "art",
    "art": "art",
    "arts": "art",
    "regulation": "reg",
    "regulations": "reg",
    "reg": "reg",
    "regs": "reg",
    "rule": "rule",
    "rules": "rule",
    "paragraph": "para",
    "paragraphs": "para",
    "para": "para",
    "paras": "para",
    "schedule": "sch",
    "schedules": "sch",
    "sch": "sch",
    "part": "pt",
    "parts": "pt",
    "pt": "pt",
    "chapter": "ch",
    "chapters": "ch",
    "ch": "ch",
}
# Kind words that, with only bracketed labels after them, refer inside the current provision.
_RELATIVE_KINDS = {"subsection", "subsections", "paragraph", "paragraphs", "sub-paragraph"}

_KIND_RE = (
    r"(?<![\w'’])(?P<kind>sub-paragraphs?|subsections?|sections?|articles?|regulations?|rules?|"
    r"paragraphs?|schedules?|parts?|chapters?|ss?\.?|sec\.|arts?\.|regs?\.|paras?\.|sch\.|pt\.|ch\.)"
)
_NUM = r"\d+[A-Z]{0,3}\d{0,2}(?![\w])"
_LABEL = r"\(\s?[0-9]{0,3}[A-Za-z]{0,4}\s?\)"
_ITEM = rf"(?:{_NUM}(?:\s?{_LABEL})*|{_LABEL}(?:\s?{_LABEL})*)"
_SEP = r"\s*(?:,|\band\b|\bor\b|\bto\b|-|–)\s*"
_CITATION_RE = re.compile(rf"{_KIND_RE}\s?(?P<items>{_ITEM}(?:{_SEP}{_ITEM})*)", re.IGNORECASE)
_ITEM_RE = re.compile(rf"(?P<num>{_NUM})?(?P<labels>(?:\s?{_LABEL})*)")
_LABEL_TEXT_RE = re.compile(r"\(\s?([0-9A-Za-z]+)\s?\)")
_OF_RE = re.compile(r"\s+of\s+", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class CitationMatch:
    """One normalised citation found in a text, with the span it was read from."""

    canonical: str
    start: int
    end: int
    text: str


_INSTRUMENT_DEPTH = 4  # jurisdiction/kind/year/number


def is_relative(canonical: str) -> bool:
    return canonical.startswith("~/")


def coordinate_tail(coordinate: str) -> str:
    """``uk/ukpga/1996/18/s124/1ZA`` → ``s124/1ZA``; empty for an instrument coordinate."""
    parts = coordinate.split("/")
    return "/".join(parts[_INSTRUMENT_DEPTH:]) if len(parts) > _INSTRUMENT_DEPTH else ""


def resolve_relative(canonical: str, base: str) -> str:
    """Resolve ``~/1ZA`` against a base tail (``s124/1``) → ``s124/1ZA``.

    A subsection-level reference replaces everything below the provision number; a lower-case
    letter label (``~/a``) is a paragraph of the base subsection.
    """
    if not is_relative(canonical) or not base:
        return canonical
    labels = canonical[2:].split("/")
    head, *rest = base.split("/")
    if labels[0][:1].isdigit() or not rest:
        return "/".join([head, *labels])
    return "/".join([head, rest[0], *labels])


def render_citation(canonical: str, *, style: str = "section") -> str:
    """Render ``s124/1ZA/a`` as ``section 124(1ZA)(a)`` (``style="s."``: ``s.124(1ZA)(a)``)."""
    head, *labels = canonical.split("/")
    match = re.match(r"([a-z]+)(.+)", head)
    if match is None:
        return canonical
    kind, number = match.groups()
    words = {
        "s": "section",
        "art": "article",
        "reg": "regulation",
        "rule": "rule",
        "para": "paragraph",
        "sch": "Schedule",
        "pt": "Part",
        "ch": "Chapter",
    }
    prefix = "s." if style == "s." and kind == "s" else words.get(kind, kind) + " "
    return prefix + number + "".join(f"({label})" for label in labels)


def _kind_prefix(kind: str) -> str | None:
    key = kind.lower().rstrip(".")
    if key in _RELATIVE_KINDS or key.startswith("sub-paragraph"):
        return None
    return _KINDS.get(key)


def _items(kind_prefix: str | None, items_text: str) -> list[str]:
    out: list[str] = []
    last_number: str | None = None
    last_labels: list[str] = []
    for raw in re.split(_SEP, items_text):
        item = _ITEM_RE.fullmatch(raw.strip())
        if item is None:
            continue
        labels = _LABEL_TEXT_RE.findall(item.group("labels") or "")
        number = item.group("num")
        if number is not None:
            last_number = number
        elif labels:
            labels = _sibling(last_labels, labels)
        last_labels = labels
        if kind_prefix is None:
            if number is not None:  # "paragraph 3" with no schedule: an absolute paragraph
                out.append("/".join([f"para{number}", *labels]))
            elif labels:
                out.append("/".join(["~", *labels]))
        elif number is not None:
            out.append("/".join([f"{kind_prefix}{number}", *labels]))
        elif labels and last_number is not None:  # "section 117(1) and (2)" → s117/2
            out.append("/".join([f"{kind_prefix}{last_number}", *labels]))
    return out


def _label_class(label: str) -> str:
    if label[:1].isdigit():
        return "digit"
    return "lower" if label.islower() else "upper"


def _sibling(previous: list[str], labels: list[str]) -> list[str]:
    """ "(1ZA)(a) and (b)": ``(b)`` replaces the deepest previous label of the same class."""
    first = _label_class(labels[0])
    for depth in range(len(previous) - 1, -1, -1):
        if _label_class(previous[depth]) == first:
            return previous[:depth] + labels
    return labels


def find_citations(text: str) -> list[CitationMatch]:
    """Every citation in ``text``, normalised. Chains joined by "of" are composed:
    "paragraph (a) of subsection (3) of section 117" → ``s117/3/a``;
    "paragraph 3 of Schedule 2" → ``sch2/para3``.
    """
    raw: list[tuple[list[str], int, int]] = []
    for match in _CITATION_RE.finditer(text):
        kind = match.group("kind")
        prefix = _kind_prefix(kind)
        if kind.lower() in {"s", "ss"} and not match.group("items")[:1].isdigit():
            continue  # a bare "s" before a bracket is not a section
        cites = _items(prefix, match.group("items"))
        if cites:
            raw.append((cites, match.start(), match.end()))

    merged: list[CitationMatch] = []
    i = 0
    while i < len(raw):
        cites, start, end = raw[i]
        while i + 1 < len(raw) and _OF_RE.fullmatch(text[end : raw[i + 1][1]]):
            outer, _, outer_end = raw[i + 1]
            cites = [_compose(inner, outer[0]) for inner in cites]
            end = outer_end
            i += 1
        merged.extend(CitationMatch(c, start, end, text[start:end]) for c in cites)
        i += 1
    return merged


def _compose(inner: str, outer: str) -> str:
    if is_relative(inner):
        return outer + "/" + inner[2:]
    if inner.startswith("para") and outer.startswith("sch"):
        return outer + "/" + inner
    return inner
