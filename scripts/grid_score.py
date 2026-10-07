"""Score the 2x2 grid (rule A, fixed before the run; docs/GRID.md) and summarise each cell.

  uv run python scripts/grid_score.py                 # results/grid/summary.json
  uv run python scripts/grid_score.py --sample        # blind review sheet, 20 answers per cell
  uv run python scripts/grid_score.py --labels FILE   # agreement of rule A with your labels

Rule A, per final answer (claim check only, no NLI, against the prompt's own premise):
  answerable prompt: PASS iff (1) it cites a gold provision (that section, or a part of it),
    (2) no figure, date, citation or Act name in it is ungrounded, (3) it has no refusal sentence;
  abstention prompt (route EPISTEMIC_ABSTENTION_*): PASS iff it abstains (says the provisions do
    not answer, or is the refusal sentence) and (2) holds.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import statistics
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "batteries/verifier"))

from grid_prompts import premise, rows  # type: ignore[import-not-found]  # noqa: E402

from legal_rag_verifier.citations import coordinate_tail, is_relative  # noqa: E402
from legal_rag_verifier.claims import ClaimKind, extract_claims  # noqa: E402
from legal_rag_verifier.engine import DEFAULT_REFUSAL, render_premise  # noqa: E402
from legal_rag_verifier.verifier import Reason, Verifier  # noqa: E402

GRID = ROOT / "results/grid"
CELLS = ("4A", "4B", "4C", "4D")
UNGROUNDED = {
    Reason.UNGROUNDED_FIGURE,
    Reason.UNGROUNDED_CITATION,
    Reason.UNGROUNDED_INSTRUMENT,
}
ABSTAINS = re.compile(
    r"\b(?:do(?:es)?\s+not|don't|doesn't|cannot|can't|is\s+not|are\s+not|no)\s+"
    r"(?:\w+\s+){0,4}?(?:answer|address|say|state|specify|mention|cover|contain|provide|include|"
    r"exist|find|information|reference|provision)",
    re.IGNORECASE,
)
SAMPLE_PER_CELL = 20
SEED = 20261006


def cites_gold(answer: str, gold: list[str]) -> bool:
    tails = [coordinate_tail(g) for g in gold]
    cited = [
        c.value
        for c in extract_claims(answer)
        if c.kind is ClaimKind.CITATION and not is_relative(c.value)
    ]
    return any(v == t or v.startswith(t + "/") for v in cited for t in tails)


def rule_a(row: dict[str, Any], answer: str, checker: Verifier) -> dict[str, Any]:
    verdicts = checker.check_text(premise(row), answer, query=row["query"]) if answer else []
    ungrounded = sorted(
        {r.claim.text for v in verdicts for r in v.claims if r.reason in UNGROUNDED}
    )
    refused = DEFAULT_REFUSAL in answer
    abstained = refused or bool(ABSTAINS.search(answer)) or not answer.strip()
    if row["expects_abstention"]:
        passed = abstained and not ungrounded
        cited = None
    else:
        cited = cites_gold(answer, row["premise"])
        passed = cited and not ungrounded and not refused
    return {
        "pass": passed,
        "cites_gold": cited,
        "ungrounded": ungrounded,
        "refused": refused,
        "abstained": abstained,
    }


def load(cell: str) -> dict[str, dict[str, Any]]:
    path = GRID / f"{cell}.jsonl"
    if not path.exists():
        return {}
    return {
        r["id"]: r for r in (json.loads(x) for x in path.read_text(encoding="utf-8").splitlines())
    }


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 2) if values else None


def visible(record: dict[str, Any]) -> tuple[int, float]:
    """Answer tokens without the API's reasoning ("thinking") tokens, and the discarded share of
    them (pro rata; Qwen has no thinking, so both equal the raw figures)."""
    usages = [a.get("usage") or {} for a in record.get("attempts", [])]
    details = [u.get("completion_tokens_details") or {} for u in usages]
    thinking = sum(d.get("reasoning_tokens", 0) for d in details)
    out = record["tokens_out"] - thinking
    share = out / record["tokens_out"] if record["tokens_out"] else 1.0
    return out, record["tokens_discarded"] * share


def summarise(cell: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(records)
    seen = [visible(r) for r in records]
    first_pass = sum(r["retries"] == 0 and r["refusals"] == 0 and r["resolved"] for r in records)
    remediated = sum(r["resolved"] for r in records) - first_pass
    histogram: dict[int, int] = {}
    for r in records:
        histogram[r["retries"]] = histogram.get(r["retries"], 0) + 1
    return {
        "cell": cell,
        "answers": n,
        "rule_a_pass": sum(r["score"]["pass"] for r in records),
        "rule_a_pass_rate": round(sum(r["score"]["pass"] for r in records) / n, 4) if n else None,
        "first_pass_clean": first_pass,
        "resolved_after_remediation": remediated,
        "unresolved": n - first_pass - remediated,
        "retries_histogram": dict(sorted(histogram.items())),
        "refusals": sum(r["refusals"] for r in records),
        "tokens_out_median": _median([r["tokens_out"] for r in records]),
        "tokens_discarded_mean": round(statistics.mean(r["tokens_discarded"] for r in records), 1)
        if n
        else None,
        "visible_tokens_out_median": _median([float(v) for v, _ in seen]),
        "visible_tokens_discarded_mean": round(statistics.mean(d for _, d in seen), 1)
        if n
        else None,
        "visible_tok_s_median": _median(
            [
                v / (r["generation_ns"] / 1e9)
                for (v, _), r in zip(seen, records, strict=True)
                if r["generation_ns"]
            ]
        ),
        "wall_s_median": _median([r["wall_ns"] / 1e9 for r in records]),
        "time_to_first_output_s_median": _median(
            [r["time_to_first_output_ns"] / 1e9 for r in records if r["time_to_first_output_ns"]]
        ),
        "generation_s_median": _median([r["generation_ns"] / 1e9 for r in records]),
        "verify_s_median": _median([r["verify_ns"] / 1e9 for r in records]),
        "decode_tok_s_median": _median([r["decode_tok_s"] for r in records if r["decode_tok_s"]]),
        "calls_median": _median([r["calls"] for r in records]),
    }


def sample(scored: dict[str, list[dict[str, Any]]], by_id: dict[str, dict[str, Any]]) -> None:
    """A blind sheet: 20 answers per cell, shuffled together, cells hidden; key kept apart."""
    rng = random.Random(SEED)  # noqa: S311 - a reproducible sample, not a secret
    items = []
    for cell in CELLS:
        records = scored.get(cell, [])
        items += [(cell, r) for r in rng.sample(records, min(SAMPLE_PER_CELL, len(records)))]
    rng.shuffle(items)
    sheet = [
        "# Grid review sheet (blind)\n",
        "Label each item in review_labels.csv: correct or incorrect, per the provisions.\n",
    ]
    key, labels = [], [["item", "label", "note"]]
    for n, (cell, r) in enumerate(items, 1):
        row = by_id[r["id"]]
        sheet += [
            f"\n## Item {n}\n",
            f"**Query:** {row['query']}\n",
            f"**Expected:** {'abstention' if row['expects_abstention'] else 'answer'}\n",
            f"<details><summary>Provisions</summary>\n\n{render_premise(premise(row))}\n</details>\n",
            f"**Answer:**\n\n> {r['answer'] or '(empty)'}\n",
        ]
        key.append({"item": n, "cell": cell, "id": r["id"], "rule_a": r["score"]["pass"]})
        labels.append([str(n), "", ""])
    (GRID / "review_sheet.md").write_text("".join(sheet), encoding="utf-8")
    (GRID / "review_key.json").write_text(json.dumps(key, indent=1) + "\n", encoding="utf-8")
    with (GRID / "review_labels.csv").open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(labels)
    print(f"{len(items)} items → results/grid/review_sheet.md (label review_labels.csv)")


def agreement(path: Path) -> dict[str, Any]:
    key = {k["item"]: k for k in json.loads((GRID / "review_key.json").read_text())}
    with path.open(encoding="utf-8") as f:
        labels = {int(r["item"]): r["label"].strip().lower() for r in csv.DictReader(f)}
    out: dict[str, Any] = {}
    for cell in CELLS:
        pairs = [
            (labels[i] == "correct", k["rule_a"])
            for i, k in key.items()
            if k["cell"] == cell and labels.get(i) in {"correct", "incorrect"}
        ]
        out[cell] = {
            "labelled": len(pairs),
            "human_correct": sum(h for h, _ in pairs),
            "rule_a_pass": sum(a for _, a in pairs),
            "agreement": round(sum(h == a for h, a in pairs) / len(pairs), 4) if pairs else None,
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", action="store_true")
    parser.add_argument("--labels", type=Path, default=None)
    args = parser.parse_args()
    if args.labels:
        print(json.dumps(agreement(args.labels), indent=1))
        return
    by_id = {r["id"]: r for r in rows()}
    checker = Verifier()  # claim check only: rule A does not use the NLI head
    scored: dict[str, list[dict[str, Any]]] = {}
    for cell in CELLS:
        records = list(load(cell).values())
        for r in records:
            r["score"] = rule_a(by_id[r["id"]], r["answer"], checker)
        scored[cell] = records
    summary = {cell: summarise(cell, rs) for cell, rs in scored.items() if rs}
    (GRID / "summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=1))
    if args.sample:
        sample(scored, by_id)


if __name__ == "__main__":
    main()
