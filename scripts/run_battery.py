"""Score the verifier on a detector battery (plan R1). Run only on a reviewed battery.

Usage:
  uv run python scripts/run_battery.py batteries/verifier/dev.jsonl --nli small|base|none
      [--entail 0.70 --contradict 0.40 --align-ratio 0.5 --neutral connective|strict]
      [--sweep]   # dev split only: grid over thresholds, NLI scores cached per pair

Headline: false-rollback rate on grounded paraphrases (and connective prose), beside recall per
failure class. Raw per-row verdicts go to results/raw/ (git-ignored); the summary prints as JSON.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sys
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "batteries/verifier"))

import premises  # noqa: E402

from legal_rag_verifier.premise import Premise  # noqa: E402
from legal_rag_verifier.verifier import NLIProbs, NLIScorer, Verifier, VerifierConfig  # noqa: E402

PASS_CLASSES = frozenset({"grounded_paraphrase", "connective", "premise_correction"})
MODELS = {
    "small": "cross-encoder/nli-deberta-v3-small",
    "base": "cross-encoder/nli-deberta-v3-base",
}


@dataclass(frozen=True)
class Outcome:
    row_id: str
    cls: str
    expected: str
    verdict: str
    reasons: tuple[str, ...]


def summarise(outcomes: Iterable[Outcome]) -> dict[str, Any]:
    """Per-class rates: false rollbacks for pass classes, recall for failure classes."""
    by_class: dict[str, list[Outcome]] = {}
    for o in outcomes:
        by_class.setdefault(o.cls, []).append(o)
    classes: dict[str, Any] = {}
    for cls, rows in sorted(by_class.items()):
        rolled = sum(o.verdict == "ROLLBACK" for o in rows)
        metric = "false_rollback_rate" if cls in PASS_CLASSES else "recall"
        classes[cls] = {"n": len(rows), "rolled_back": rolled, metric: round(rolled / len(rows), 4)}
    passes = [o for c in PASS_CLASSES for o in by_class.get(c, [])]
    failures = [o for c, rows in by_class.items() if c not in PASS_CLASSES for o in rows]
    caught = sum(o.verdict == "ROLLBACK" for o in failures)
    false = sum(o.verdict == "ROLLBACK" for o in passes)
    return {
        "classes": classes,
        "headline": {
            "grounded_paraphrase_false_rollback_rate": classes.get("grounded_paraphrase", {}).get(
                "false_rollback_rate"
            ),
            "pass_false_rollback_rate": round(false / len(passes), 4) if passes else None,
            "failure_recall": round(caught / len(failures), 4) if failures else None,
            "rollback_precision": round(caught / (caught + false), 4) if caught + false else None,
        },
    }


class CachingScorer:
    """Memoises NLI scores per (premise text, hypothesis) so a threshold sweep costs one pass."""

    def __init__(self, inner: NLIScorer) -> None:
        self.inner = inner
        self.model_id = inner.model_id
        self._cache: dict[tuple[str, str], NLIProbs] = {}

    def score(self, premises: Sequence[str], hypothesis: str) -> list[NLIProbs]:
        missing = [p for p in premises if (p, hypothesis) not in self._cache]
        if missing:
            for p, probs in zip(missing, self.inner.score(missing, hypothesis), strict=True):
                self._cache[(p, hypothesis)] = probs
        return [self._cache[(p, hypothesis)] for p in premises]


def load_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def premises_for(
    rows: Sequence[dict[str, Any]], data_root: Path, enrichment: Path | None = None
) -> dict[str, Premise]:
    return {premises.premise_key(r): premises.build(r, data_root, enrichment)[0] for r in rows}


def run(
    rows: Sequence[dict[str, Any]], built: dict[str, Premise], verifier: Verifier
) -> tuple[list[Outcome], list[dict[str, Any]]]:
    outcomes: list[Outcome] = []
    raw: list[dict[str, Any]] = []
    for row in rows:
        verdict = verifier.check_sentence(
            built[premises.premise_key(row)], row["sentence"], query=row["query"]
        )
        outcomes.append(
            Outcome(
                row["id"],
                row["class"],
                row["expected"],
                verdict.verdict.value,
                tuple(r.value for r in verdict.reasons),
            )
        )
        raw.append({"id": row["id"], **verdict.to_dict()})
    return outcomes, raw


def _check_sealed(battery: Path, detector: str) -> None:
    """A held-out battery runs only if a seal matches it, and once per detector (plan R1)."""
    digest = hashlib.sha256(battery.read_bytes()).hexdigest()
    seals = sorted((ROOT / "batteries/verifier/seals").glob("*.json"))
    match = [
        p for p in seals if json.loads(p.read_text(encoding="utf-8"))["battery"]["sha256"] == digest
    ]
    if not match:
        raise SystemExit("held-out battery is not sealed (batteries/verifier/seal.py)")
    done = ROOT / "results" / f"{match[0].stem}-{detector}.done"
    if done.exists():
        raise SystemExit(f"{match[0].stem} has already run with {detector} ({done})")
    done.parent.mkdir(exist_ok=True)
    done.write_text(datetime.now(UTC).isoformat(timespec="seconds") + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("battery", type=Path)
    parser.add_argument("--nli", choices=["none", *MODELS], default="none")
    parser.add_argument("--device", default=None)
    parser.add_argument("--entail", type=float, default=0.70)
    parser.add_argument("--contradict", type=float, default=0.40)
    parser.add_argument("--align-ratio", type=float, default=0.5)
    parser.add_argument("--neutral", choices=["connective", "strict"], default="connective")
    parser.add_argument("--sweep", action="store_true")
    parser.add_argument("--enrichment", type=Path, default=None, help="enrichment layer dir")
    parser.add_argument("--neutral-grounded", choices=["emit", "rollback"], default="emit")
    parser.add_argument("--tag", default="", help="suffix for the raw output file")
    args = parser.parse_args()

    rows = load_rows(args.battery)
    if any(r.get("split") == "heldout" for r in rows):
        if args.sweep:
            raise SystemExit("no threshold sweep on a held-out battery")
        _check_sealed(args.battery, args.nli)
    if args.sweep and any(r.get("split") != "dev" for r in rows):
        raise SystemExit("--sweep calibrates thresholds: dev split only (plan R1)")
    built = premises_for(rows, ROOT / "data", args.enrichment)
    scorer: NLIScorer | None = None
    if args.nli != "none":
        from legal_rag_verifier.nli import SentenceNLIVerifier  # noqa: PLC0415

        scorer = CachingScorer(SentenceNLIVerifier(MODELS[args.nli], args.device))

    neutral: Literal["connective", "strict"] = args.neutral
    configs = [
        VerifierConfig(
            args.entail, args.contradict, neutral, 2, args.align_ratio, args.neutral_grounded
        )
    ]
    if args.sweep:
        policies: list[Literal["connective", "strict"]] = ["connective", "strict"]
        configs = [
            VerifierConfig(e, c, n, 2, a, args.neutral_grounded)
            for e, c, n, a in itertools.product(
                [0.5, 0.6, 0.7, 0.8, 0.9],
                [0.3, 0.4, 0.5, 0.6, 0.7],
                policies,
                [0.3, 0.5, 0.7],
            )
        ]
    results = []
    for config in configs:
        t0 = time.perf_counter()
        outcomes, raw = run(rows, built, Verifier(scorer, config))
        summary = summarise(outcomes)
        summary["config"] = config.to_dict()
        summary["nli"] = scorer.model_id if scorer else None
        summary["enrichment"] = next(iter(built.values())).enrichment if built else None
        summary["seconds"] = round(time.perf_counter() - t0, 2)
        results.append(summary)
        if not args.sweep:
            out = ROOT / "results/raw" / f"{args.battery.stem}-{args.nli}{args.tag}.jsonl"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("".join(json.dumps(r) + "\n" for r in raw), encoding="utf-8")
    print(json.dumps(results if args.sweep else results[0], indent=2))


if __name__ == "__main__":
    main()
