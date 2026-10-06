"""Build the verifier's detector batteries (plan R1, R9, R11) from hand-written rows.

Rows live in ``dev_rows.toml`` (dev split) and ``heldout_rows.toml`` (held-out draft). Each row
pairs a generation prompt with one sentence an answer might contain, and the verdict a correct
detector should give. A row's prompt is either a router concept query (``query_id``: the query and
its gold provisions, plan R11) or an explicit ``query`` with its ``query_source`` and a premise
named by ``premise_corpus`` (corpus provisions) or ``premise_spec`` (an anchor version or timeline,
see ``premises.py``). Rows were written against the provision text only; this script never runs
the verifier. It checks every excerpt is verbatim in its premise, fills in ``source_url`` and
writes ``dev.jsonl`` or ``heldout_draft.jsonl``.

Usage: uv run python batteries/verifier/build_dev.py [--split dev|heldout]
(needs the local corpus under data/ and the anchor versions under anchors_xml/)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tomllib
from pathlib import Path
from typing import Any

import premises

ROOT = premises.ROOT
HERE = Path(__file__).resolve().parent
CONCEPT = ROOT / "batteries/router/concept/uk.jsonl"
CITATION_FORM = {
    "uk-informal-0009": ROOT / "batteries/router/uk/informal.jsonl",
    "uk-false_abstention-0019": ROOT / "batteries/router/uk/false_abstention.jsonl",
}
SPLITS = {
    "dev": (HERE / "dev_rows.toml", HERE / "dev.jsonl", "dev"),
    "heldout": (HERE / "heldout_rows.toml", HERE / "heldout_draft.jsonl", "heldout"),
}

EXPECTED = {
    "grounded_paraphrase": "EMIT",
    "connective": "EMIT",
    "premise_correction": "EMIT",
    "wrong_figure": "ROLLBACK",
    "wrong_citation": "ROLLBACK",
    "wrong_instrument": "ROLLBACK",
    "modal_shift": "ROLLBACK",
    "dropped_qualifier": "ROLLBACK",
    "value_swap": "ROLLBACK",
    "version_swap": "ROLLBACK",
    "unsupported_plausible": "ROLLBACK",
}


def _norm(text: str) -> str:
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip()


def _queries() -> dict[str, dict[str, Any]]:
    out = {}
    with CONCEPT.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            out[row["id"]] = row
    for qid, path in CITATION_FORM.items():
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                if row["id"] == qid:
                    out[qid] = row
    return out


def load_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("rb") as handle:
        return list(tomllib.load(handle)["row"])


def _resolve(row: dict[str, Any], queries: dict[str, dict[str, Any]], split: str) -> dict[str, Any]:
    """The query, query source, premise coordinates and premise spec of one row."""
    if "query_id" in row:
        query = queries[row["query_id"]]
        premise_query = queries[row.get("premise_of") or row["query_id"]]
        concept_split = "dev" if split == "dev" else "test"
        if premise_query.get("split") != concept_split:
            raise ValueError(
                f"premise query {premise_query['id']} is not in the {concept_split} split"
            )
        return {
            "query_id": row["query_id"],
            "query": query["query"],
            "query_source": f"legal-rag-router {row['query_id']}",
            "premise": premise_query["gold"],
            "premise_spec": None,
        }
    spec = row.get("premise_spec")
    if spec:
        anchor = premises.anchors()[spec.split(":", 1)[1].split("@", 1)[0]]
        if anchor["split"] != split:
            raise ValueError(f"{spec} belongs to the {anchor['split']} split")
        coordinates = [anchor["coordinate"]]
    else:
        coordinates = row["premise_corpus"]
    return {
        "query_id": None,
        "query": row["query"],
        "query_source": row["query_source"],
        "premise": coordinates,
        "premise_spec": spec,
    }


def build(split: str, data_root: Path) -> list[dict[str, Any]]:
    rows_file, _, split_name = SPLITS[split]
    queries = _queries()
    out: list[dict[str, Any]] = []
    errors: list[str] = []
    prefix = "vdev" if split == "dev" else "vhold"
    for n, row in enumerate(load_rows(rows_file), start=1):
        try:
            resolved = _resolve(row, queries, split_name)
        except (KeyError, ValueError) as exc:
            errors.append(f"row {n}: {exc}")
            continue
        premise, by_coord = premises.build(resolved, data_root)
        instrument = "/".join(resolved["premise"][0].split("/")[: _depth(resolved["premise"][0])])
        excerpt = _norm(row["excerpt"])
        if row["at"] == "fact":
            coordinate = resolved["premise"][0]
            window = next((p for p in premise.facts if excerpt in _norm(p.text)), None)
        else:
            coordinate = f"{instrument}/{row['at']}"
            window = next(
                (
                    p
                    for p in premise.passages
                    if p.coordinate
                    and (
                        coordinate == p.coordinate
                        or coordinate.startswith(p.coordinate + "/")
                        or p.coordinate.startswith(coordinate + "/")
                    )
                    and excerpt in _norm(p.text)
                ),
                None,
            )
        if window is None:
            errors.append(f"row {n}: excerpt not found under {coordinate}: {row['excerpt'][:60]!r}")
            continue
        record = by_coord.get(coordinate) or by_coord.get(window.coordinate or "") or {}
        out.append(
            {
                "id": f"{prefix}-{n:04d}",
                "split": split_name,
                "class": row["class"],
                "expected": EXPECTED[row["class"]],
                **resolved,
                "sentence": row["sentence"],
                "excerpt": row["excerpt"],
                "excerpt_coordinate": coordinate,
                "source_url": row.get("source_url") or record.get("source_url"),
                "note": row.get("note", ""),
            }
        )
    if errors:
        raise SystemExit("\n".join(errors))
    return out


def _depth(coordinate: str) -> int:
    from legal_rag_verifier.citations import instrument_depth  # noqa: PLC0415

    return instrument_depth(coordinate)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=list(SPLITS), default="dev")
    args = parser.parse_args()
    rows = build(args.split, ROOT / "data")
    text = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)
    out = SPLITS[args.split][1]
    out.write_text(text, encoding="utf-8")
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["class"]] = counts.get(r["class"], 0) + 1
    print(json.dumps({"split": args.split, "rows": len(rows), "classes": counts}, indent=2))
    print(out.name, "sha256", hashlib.sha256(text.encode("utf-8")).hexdigest())


if __name__ == "__main__":
    main()
