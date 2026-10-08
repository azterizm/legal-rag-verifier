"""Stop 36: a human check of rollbacks and retries (docs/GRID.md § Stop 36).

The auditor both rejects a sentence and accepts its retry, so a retry that passes the auditor is not
shown to be right. This stop labels sentences by hand and with two LLM judges, blind:

- **core**: the 46 parity states of stop 29, each with its rejected draft X and the first retries
  R0, R1, R3 and R4 (exact duplicates within a state labelled once). You label all of it.
- **extended**: every rejected draft and every released sentence in the test traces of 4B,
  4B-inject and 4B-inject-v2. Judges only.

Each sentence is labelled read after the answer so far: ``grounding``, ``on_question``,
``reads_on``. The judges see the question, the provisions (statute text only), the answer so far
and one sentence; never the arm, the cell or a verdict.

  uv run python scripts/rollback_review.py build           # sheet, blank labels, key, item files
  uv run python scripts/rollback_review.py pilot           # dev only: the judge prompt, both judges
  uv run python scripts/rollback_review.py judge --model gpt-oss-120b-medium --set core   # on a go

The sheet quotes full statute text and the key unblinds it: both are git-ignored, and the key's
SHA-256 is recorded in docs/GRID.md before labelling. Router calls on test, and every Gemini call,
need your go.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "batteries/verifier"))

from grid_judge import chat  # type: ignore[import-not-found]  # noqa: E402
from grid_prompts import premise, rows  # type: ignore[import-not-found]  # noqa: E402
from replay_states import (  # type: ignore[import-not-found]  # noqa: E402
    committed_text,
    load,
    shared_states,
)

from legal_rag_verifier.engine import render_premise  # noqa: E402

GRID = ROOT / "results/grid"
OUT = GRID / "rollback"
SEED = 20261008
ARMS = ("X", "R0", "R1", "R3", "R4")
EXTENDED_CELLS = ("4B", "4B-inject", "4B-inject-v2")
PILOT_CELLS = ("4B-inject-turn", "4B-inject-v2")
JUDGES = ("gpt-oss-120b-medium", "gemini-3.8-flash-high")  # named by you; no other model is called
GROUNDING = ("supported", "unsupported", "contradicted", "no_claim")
YES_NO = ("yes", "no")
ERRORS = (
    "wrong_figure",
    "wrong_citation",
    "wrong_instrument",
    "dropped_qualifier",
    "fabricated",
    "other",
)

DEFINITIONS = """\
- grounding:
  - "supported": every claim in the sentence, with its figures, citations, Act names, conditions
    and qualifiers, is stated in or follows directly from the provisions.
  - "unsupported": the sentence makes a claim the provisions do not make, including a rule stated
    without a condition or qualifier the provisions attach to it.
  - "contradicted": the provisions say otherwise.
  - "no_claim": the sentence makes no legal claim (a heading, a connective, a refusal). A sentence
    cut off part way is labelled on the claims it does make.
- on_question: "yes" if the sentence helps answer the question asked; "no" if it states law the
  question did not ask about.
- reads_on: "yes" if the sentence is complete and continues the answer so far without repeating
  it; "no" for a fragment, a repeat or a copied heading."""

SYSTEM = (
    "You are a careful UK legal reviewer. You check one sentence of an answer against the "
    "statutory provisions it was written from. Judge only against the provisions given, not "
    "outside knowledge. Reply with a single JSON object."
)
USER = """Question: {query}

Provisions:
<<<
{provisions}
>>>

Answer so far:
<<<
{prefix}
>>>

Next sentence to review:
<<<
{sentence}
>>>

Label the next sentence, read after the answer so far.
{definitions}

