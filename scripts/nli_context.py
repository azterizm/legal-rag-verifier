"""Stop 40: the question in the entailment check, offline (docs/GRID.md § Stop 40).

Re-runs the auditor on sentences already labelled (stop 37 Part A, your grades; stop 36 core, Claude
Opus 5.5's labels) with four inputs to the entailment model. Only that input changes: the claim
check, thresholds and engine are as run. The model is wrapped, not edited.

- V0: the sentence alone against each chunk (as run);
- V1: ``Question: {query}\\nAnswer: {sentence}`` as the hypothesis;
- V2: as V1 with the previous sentence of the answer before the sentence;
- V3: ``Question: {query}\\n`` in front of every chunk.

  uv run --extra nli python scripts/nli_context.py     # → results/nli_context/
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "batteries/verifier"))

import grid_prompts  # type: ignore[import-not-found]  # noqa: E402
import software_battery  # type: ignore[import-not-found]  # noqa: E402
from replay_states import load, shared_states  # type: ignore[import-not-found]  # noqa: E402

from legal_rag_verifier.nli import SentenceNLIVerifier  # noqa: E402
from legal_rag_verifier.premise import Premise  # noqa: E402
from legal_rag_verifier.segmenter import split_sentences  # noqa: E402
from legal_rag_verifier.verifier import NLIProbs, Verifier  # noqa: E402

OUT = ROOT / "results/nli_context"
VARIANTS = ("V0", "V1", "V2", "V3")
NLI_REASONS = {"NLI_CONTRADICTION", "NLI_NOT_ENTAILED", "NEUTRAL_STRICT"}
HALVE = 0.5  # reading set before scoring (GRID § Stop 40)
KEEP = 0.9


class ContextNLI(SentenceNLIVerifier):
    """The run's NLI head with the question (and previous sentence) added per variant."""

    variant = "V0"
    question = ""
    previous = ""

    def chunks(self, premise: str) -> tuple[str, ...]:
        pieces = super().chunks(premise)
        if self.variant == "V3":
            return tuple(f"Question: {self.question}\n{p}" for p in pieces)
        return pieces

    def score(self, premises: Sequence[str], hypothesis: str) -> list[NLIProbs]:
        if self.variant == "V1":
            hypothesis = f"Question: {self.question}\nAnswer: {hypothesis}"
        elif self.variant == "V2":
            answer = f"{self.previous} {hypothesis}".strip()
            hypothesis = f"Question: {self.question}\nAnswer: {answer}"
        return super().score(premises, hypothesis)


def previous_sentence(prefix: str) -> str:
    sentences = split_sentences(prefix)
    return sentences[-1].text if sentences else ""


def software_items() -> list[dict[str, Any]]:
    """Stop 37 Part A texts with your grades."""
    a = load(ROOT / "results/software/4B.jsonl")
    b = load(ROOT / "results/software/4B-inject-v2.jsonl")
    states = {s.id: s for s in shared_states(a, b)[0]}
    review = ROOT / "results/software/review"
    key = json.loads((review / "key.json").read_text(encoding="utf-8"))
    with (review / "grades.csv").open(encoding="utf-8") as f:
        grades = {r["item"]: r for r in csv.DictReader(f)}
    sheet = (review / "sheet.md").read_text(encoding="utf-8")
    by_id = {r["id"]: r for r in software_battery.rows()}
    items = []
    for k in key:
        if k["part"] != "A" or not k["item"]:
            continue
        marker = f"**{k['item']}.** "
        text = sheet.split(marker, 1)[1].split("\n", 1)[0].strip()
        items.append(
            {
                "set": "software",
                "item": k["item"],
                "id": k["id"],
                "query": by_id[k["id"]]["query"],
                "prefix": states[k["id"]].committed.strip(),
                "sentence": text,
                "recorded": k["sources"][0]["verdict"],
                "wrong": grades[k["item"]]["correct"] == "no",
                "right": grades[k["item"]]["correct"] == "yes",
            }
        )
    return items


