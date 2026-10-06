"""Render a built battery as a Markdown review sheet, grouped by premise (label review, plan R1).

Usage: uv run python batteries/verifier/review_sheet.py [dev.jsonl|heldout_draft.jsonl] > review.md
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    source = HERE / (sys.argv[1] if len(sys.argv) > 1 else "dev.jsonl")
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
    premise_keys = {r.get("premise_spec") or tuple(r["premise"]) for r in rows}
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["class"]] = counts.get(r["class"], 0) + 1
    out = [
        f"# Detector battery ({rows[0]['split'] if rows else ''}) — label review sheet",
        "",
        (
            f"{len(rows)} rows over {len(premise_keys)} "
            "premises. "
            "Each row: the sentence, the label (class → expected verdict), and the excerpt of the "
            "provision it was judged against. Mark any label you disagree with by row id."
        ),
        "",
        "| Class | Rows | Expected |",
        "|---|---:|---|",
    ]
    expected = {r["class"]: r["expected"] for r in rows}
    out += [f"| {c} | {n} | {expected[c]} |" for c, n in sorted(counts.items())]
    current = None
    for r in rows:
        key = r.get("premise_spec") or " + ".join(r["premise"])
        if key != current:
            current = key
            out += ["", f"## {key}", ""]
        out.append(f"Query ({r.get('query_source') or r.get('query_id')}): `{r['query']}`")
        line = (
            f"- **{r['id']}** · `{r['class']}` → **{r['expected']}**  \n"
            f"  Sentence: {r['sentence']}  \n"
            f"  Source ([{r['excerpt_coordinate'].split('/', 4)[-1]}]({r['source_url']})): "
            f"“{r['excerpt']}”"
        )
        if r["note"]:
            line += f"  \n  Note: {r['note']}"
        out.append(line)
    print("\n".join(out))


if __name__ == "__main__":
    main()
