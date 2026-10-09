"""Stop 45: public documentation pages split into sections under their headings (software pool).

Pages are fetched once and cached under ``results/distill/pages/`` (git-ignored). A section is the
text blocks under one heading (h1 to h4), 300 to 2,500 characters; a longer one is split at block
boundaries into pieces of at most 1,800 characters.
"""

from __future__ import annotations

import hashlib
import re
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "results/distill/pages"
SKIP = {"script", "style", "nav", "footer", "header", "noscript", "svg", "aside"}
BLOCK = {"p", "li", "pre", "dt", "dd", "td", "th", "blockquote"}
HEADING = {"h1", "h2", "h3", "h4"}
MIN_CHARS, MAX_CHARS, PIECE = 300, 2500, 1800


class _Blocks(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str, str]] = []
        self._text: list[str] = []
        self._tag = ""
        self._skip = 0
        self._pre = 0

    def _flush(self) -> None:
        text = "".join(self._text)
        text = text.strip() if self._pre else re.sub(r"\s+", " ", text).strip()
        text = text.replace("¶", "").strip()
        if text and self._tag:
            self.blocks.append((self._tag, text))
        self._text = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIP:
            self._skip += 1
        if tag in BLOCK | HEADING:
            self._flush()
            self._tag = tag
        if tag == "pre":
            self._pre += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP:
            self._skip = max(0, self._skip - 1)
        if tag in BLOCK | HEADING:
            self._flush()
            self._tag = ""
        if tag == "pre":
            self._pre = max(0, self._pre - 1)

    def handle_data(self, data: str) -> None:
        if not self._skip and self._tag:
            self._text.append(data)


def fetch(url: str) -> str:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (hashlib.sha256(url.encode()).hexdigest()[:16] + ".html")
    if not path.exists():
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})  # noqa: S310
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - fixed URLs
            path.write_bytes(response.read())
    return path.read_text(encoding="utf-8", errors="ignore")


def sections(url: str) -> list[tuple[str, str]]:
    """(heading, text) per section of the page, in page order."""
    parser = _Blocks()
    parser.feed(fetch(url))
    title = next((t for tag, t in parser.blocks if tag == "h1"), "")
    out: list[tuple[str, str]] = []
    heading, body = title, list[str]()
    for tag, text in [*parser.blocks, ("h1", "")]:
        if tag in HEADING:
            out += _pieces(heading if heading == title else f"{title}, {heading}", body)
            heading, body = text, []
        else:
            body.append(text)
    return out


def _pieces(heading: str, body: list[str]) -> list[tuple[str, str]]:
    text = "\n".join(body)
    if len(text) < MIN_CHARS:
        return []
    if len(text) <= MAX_CHARS:
        return [(heading, text)]
    out: list[tuple[str, str]] = []
    piece: list[str] = []
    for block in body:
        if piece and len("\n".join([*piece, block])) > PIECE:
            out.append((heading, "\n".join(piece)))
            piece = []
        piece.append(block)
    if piece:
        out.append((heading, "\n".join(piece)))
    return [(h, t) for h, t in out if MIN_CHARS <= len(t) <= MAX_CHARS]