Return JSON with keys:
  "grounding": "supported" | "unsupported" | "contradicted" | "no_claim",
  "error": null, or for "unsupported" or "contradicted" one of "wrong_figure" | "wrong_citation" |
     "wrong_instrument" | "dropped_qualifier" | "fabricated" | "other",
  "on_question": "yes" | "no",
  "reads_on": "yes" | "no",
  "reason": one sentence."""
PROMPT_SHA = hashlib.sha256((SYSTEM + USER + DEFINITIONS).encode()).hexdigest()
NOTHING_YET = "(nothing yet: this is the first sentence)"


@dataclass
class Item:
    """One sentence to label, read after the answer so far."""

    id: str  # the grid prompt id
    prefix: str
    sentence: str
    sources: list[dict[str, Any]] = field(default_factory=list)  # arm or cell, kind, verdict

    @property
    def sha(self) -> str:
        blob = json.dumps([self.id, self.prefix, self.sentence], ensure_ascii=False)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


def dedupe(items: Iterable[Item]) -> list[Item]:
    """Exact duplicates (same prompt, answer so far and sentence) merged, sources kept, in order."""
    merged: dict[str, Item] = {}
    for item in items:
        if item.sha in merged:
            merged[item.sha].sources.extend(item.sources)
        else:
            merged[item.sha] = item
    return list(merged.values())


def state_items(record: dict[str, Any], prefix: str) -> tuple[list[Item], list[str]]:
    """A stop 29 state's sentences (X and the retries), and the arms with no text to label."""
    items, empty = [], []
    for arm in ARMS:
        result = record[arm]
        text = (result.get("text") or "").strip()
        if not text:
            empty.append(arm)
            continue
        source = {"arm": arm, "verdict": result.get("verdict", "ROLLBACK" if arm == "X" else None)}
        items.append(Item(record["id"], prefix, text, [source]))
    return dedupe(items), empty


def core() -> tuple[list[tuple[str, list[Item]]], dict[str, list[str]]]:
    """Per parity state: its prompt id and its sentences; and the empty arms per state."""
    a, b = load(GRID / "4B.jsonl"), load(GRID / "4B-inject.jsonl")
    states = {s.id: s for s in shared_states(a, b)[0]}
    records = [json.loads(x) for x in (GRID / "replay/arms.jsonl").read_text().splitlines()]
    out, empty = [], {}
    for record in (r for r in records if r["parity"]):
        state = states[record["id"]]
        if record["X"]["text"].strip() != state.rejected.strip():
            raise ValueError(f"{record['id']}: X differs from the recorded rejected draft")
        items, missing = state_items(record, state.committed.strip())
        out.append((record["id"], items))
        if missing:
            empty[record["id"]] = missing
    return out, empty


def trace_items(record: dict[str, Any], cell: str) -> list[Item]:
    """Every rejected draft and every released sentence of one traced answer."""
    trace = record.get("trace")
    if not trace:
        return []  # answered by the router's refusal, never generated
    items: list[Item] = []
    sentences = trace["sentences"]
    for i, sentence in enumerate(sentences):
        prefix = committed_text(record["answer"], [s["text"] for s in sentences[:i]]).strip()
        for n, attempt in enumerate(sentence["attempts"]):
            verdict = attempt["verdict"]
            text = (verdict.get("text") or "").strip()
            if not text:
                continue
            if verdict["verdict"] != "EMIT":
                source = {"cell": cell, "kind": "rejected", "attempt": n, "verdict": "ROLLBACK"}
            elif sentence["outcome"] == "emitted":
                source = {"cell": cell, "kind": "released", "attempt": n, "verdict": "EMIT"}
            else:
                continue
            items.append(Item(record["id"], prefix, text, [source]))
    return items


def extended() -> list[Item]:
    items = [
        item
        for cell in EXTENDED_CELLS
        for record in load(GRID / f"{cell}.jsonl").values()
        for item in trace_items(record, cell)
    ]
    return dedupe(items)


def provisions(row: dict[str, Any]) -> str:
    return render_premise(premise(row, enrichment=None)) or "(none)"


def code(state: int, letter: int) -> str:
    return f"{state:02d}{'ABCDEFGH'[letter]}"