def statute_items() -> list[dict[str, Any]]:
    """Stop 36 core texts with Claude Opus 5.5's labels."""
    review = ROOT / "results/grid/rollback"
    key = json.loads((review / "key.json").read_text(encoding="utf-8"))["items"]
    core = {
        json.loads(x)["item"]: json.loads(x)
        for x in (review / "core.jsonl").read_text(encoding="utf-8").splitlines()
    }
    with (review / "labels.csv").open(encoding="utf-8") as f:
        labels = {r["item"]: r for r in csv.DictReader(f)}
    by_id = {r["id"]: r for r in grid_prompts.rows("test")}
    return [
        {
            "set": "statutes",
            "item": k["item"],
            "id": k["id"],
            "query": by_id[k["id"]]["query"],
            "prefix": core[k["item"]]["prefix"],
            "sentence": core[k["item"]]["sentence"],
            "recorded": k["sources"][0]["verdict"],
            "wrong": labels[k["item"]]["grounding"] in ("unsupported", "contradicted"),
            "right": labels[k["item"]]["grounding"] == "supported",
        }
        for k in key
    ]


def run(items: Sequence[dict[str, Any]], premises: dict[str, Premise]) -> list[dict[str, Any]]:
    nli = ContextNLI("cross-encoder/nli-deberta-v3-base")
    verifier = Verifier(nli)
    out = []
    for n, item in enumerate(items, 1):
        nli.question = item["query"]
        nli.previous = previous_sentence(item["prefix"])
        verdicts = {}
        for variant in VARIANTS:
            nli.variant = variant
            v = verifier.check_sentence(premises[item["id"]], item["sentence"], query=item["query"])
            verdicts[variant] = {"verdict": v.verdict.name, "reasons": [r.name for r in v.reasons]}
        out.append({**item, "verdicts": verdicts})
        if n % 25 == 0:
            print(f"{item['set']}: {n}/{len(items)}", flush=True)
    return out


def summarise(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for variant in VARIANTS:
        rolled = [r for r in records if r["verdicts"][variant]["verdict"] != "EMIT"]
        nli = [r for r in rolled if set(r["verdicts"][variant]["reasons"]) <= NLI_REASONS]
        out[variant] = {
            "texts": len(records),
            "right": sum(r["right"] for r in records),
            "wrong": sum(r["wrong"] for r in records),
            "false_rollbacks": sum(r["right"] for r in rolled),
            "caught": sum(r["wrong"] for r in rolled),
            "false_rollbacks_by_nli": sum(r["right"] for r in nli),
            "caught_by_nli": sum(r["wrong"] for r in nli),
            "rollbacks_other": sum(not r["right"] and not r["wrong"] for r in rolled),
        }
    recorded = [r for r in records if r["recorded"] in ("EMIT", "ROLLBACK")]
    out["V0_reproduces_recorded"] = {
        "same": sum(
            (r["verdicts"]["V0"]["verdict"] == "EMIT") == (r["recorded"] == "EMIT")
            for r in recorded
        ),
        "of": len(recorded),
        "verdicts": dict(Counter(r["recorded"] for r in records)),
    }
    base = out["V0"]
    for variant in VARIANTS[1:]:
        v = out[variant]
        v["worth_a_fresh_test_on_this_set"] = (
            v["false_rollbacks"] <= HALVE * base["false_rollbacks"]
            and v["caught"] >= KEEP * base["caught"]
        )
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {}
    for name, items in (("software", software_items()), ("statutes", statute_items())):
        module = software_battery if name == "software" else grid_prompts
        rows = module.rows() if name == "software" else module.rows("test")
        ids = {i["id"] for i in items}
        premises: dict[str, Premise] = {r["id"]: module.premise(r) for r in rows if r["id"] in ids}
        records = run(items, premises)
        (OUT / f"{name}.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8"
        )
        report[name] = summarise(records)
    for variant in VARIANTS[1:]:
        report[f"{variant}_worth_a_fresh_test"] = all(
            report[s][variant]["worth_a_fresh_test_on_this_set"] for s in ("software", "statutes")
        )
    (OUT / "report.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
