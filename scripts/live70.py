"""Stop 70 (docs/GRID.md § Stop 70), on this machine: the answers with the source in the prompt,
kept apart from stop 68's. The questions are stop 68's.

  uv run python scripts/live70.py reuse                                    # the 7B's graded answers
  uv run --with modal modal run scripts/modal_distill.py::live70 --gen qwen7   # then --gen minicpm1

Answers and traces quote statute text and stay git-ignored (``results/live70/``).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import live68 as l68  # type: ignore[import-not-found]  # noqa: E402

OUT = ROOT / "results/live70"
SETS = l68.SETS
ARMS = ("none", "ban", "turn")
GENERATORS = ("qwen7", "minicpm1")
# The 7B's answers with the source on the fresh questions (stops 43 and 56), graded by you.
REUSED = {
    ("qwen7", "fresh", "none"): ROOT / "results/fresh/answers.jsonl",
    ("qwen7", "fresh2", "none"): ROOT / "results/fresh2/answers.jsonl",
}
items = l68.items
rows = l68.rows
key = l68.key
read_jsonl = l68.read_jsonl


def path(generator: str) -> Path:
    return OUT / f"{generator}.jsonl"


def append(generator: str, records: Sequence[Mapping[str, Any]]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with path(generator).open("a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def done(generator: str) -> dict[str, dict[str, Any]]:
    return {r["key"]: r for r in read_jsonl(path(generator)) if r.get("text") is not None}


def reuse() -> dict[str, int]:
    out: dict[str, int] = {}
    for (generator, set_name, arm), file in REUSED.items():
        have = done(generator)
        ids = {r["id"] for r in rows(set_name)}
        records = []
        for r in read_jsonl(file):
            row_id, mode = r["key"].split(":")
            k = key(set_name, row_id, arm)
            if mode == "source" and row_id in ids and k not in have and r.get("text") is not None:
                records.append(
                    {
                        "key": k,
                        "set": set_name,
                        "id": row_id,
                        "arm": arm,
                        "text": r["text"],
                        "model": r.get("model"),
                        "reused_from": str(file.relative_to(ROOT)),
                    }
                )
        append(generator, records)
        out[f"{generator} {set_name} {arm}"] = len(records)
    return out


if __name__ == "__main__":
    if sys.argv[1:] != ["reuse"]:
        raise SystemExit(__doc__)
    print(json.dumps(reuse(), indent=1))