def sheet(states: Sequence[tuple[str, list[Item]]], by_id: dict[str, dict[str, Any]]) -> str:
    parts = [
        "# Stop 36 review sheet (blind)",
        "",
        "Label every lettered sentence in `labels.csv`, read after the answer so far. Judge only",
        "against the provisions shown. Label each sentence on its own, not against the others.",
        "Leave `note` empty or write a few words.",
        "",
        "Columns: `grounding` (supported / unsupported / contradicted / no_claim), `on_question`",
        "(yes / no), `reads_on` (yes / no).",
        "",
        DEFINITIONS,
    ]
    for n, (key, items) in enumerate(states, 1):
        row = by_id[key]
        parts += [
            "",
            "---",
            "",
            f"## Question {n:02d}",
            "",
            f"**Question:** {row['query']}",
            "",
            "<details><summary>Provisions</summary>",
            "",
            provisions(row),
            "",
            "</details>",
            "",
            f"**Answer so far:** {items[0].prefix or NOTHING_YET}",
            "",
        ]
        parts += [f"**{code(n, i)}.** {item.sentence}\n" for i, item in enumerate(items)]
    return "\n".join(parts) + "\n"


def build() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    by_id = {r["id"]: r for r in rows("test")}
    states, empty = core()
    rng = random.Random(SEED)  # noqa: S311 - a reproducible order, not a secret
    rng.shuffle(states)
    for _, items in states:
        rng.shuffle(items)
    key, lines = [], []
    for n, (prompt_id, items) in enumerate(states, 1):
        for i, item in enumerate(items):
            key.append(
                {"item": code(n, i), "id": prompt_id, "sha": item.sha, "sources": item.sources}
            )
            lines.append(
                {
                    "item": code(n, i),
                    "id": prompt_id,
                    "sha": item.sha,
                    "prefix": item.prefix,
                    "sentence": item.sentence,
                }
            )
    (OUT / "sheet.md").write_text(sheet(states, by_id), encoding="utf-8")
    key_text = json.dumps({"empty_arms": empty, "items": key}, indent=1, ensure_ascii=False) + "\n"
    (OUT / "key.json").write_text(key_text, encoding="utf-8")
    _write_jsonl(OUT / "core.jsonl", lines)
    labels = OUT / "labels.csv"
    if not labels.exists():  # never overwrite your labels
        with labels.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["item", "grounding", "on_question", "reads_on", "note"])
            writer.writerows([k["item"], "", "", "", ""] for k in key)
    ext = extended()
    _write_jsonl(
        OUT / "extended.jsonl",
        [
            {
                "id": i.id,
                "sha": i.sha,
                "prefix": i.prefix,
                "sentence": i.sentence,
                "sources": i.sources,
            }
            for i in ext
        ],
    )
    print(
        json.dumps(
            {
                "core_states": len(states),
                "core_items": len(key),
                "core_empty_arms": sum(len(v) for v in empty.values()),
                "extended_items": len(ext),
                "extended_rejected": sum(
                    any(s["kind"] == "rejected" for s in i.sources) for i in ext
                ),
                "extended_released": sum(
                    any(s["kind"] == "released" for s in i.sources) for i in ext
                ),
                "key_sha256": hashlib.sha256(key_text.encode()).hexdigest(),
                "prompt_sha256": PROMPT_SHA,
            },
            indent=1,
        )
    )


def _write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
    path.write_text(text, encoding="utf-8")


