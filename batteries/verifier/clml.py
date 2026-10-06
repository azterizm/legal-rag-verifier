"""Convert a legislation.gov.uk point-in-time CLML document into provision records.

The records have the shape of the router's ``data/uk`` rows (``coordinate``, ``parent``,
``number_label``, ``text``, ``text_after``, ``order``, ``source_url``), so a dated version of a
provision is assembled into premise windows by the same ``Premise.from_records`` as the corpus.
Each provision element carries an ``IdURI`` (``…/id/ukpga/1996/18/section/227/1/zza``) that maps
onto the router's coordinate (``uk/ukpga/1996/18/s227/1/zza``).

Battery tooling only (stdlib); the input files are official, already-downloaded documents.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

NS = "{http://www.legislation.gov.uk/namespaces/legislation}"
_PROVISION_TAGS = {f"{NS}P{i}" for i in range(1, 8)}
_PARA_TAGS = {f"{NS}P{i}para" for i in range(1, 8)}
_DROP = {f"{NS}CommentaryRef", f"{NS}FootnoteRef", f"{NS}Pnumber"}
_KIND = {
    "section": "s",
    "schedule": "sch",
    "paragraph": "para",
    "regulation": "reg",
    "article": "art",
}
_ID = re.compile(r"/id/(?P<inst>(?:ukpga|uksi|asp|nisi|wsi)/[^/]+/[^/]+)/(?P<rest>.+)$")


def coordinate_of(id_uri: str) -> str | None:
    """``…/id/ukpga/1996/18/section/227/1`` → ``uk/ukpga/1996/18/s227/1``."""
    match = _ID.search(id_uri)
    if match is None:
        return None
    parts = match["rest"].split("/")
    if parts[0] not in _KIND or len(parts) < 2:  # noqa: PLR2004
        return None
    head = _KIND[parts[0]] + parts[1]
    return "/".join(["uk", match["inst"], head, *parts[2:]])


def _text(element: ET.Element) -> str:
    """All text under ``element`` except commentary/footnote markers and provision numbers."""
    out: list[str] = []

    def walk(node: ET.Element) -> None:
        if node.tag in _DROP:
            if node.tail:
                out.append(node.tail)
            return
        if node.text:
            out.append(node.text)
        for child in node:
            walk(child)
        if node is not element and node.tail:
            out.append(node.tail)

    walk(element)
    return re.sub(r"\s+", " ", "".join(out)).strip()


def _table(element: ET.Element) -> str:
    """Table rows as "cell cell; cell cell"."""
    rows = [
        " ".join(_text(cell) for cell in row if cell.tag.endswith(("}td", "}th")))
        for row in element.iter()
        if row.tag.endswith("}tr")
    ]
    return "; ".join(r for r in rows if r)


def _number(element: ET.Element) -> str:
    pnumber = element.find(f"{NS}Pnumber")
    if pnumber is None:
        return ""
    return re.sub(r"\s+", "", "".join(pnumber.itertext()))


def records(path: Path) -> list[dict[str, Any]]:
    """Provision records (and the instrument record) for one CLML document."""
    root = ET.parse(path).getroot()  # noqa: S314 - official document already on disk
    title = root.findtext(".//{http://purl.org/dc/elements/1.1/}title") or ""
    out: list[dict[str, Any]] = []
    order = 0

    def visit(element: ET.Element, parent: str | None) -> None:
        nonlocal order
        coordinate = None
        if element.tag in _PROVISION_TAGS:
            coordinate = coordinate_of(element.get("IdURI", ""))
        if coordinate is not None:
            before: list[str] = []
            after: list[str] = []
            seen_child = False
            for part in element:
                if part.tag in _PARA_TAGS:
                    for item in part:
                        if item.tag in _PROVISION_TAGS:
                            seen_child = True
                            continue
                        (after if seen_child else before).append(_text(item))
                elif part.tag == f"{NS}Tabular":  # a table beside the subsection's text
                    after.append(_table(part))
            instrument = "/".join(coordinate.split("/")[:4])
            out.append(
                {
                    "record_type": "provision",
                    "coordinate": coordinate,
                    "parent": parent or instrument,
                    "number_label": _number(element),
                    "order": order,
                    "text": " ".join(t for t in before if t),
                    "text_after": " ".join(t for t in after if t),
                    "repealed": False,
                    "source_url": element.get("DocumentURI", ""),
                }
            )
            order += 1
            parent = coordinate
        for child in element:
            visit(child, parent)

    body = root.find(f".//{NS}Body")
    if body is not None:
        visit(body, None)
    if out:
        instrument = "/".join(out[0]["coordinate"].split("/")[:4])
        out.insert(0, {"record_type": "instrument", "coordinate": instrument, "title": title})
    return out
