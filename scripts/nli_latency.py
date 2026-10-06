"""NLI latency on this machine: p50/p99 per model and device, one pair and a full premise batch.

Usage: uv run --extra nli python scripts/nli_latency.py [--n 200] [--models ...] [--devices ...]
Timing is device-synchronised wall time around tokenisation + forward pass + softmax, in-process
(vault 04 §5). The premise is ERA 1996 s.124 as in force (tests/fixtures), 9 candidates per
sentence (6 windows, 1 fact, 2 joined cross-references).
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from legal_rag_verifier.index import build_index  # noqa: E402
from legal_rag_verifier.nli import SentenceNLIVerifier  # noqa: E402
from legal_rag_verifier.premise import Premise  # noqa: E402
from legal_rag_verifier.verifier import Verifier, _nli_candidates  # noqa: E402
from tests.conftest import S124_FACTS, SI_2026_310, load_fixture  # noqa: E402

SENTENCES = [
    "The compensatory award is capped at the lower of £123,543 and 52 weeks' pay.",
    "The limit may be exceeded so the award reflects the amount payable under section 114(2)(a).",
    "The limit does not apply where the dismissal is automatically unfair under section 100.",
    "The tribunal takes into account any payment already made by the respondent.",
    "The position is as follows:",
    "An employee can always recover their full losses whatever their salary.",
    "Before applying the cap, the tribunal deducts any reduction required by law.",
    "This limit applies to compensatory awards for unfair dismissal.",
]


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, round(q * (len(ordered) - 1))))
    return ordered[k]


def chip() -> str:
    try:
        out = subprocess.run(
            ["/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return platform.processor()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=200)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument(
        "--models",
        nargs="+",
        default=["cross-encoder/nli-deberta-v3-small", "cross-encoder/nli-deberta-v3-base"],
    )
    parser.add_argument("--devices", nargs="+", default=["mps", "cpu"])
    args = parser.parse_args()

    import torch  # noqa: PLC0415

    premise = Premise.from_records(
        load_fixture("era1996_s124.jsonl"), facts=S124_FACTS, extra_titles=[SI_2026_310]
    )
    candidates = [text for text, _, _ in _nli_candidates(build_index(premise))]
    rows = []
    for model in args.models:
        for device in args.devices:
            scorer = SentenceNLIVerifier(model, device)
            verifier = Verifier(scorer)
            for label, premises in (
                ("1 pair", candidates[1:2]),
                (f"{len(candidates)} pairs", candidates),
            ):
                for i in range(args.warmup):
                    scorer.timed_score(premises, SENTENCES[i % len(SENTENCES)])
                times = [
                    scorer.timed_score(premises, SENTENCES[i % len(SENTENCES)])[1] / 1e6
                    for i in range(args.n)
                ]
                rows.append(
                    {
                        "model": scorer.model_id,
                        "device": device,
                        "batch": label,
                        "n": args.n,
                        "p50_ms": round(statistics.median(times), 2),
                        "p99_ms": round(percentile(times, 0.99), 2),
                        "max_ms": round(max(times), 2),
                    }
                )
                print(json.dumps(rows[-1]))
            # whole check_sentence (claim check + NLI) on the full premise
            totals = []
            for i in range(args.n):
                verdict = verifier.check_sentence(premise, SENTENCES[i % len(SENTENCES)])
                totals.append((verdict.claim_latency_ns + verdict.nli_latency_ns) / 1e6)
            rows.append(
                {
                    "model": scorer.model_id,
                    "device": device,
                    "batch": "check_sentence",
                    "n": args.n,
                    "p50_ms": round(statistics.median(totals), 2),
                    "p99_ms": round(percentile(totals, 0.99), 2),
                    "max_ms": round(max(totals), 2),
                }
            )
            print(json.dumps(rows[-1]))
            del scorer, verifier
            if device == "mps":
                torch.mps.empty_cache()
    meta = {
        "machine": chip(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "torch": torch.__version__,
        "transformers": __import__("transformers").__version__,
    }
    out = ROOT / "results" / "nli_latency.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"meta": meta, "rows": rows}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
