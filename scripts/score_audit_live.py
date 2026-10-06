"""Score the verifier on anonymised live answers from legal-rag-audit (post-hoc, cells 4A/4D style).

Input: ``external/audit_live/answers.jsonl`` (git-ignored; systems anonymised as "System A/B"; one
row per answer with the audit's own per-answer outcome). Nothing is run on the audit side.

Premises: a point-in-time answer is checked against the dated version of the anchor provision in
force on the date asked (``anchor:<id>@<as_at>``); era-124 has no dated text here and is skipped. A
fictional-instrument answer is checked against an empty premise: by construction there is no source,
so any figure it offers is ungrounded (the audit's claim-shape rule, applied by the claim check).

Signals per answer: ``flagged`` = a sentence carrying a figure of the asked kind is rolled back;
``sentences_rolled_back`` = all rolled-back sentences (noise on real prose).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.run_battery import MODELS, CachingScorer  # noqa: E402

sys.path.insert(0, str(ROOT / "batteries/verifier"))
import premises  # noqa: E402

from legal_rag_verifier.claims import ClaimKind  # noqa: E402
from legal_rag_verifier.premise import Premise  # noqa: E402
from legal_rag_verifier.verifier import NLIScorer, Verdict, Verifier  # noqa: E402

AS_AT = {
    "pit-era-227-1": "era-227@2014-06-01",
    "pit-era-227-2": "era-227@2020-06-01",
    "pit-era-186-1": "era-186@2014-01-01",
    "pit-era-186-2": "era-186@2019-01-01",
    "pit-ca-382-1": "ca-382@2014-01-01",
    "pit-ca-382-2": "ca-382@2019-01-01",
    "pit-ca-465-1": "ca-465@2014-01-01",
    "pit-ca-465-2": "ca-465@2019-01-01",
}
SHAPE = {"figure": ClaimKind.MONEY, "percentage": ClaimKind.PERCENT}
FICT_SHAPE = {
    "fict-ravensbourne-1": "figure",
    "fict-ravensbourne-2": "percentage",
    "fict-blackmere-1": "figure",
    "fict-blackmere-2": "percentage",
    "fict-thornfield-1": "figure",
    "fict-thornfield-2": "figure",
    "fict-marchwood-1": "percentage",
    "fict-marchwood-2": "figure",
    "fict-harrowgate-1": "figure",
    "fict-harrowgate-2": "percentage",
}


def _figures(probe: str) -> tuple[str, str]:
    """(in-force figure, superseded figure) for a point-in-time probe, from anchors.toml."""
    anchor_id, _, as_at = AS_AT[probe].partition("@")
    versions = premises.anchors()[anchor_id]["versions"]
    own = next(v["figure"] for v in versions if v["as_at"] == as_at)
    other = next(v["figure"] for v in versions if v["as_at"] != as_at)
    return own.replace(" million", ""), other.replace(" million", "")


def judge(
    row: dict[str, Any], verifier: Verifier, enrichment: Path | None, mode: str
) -> dict[str, Any] | None:
    probe = row["probe_id"]
    core: dict[str, Any] = {}
    if probe in AS_AT:
        anchor_id, _, as_at = AS_AT[probe].partition("@")
        spec = f"anchor:{anchor_id}@{'timeline' if mode == 'timeline' else as_at}"
        premise, _ = premises.build({"premise_spec": spec}, ROOT / "data", enrichment)
        kind = ClaimKind.MONEY
    elif probe in FICT_SHAPE:
        premise, kind = Premise(()), SHAPE[FICT_SHAPE[probe]]
    else:
        return None  # era-124 (no dated text) and anything else
    verdicts = verifier.check_text(premise, row["answer"], query=row["query"])
    if probe in AS_AT:
        own, other = _figures(probe)
        own_sents = [v for v in verdicts if own in v.text and other not in v.text]
        other_sents = [v for v in verdicts if other in v.text]
        core = {
            "in_force_sentences": len(own_sents),
            "in_force_sentences_emitted": sum(v.emitted for v in own_sents),
            "superseded_sentences": len(other_sents),
            "superseded_sentences_flagged": sum(not v.emitted for v in other_sents),
        }
    figure_rolled = [
        v
        for v in verdicts
        if v.verdict is Verdict.ROLLBACK and any(c.claim.kind is kind for c in v.claims)
    ]
    return {
        "system": row["system"],
        "probe_id": probe,
        "pass_index": row["pass_index"],
        "audit_check": row["audit_check"],
        "audit_status": row["audit_status"],
        "audit_outcome": row["audit_outcome"],
        "flagged": bool(figure_rolled),
        "sentences": len(verdicts),
        "sentences_rolled_back": sum(v.verdict is Verdict.ROLLBACK for v in verdicts),
        "reasons": sorted({r.value for v in figure_rolled for r in v.reasons}),
        **core,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nli", choices=["none", *MODELS], default="none")
    parser.add_argument(
        "--enrichment", type=Path, default=ROOT / "enrichment/gemini-3.8-flash-high"
    )
    parser.add_argument("--premise", choices=["version", "timeline"], default="version")
    args = parser.parse_args()
    rows = [
        json.loads(line)
        for line in (ROOT / "external/audit_live/answers.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    scorer: NLIScorer | None = None
    if args.nli != "none":
        from legal_rag_verifier.nli import SentenceNLIVerifier  # noqa: PLC0415

        scorer = CachingScorer(SentenceNLIVerifier(MODELS[args.nli]))
    verifier = Verifier(scorer)
    judged = [
        j for r in rows if (j := judge(r, verifier, args.enrichment, args.premise)) is not None
    ]
    table: Counter[tuple[str, str, str, bool]] = Counter(
        (j["system"], j["audit_check"], j["audit_status"], j["flagged"]) for j in judged
    )
    noise = [
        j["sentences_rolled_back"] / j["sentences"]
        for j in judged
        if j["audit_status"] == "PASS" and j["sentences"]
    ]
    pit = [j for j in judged if "in_force_sentences" in j]
    core = {
        key: sum(j[key] for j in pit)
        for key in (
            "in_force_sentences",
            "in_force_sentences_emitted",
            "superseded_sentences",
            "superseded_sentences_flagged",
        )
    }
    summary = {
        "detector": args.nli,
        "premise": args.premise,
        "point_in_time_core_sentences": core,
        "answers_scored": len(judged),
        "answers_skipped": len(rows) - len(judged),
        "agreement": {
            f"{s} {c} audit={a} verifier={'flag' if f else 'pass'}": n
            for (s, c, a, f), n in sorted(table.items())
        },
        "pass_answers_mean_share_of_sentences_rolled_back": round(sum(noise) / len(noise), 4)
        if noise
        else None,
        "per_answer": judged,
    }
    print(json.dumps(summary, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
