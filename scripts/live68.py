"""Stop 68 (docs/GRID.md § Stop 68), on this machine: the 240 questions, the answers already made,
and where each generator's answers are kept. The loop runs on Modal.

  uv run python scripts/live68.py questions                        # counts; the pool draw
  uv run python scripts/live68.py reuse                            # copy the answers already made
  uv run --with modal modal run scripts/modal_distill.py::live68 --gen qwen27

Answers and traces quote statute text and stay git-ignored (``results/live68/``).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "batteries/verifier"))

OUT = ROOT / "results/live68"
POOL = ROOT / "results/distill/pool2"
SETS = ("fresh", "fresh2", "pool")
ARMS = ("none", "turn", "plain")
GENERATORS = ("qwen27", "qwen7", "minicpm1")
SEED = 20261016
PER_DOMAIN = 60
# Answers already made with the same model, server, decoding and judge (GRID § Stop 68): the
# closed-book answer of each question, as ``(generator, set, arm) → file``.
REUSED = {
    ("qwen7", "fresh", "none"): ROOT / "results/fresh/answers.jsonl",
    ("qwen7", "fresh2", "none"): ROOT / "results/fresh2/answers.jsonl",
    ("qwen27", "fresh2", "none"): ROOT / "results/fresh2-q27/answers.jsonl",
    ("qwen27", "fresh2", "turn"): ROOT / "results/fresh2-short-live/answers.jsonl",
}


def key(set_name: str, row_id: str, arm: str) -> str:
    return f"{set_name}:{row_id}:{arm}"


def path(generator: str) -> Path:
    return OUT / f"{generator}.jsonl"


def read_jsonl(file: Path) -> list[dict[str, Any]]:
    if not file.exists():
        return []
    return [json.loads(x) for x in file.read_text("utf-8").splitlines() if x.strip()]


def append(generator: str, records: Sequence[Mapping[str, Any]]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with path(generator).open("a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def done(generator: str) -> dict[str, dict[str, Any]]:
    return {r["key"]: r for r in read_jsonl(path(generator)) if r.get("text") is not None}


# ---------------------------------------------------------------------- questions


def draw(pool: Sequence[Mapping[str, Any]], seed: int = SEED, n: int = PER_DOMAIN) -> list[str]:
    """``n`` source ids per domain, drawn with ``seed`` from the sorted ids."""
    rng = random.Random(seed)  # noqa: S311 - a draw, not a secret
    out: list[str] = []
    for domain in ("legal", "software"):
        ids = sorted(r["id"] for r in pool if r["domain"] == domain)
        out += sorted(rng.sample(ids, n))
    return out


def pool_rows() -> list[dict[str, Any]]:
    pool = read_jsonl(POOL / "pool.jsonl")
    questions = {r["source"]: r["questions"] for r in read_jsonl(POOL / "questions.jsonl")}
    by_id = {r["id"]: r for r in pool}
    return [{**by_id[i], "query": questions[i][0]} for i in draw(pool)]


def fresh_rows(set_name: str) -> list[dict[str, Any]]:
    import fresh_battery as fb  # type: ignore[import-not-found]  # noqa: PLC0415

    keep = fb.BATTERY
    try:
        fb.BATTERY = ROOT / "batteries" / set_name
        return list(fb.rows())
    finally:
        fb.BATTERY = keep


def rows(set_name: str) -> list[dict[str, Any]]:
    return pool_rows() if set_name == "pool" else fresh_rows(set_name)


def premise(set_name: str, row: Mapping[str, Any]) -> Any:
    if set_name == "pool":
        import distill_data as dd  # type: ignore[import-not-found]  # noqa: PLC0415

        return dd.premise(row)
    import fresh_battery as fb  # noqa: PLC0415

    return fb.premise(row)


def items(set_name: str) -> list[dict[str, Any]]:
    """What the loop needs per question: id, query, domain and the premise."""
    return [
        {"id": r["id"], "query": r["query"], "domain": r["domain"], "premise": premise(set_name, r)}
        for r in rows(set_name)
    ]


# ---------------------------------------------------------------------- reuse


def reuse() -> dict[str, int]:
    """Copy the closed-book answers already made into each generator's file, once."""
    out: dict[str, int] = {}
    for (generator, set_name, arm), file in REUSED.items():
        have = done(generator)
        ids = {r["id"] for r in rows(set_name)}
        records = []
        for r in read_jsonl(file):
            row_id, mode = r["key"].split(":")
            k = key(set_name, row_id, arm)
            if mode == "closed" and row_id in ids and k not in have and r.get("text") is not None:
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["questions", "reuse"])
    command = parser.parse_args().command
    if command == "questions":
        counts: dict[str, Any] = {s: len(rows(s)) for s in SETS}
        pool = pool_rows()
        counts["pool_domains"] = {
            d: sum(r["domain"] == d for r in pool) for d in ("legal", "software")
        }
        print(json.dumps(counts, indent=1))
    else:
        print(json.dumps(reuse(), indent=1))


if __name__ == "__main__":
    main()
