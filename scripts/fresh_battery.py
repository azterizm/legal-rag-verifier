"""Stop 43: the fresh blind test (docs/GRID.md § Stops 43 to 47).

80 questions (``batteries/fresh/``: 40 software, 40 statutes), each answered twice by Qwen 2.5 7B on
a Modal L4: with the source in the prompt, and closed-book. You grade every sentence against the
source shown. Answers, key and sheet are git-ignored until your grades are committed.

  uv run python scripts/fresh_battery.py prompts     # counts; what is sent
  uv run --with modal modal run scripts/modal_distill.py::fresh_answers   # resumable
  uv run python scripts/fresh_battery.py sheet       # results/fresh/: sheet, grades, key
  uv run python scripts/fresh_battery.py seal        # sha256 of every file, for GRID
"""

from __future__ import annotations

import argparse
import csv
import hashlib
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

from legal_rag_verifier.engine import SYSTEM_PROMPT  # noqa: E402
from legal_rag_verifier.premise import Passage, Premise  # noqa: E402
from legal_rag_verifier.segmenter import split_sentences  # noqa: E402

BATTERY = ROOT / "batteries/fresh"
OUT = ROOT / "results/fresh"
ANSWERS = OUT / "answers.jsonl"
SEED = 20261009
MODES = ("source", "closed")
# stop 37's software prompt (scripts/grid_qwen.py), and the closed-book versions fixed in GRID
SOFTWARE_PROMPT = (
    "You answer questions about software using only the documentation below. State figures, "
    "defaults, version numbers and names exactly as the documentation gives them. If the "
    "documentation does not answer the question, say so. Answer in a few plain sentences, without "
    "headings or lists.\n\nDocumentation:\n{premise}"
)
CLOSED = {
    "software": (
        "You answer questions about software. State figures, defaults, version numbers and names "
        "exactly. If you do not know the answer, say so. Answer in a few plain sentences, without "
        "headings or lists."
    ),
    "legal": (
        "You answer questions about legislation. State figures, dates, section numbers and the "
        "names of Acts exactly. If you do not know the answer, say so. Answer in a few plain "
        "sentences, without headings or lists."
    ),
}


def rows() -> list[dict[str, Any]]:
    out = []
    for name, domain in (("software", "software"), ("statutes", "legal")):
        lines = (BATTERY / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
        out += [{**json.loads(x), "domain": domain} for x in lines]
    return out


def premise(row: Mapping[str, Any]) -> Premise:
    """Software: the quoted passages. Statutes: the provision with its enrichment layer, as run."""
    if row["domain"] == "software":
        return Premise(tuple(Passage(p["text"], heading=p["heading"]) for p in row["passages"]))
    import premises  # noqa: PLC0415
    from grid_prompts import ENRICHMENT  # type: ignore[import-not-found]  # noqa: PLC0415

    built, _ = premises.build(dict(row), ROOT / "data", ENRICHMENT)
    return built


def source_text(row: Mapping[str, Any]) -> str:
    from grid_cells import render_premise  # type: ignore[import-not-found]  # noqa: PLC0415

    return str(render_premise(premise(row)))


def requests() -> list[dict[str, Any]]:
    """Two chat requests per question. No label or grade is in any of them."""
    out = []
    for row in rows():
        prompt = SOFTWARE_PROMPT if row["domain"] == "software" else SYSTEM_PROMPT
        for mode in MODES:
            system = (
                prompt.format(premise=source_text(row))
                if mode == "source"
                else CLOSED[row["domain"]]
            )
            out.append(
                {
                    "key": f"{row['id']}:{mode}",
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": row["query"]},
                    ],
                }
            )
    return out


def answers() -> dict[str, dict[str, Any]]:
    if not ANSWERS.exists():
        return {}
    lines = ANSWERS.read_text(encoding="utf-8").splitlines()
    return {r["key"]: r for r in map(json.loads, lines) if r.get("text") is not None}


def append_answers(records: Sequence[Mapping[str, Any]]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with ANSWERS.open("a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def sheet() -> None:
    """Every sentence of every answer; questions in a seeded order, answers lettered at random."""
    done = answers()
    by_id = {r["id"]: r for r in rows()}
    missing = [f"{i}:{m}" for i in by_id for m in MODES if f"{i}:{m}" not in done]
    if missing:
        raise RuntimeError(f"{len(missing)} answers missing; rerun fresh_answers")
    rng = random.Random(SEED)  # noqa: S311 - a shuffle, not a secret
    order = list(by_id)
    rng.shuffle(order)
    lines = [
        "# Fresh test: your grading sheet (stop 43)",
        "",
        (
            "For each numbered sentence, fill `correct` in `grades.csv`: yes if every claim in the "
            "sentence matches the source shown, no if any claim does not, unsure otherwise. A "
            "sentence with no claim (a link or a refusal) is yes unless it misstates the source."
        ),
        "",
    ]
    key: dict[str, dict[str, Any]] = {}
    grades = []
    for q, row_id in enumerate(order, 1):
        row = by_id[row_id]
        lines += [
            f"## Q{q:02d}. {row['query']}",
            "",
            "Source:",
            "",
            "```",
            source_text(row),
            "```",
            "",
        ]
        modes = list(MODES)
        rng.shuffle(modes)
        for letter, mode in zip("AB", modes, strict=True):
            lines += [f"**Answer {letter}**", ""]
            for n, s in enumerate(split_sentences(done[f"{row_id}:{mode}"]["text"]), 1):
                item = f"Q{q:02d}{letter}{n}"
                lines.append(f"- **{item}.** {s.text}")
                key[item] = {"id": row_id, "mode": mode, "sentence": n - 1, "text": s.text}
                grades.append({"item": item, "correct": "", "note": ""})
            lines.append("")
    (OUT / "sheet.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (OUT / "key.json").write_text(json.dumps(key, indent=1, ensure_ascii=False) + "\n", "utf-8")
    with (OUT / "grades.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["item", "correct", "note"])
        writer.writeheader()
        writer.writerows(grades)
    print(f"{len(order)} questions, {len(grades)} sentences → {OUT.relative_to(ROOT)}")


def seal() -> dict[str, str]:
    files = [
        BATTERY / "software.jsonl",
        BATTERY / "statutes.jsonl",
        ANSWERS,
        OUT / "key.json",
        OUT / "sheet.md",
        OUT / "grades.csv",
    ]
    out = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (OUT / "seal.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prompts", "sheet", "seal"])
    command = parser.parse_args().command
    if command == "prompts":
        reqs = requests()
        chars = [sum(len(m["content"]) for m in r["messages"]) for r in reqs]
        print(json.dumps({"requests": len(reqs), "done": len(answers()), "max_chars": max(chars)}))
    elif command == "sheet":
        sheet()
    else:
        print(json.dumps(seal(), indent=1))


if __name__ == "__main__":
    main()