def parse(text: str) -> dict[str, Any]:
    """The judge's reply as the labels asked for, or ValueError."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in output")
    parsed: dict[str, Any] = json.loads(text[start : end + 1])
    if parsed.get("grounding") not in GROUNDING:
        raise ValueError(f"bad grounding: {parsed.get('grounding')!r}")
    for name in ("on_question", "reads_on"):
        value = parsed.get(name)
        if isinstance(value, bool):  # tolerated: true/false for yes/no
            parsed[name] = "yes" if value else "no"
        elif value not in YES_NO:
            raise ValueError(f"bad {name}: {value!r}")
    if parsed.get("error") not in (None, *ERRORS):
        parsed["error"] = "other"
    return parsed


def judge(model: str, row: dict[str, Any], prefix: str, sentence: str) -> dict[str, Any]:
    """One label; re-asks (at most twice) only when the reply is not the JSON asked for."""
    user = USER.format(
        query=row["query"],
        provisions=provisions(row),
        prefix=prefix or NOTHING_YET,
        sentence=sentence,
        definitions=DEFINITIONS,
    )
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    out, latency = "", 0
    usage: dict[str, Any] = {}
    for attempt in range(1, 4):
        out, usage, latency = chat(messages, model=model)
        try:
            return {**parse(out), "attempts": attempt, "usage": usage, "latency_ns": latency}
        except ValueError:
            messages = [
                *messages[:2],
                {"role": "assistant", "content": out},
                {"role": "user", "content": "Reply with ONLY the JSON object asked for."},
            ]
    return {"grounding": None, "error": f"no JSON after 3 attempts: {out[:200]!r}", "usage": usage}


def run(
    model: str, items: Sequence[dict[str, Any]], by_id: dict[str, dict[str, Any]], out: Path
) -> None:
    """Judge items in a fixed shuffled order; resumable (items already judged are skipped)."""
    if model not in JUDGES:
        raise ValueError(f"not a named judge: {model}")
    order = list(items)
    random.Random(SEED + 1).shuffle(order)  # noqa: S311 - a reproducible order, not a secret
    done = set()
    if out.exists():
        done = {json.loads(x)["sha"] for x in out.read_text(encoding="utf-8").splitlines()}
    for n, item in enumerate(order, 1):
        if item["sha"] in done:
            continue
        label = judge(model, by_id[item["id"]], item["prefix"], item["sentence"])
        record = {
            "sha": item["sha"],
            "id": item["id"],
            "judge": model,
            "prompt_sha256": PROMPT_SHA,
            **label,
        }
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(
            f"{n}/{len(order)} {model} {item['id']}: {label.get('grounding')} "
            f"{label.get('on_question')} {label.get('reads_on')}",
            flush=True,
        )


def pilot_items(size: int) -> list[dict[str, Any]]:
    """Dev only: at each rollback point of the dev pilot traces, the first rejected draft and its
    first retry; a seeded sample of ``size`` items."""
    items: list[Item] = []
    for cell in PILOT_CELLS:
        for record in load(GRID / "dev" / f"{cell}.jsonl").values():
            sentences = (record.get("trace") or {}).get("sentences", [])
            for i, sentence in enumerate(sentences):
                if not sentence["rollbacks"]:
                    continue
                prefix = committed_text(record["answer"], [s["text"] for s in sentences[:i]])
                for attempt in sentence["attempts"][:2]:
                    text = (attempt["verdict"].get("text") or "").strip()
                    if text:
                        items.append(Item(record["id"], prefix.strip(), text, [{"cell": cell}]))
    unique = dedupe(items)
    sample = random.Random(SEED).sample(unique, min(size, len(unique)))  # noqa: S311
    return [
        {"id": i.id, "sha": i.sha, "prefix": i.prefix, "sentence": i.sentence, "sources": i.sources}
        for i in sample
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build")
    pilot = sub.add_parser("pilot")
    pilot.add_argument("--size", type=int, default=12)
    run_judge = sub.add_parser("judge")
    run_judge.add_argument("--model", choices=JUDGES, required=True)
    run_judge.add_argument("--set", choices=["core", "extended"], required=True)
    args = parser.parse_args()
    if args.command == "build":
        build()
    elif args.command == "pilot":
        OUT.mkdir(parents=True, exist_ok=True)
        items = pilot_items(args.size)
        _write_jsonl(OUT / "pilot.jsonl", items)
        by_id = {r["id"]: r for r in rows("dev")}
        for model in JUDGES:
            run(model, items, by_id, OUT / f"pilot-{model}.jsonl")
    else:
        items = [json.loads(x) for x in (OUT / f"{args.set}.jsonl").read_text().splitlines()]
        by_id = {r["id"]: r for r in rows("test")}
        run(args.model, items, by_id, OUT / f"judge-{args.model}-{args.set}.jsonl")


if __name__ == "__main__":
    main()
