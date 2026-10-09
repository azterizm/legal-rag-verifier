"""Stop 41: the auditor with derived facts, scored on the software battery (docs/GRID.md § Stop 41).

Arms (the entailment model and thresholds unchanged):
- V0: today's auditor;
- S: each kept fact added to its passage as an enrichment element (an extra entailment candidate);
- S-claims (diagnostic): as S, and each fact also a FACT passage, so the claim check sees it.

Levels: Part A, the 34 graded sentences of stop 37; Part B, the 40 plain answers (4D's first
draft), each split into sentences, every sentence audited. The audit runs on Modal
(``scripts/modal_normalise.py``) and never sees a grade; scoring here reads the committed output.

  uv run python scripts/nli_normalised.py      # results/normalise/audit.jsonl → report.json
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from legal_rag_verifier.premise import Passage, PassageKind, Premise  # noqa: E402
from legal_rag_verifier.segmenter import split_sentences  # noqa: E402

OUT = ROOT / "results/normalise"
ARMS = ("V0", "S", "S-claims")
NLI_MODEL = "cross-encoder/nli-deberta-v3-base"


def premise_for(arm: str, passages: Sequence[Mapping[str, str]], facts: Sequence[Any]) -> Premise:
    """The premise of one source under ``arm`` (``facts``: kept facts, 1-based ``passage``)."""
    by_passage = {
        n: tuple(dict.fromkeys(f["fact"] for f in facts if f["passage"] == n))
        for n in range(1, len(passages) + 1)
    }
    windows = tuple(
        Passage(
            p["text"],
            heading=p["heading"],
            elements=by_passage[n] if arm != "V0" else (),
        )
        for n, p in enumerate(passages, 1)
    )
    if arm == "S-claims":
        windows += tuple(Passage(f["fact"], kind=PassageKind.FACT) for f in facts)
    return Premise(windows)


# ---------------------------------------------------------------------- the audit (Modal)


def audit(
    items: Sequence[Mapping[str, Any]],
    sources: Mapping[str, Sequence[Mapping[str, str]]],
    facts: Mapping[str, Sequence[Any]],
) -> list[dict[str, Any]]:
    """Every item under every arm; logs each entailment candidate's scores. No grades in."""
    from legal_rag_verifier.nli import SentenceNLIVerifier  # noqa: PLC0415
    from legal_rag_verifier.verifier import NLIProbs, Verifier  # noqa: PLC0415

    class Logged(SentenceNLIVerifier):
        calls: list[list[tuple[str, NLIProbs]]]

        def score(self, premises: Sequence[str], hypothesis: str) -> list[NLIProbs]:
            probs = super().score(premises, hypothesis)
            self.calls.append(list(zip(premises, probs, strict=True)))
            return probs

    nli = Logged(NLI_MODEL)
    verifier = Verifier(nli)
    premises = {
        (arm, i): premise_for(arm, sources[i], facts.get(i, ())) for arm in ARMS for i in sources
    }
    out = []
    for n, item in enumerate(items, 1):
        verdicts = {}
        for arm in ARMS:
            nli.calls = []
            v = verifier.check_sentence(
                premises[arm, item["id"]], item["sentence"], query=item["query"]
            )
            verdicts[arm] = {
                "verdict": v.verdict.name,
                "reasons": [r.name for r in v.reasons],
                "aligned": list(v.aligned),
                "nli_ms": v.nli_latency_ns / 1e6,
                "candidates": [
                    [text, round(p.entailment, 4), round(p.neutral, 4), round(p.contradiction, 4)]
                    for call in nli.calls
                    for text, p in call
                ],
            }
        out.append({"key": item["key"], "verdicts": verdicts, "nli_model": nli.model_id})
        if n % 25 == 0:
            print(f"{n}/{len(items)}", flush=True)
    return out


# ---------------------------------------------------------------------- inputs (laptop)


def _grades() -> tuple[list[dict[str, Any]], dict[str, dict[str, str]]]:
    review = ROOT / "results/software/review"
    key = json.loads((review / "key.json").read_text(encoding="utf-8"))
    with (review / "grades.csv").open(encoding="utf-8") as f:
        return key, {r["item"]: r for r in csv.DictReader(f)}


def part_a() -> list[dict[str, Any]]:
    """Stop 37 Part A: the 34 graded sentences (as stop 40 read them)."""
    from nli_context import software_items  # type: ignore[import-not-found]  # noqa: PLC0415

    return [
        {
            "key": f"A:{i['item']}",
            "level": "A",
            "item": i["item"],
            "id": i["id"],
            "query": i["query"],
            "sentence": i["sentence"],
            "recorded": i["recorded"],
            "right": i["right"],
            "wrong": i["wrong"],
        }
        for i in software_items()
    ]


def part_b() -> list[dict[str, Any]]:
    """Stop 37 Part B: each plain answer (4D's first draft) split into sentences."""
    from software_battery import rows  # type: ignore[import-not-found]  # noqa: PLC0415

    key, grades = _grades()
    queries = {r["id"]: r["query"] for r in rows()}
    path = ROOT / "results/software/4D.jsonl"
    plain = {
        r["id"]: r["attempts"][0]["text"].strip()
        for r in (json.loads(x) for x in path.read_text(encoding="utf-8").splitlines())
    }
    items = []
    for k in key:
        if k["part"] != "B" or not any(s["arm"] == "plain" for s in k["sources"]):
            continue
        grade = grades[k["item"]]["correct"]
        for n, s in enumerate(split_sentences(plain[k["id"]])):
            items.append(
                {
                    "key": f"B:{k['item']}:{n}",
                    "level": "B",
                    "item": k["item"],
                    "id": k["id"],
                    "query": queries[k["id"]],
                    "sentence": s.text,
                    "right": grade == "yes",
                    "wrong": grade == "no",
                }
            )
    return items


def inputs() -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Items (with grades), sources and kept facts, for both levels."""
    import normalise_sources  # type: ignore[import-not-found]  # noqa: PLC0415

    items = part_a() + part_b()
    sources = normalise_sources.software_sources()
    lines = (OUT / "facts.jsonl").read_text(encoding="utf-8").splitlines()
    facts = {r["source"]: r["facts"] for r in map(json.loads, lines)}
    return items, sources, facts


def blind(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """What the audit is sent: no grade, no recorded verdict."""
    return [{k: i[k] for k in ("key", "id", "query", "sentence")} for i in items]


def assert_prompts_clean(items: Sequence[Mapping[str, Any]]) -> int:
    """No question, answer or graded sentence appears in any cached prompt."""
    texts = {i["query"] for i in items} | {i["sentence"] for i in items}
    prompts = [
        json.loads(p.read_text(encoding="utf-8"))["prompt"]
        for p in (OUT / "gemini-3.8-flash-high").glob("sw_*.json")
    ]
    leaks = [t for t in texts if len(t) > 20 and any(t in p for p in prompts)]  # noqa: PLR2004
    if leaks:
        raise RuntimeError(f"a question or answer is in a prompt: {leaks[:3]}")
    return len(prompts)


# ---------------------------------------------------------------------- scoring (laptop)


def _rolled(r: Mapping[str, Any], arm: str) -> bool:
    return bool(r["verdicts"][arm]["verdict"] != "EMIT")


def _by_nli(r: Mapping[str, Any], arm: str) -> bool:
    from nli_context import NLI_REASONS  # noqa: PLC0415

    return set(r["verdicts"][arm]["reasons"]) <= set(NLI_REASONS)


def best(r: Mapping[str, Any], arm: str, facts: set[str]) -> dict[str, Any] | None:
    """The best entailing candidate, and whether it is a derived fact."""
    candidates = r["verdicts"][arm]["candidates"]
    if not candidates:
        return None
    text, e, _, _ = max(candidates, key=lambda c: c[1])
    return {"text": text, "entailment": e, "fact": any(text.endswith(f) for f in facts)}


def answers(records: Sequence[Mapping[str, Any]], arm: str) -> list[dict[str, Any]]:
    """Part B per answer: rolled back when any sentence is."""
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for r in records:
        grouped.setdefault(r["item"], []).append(r)
    return [
        {
            "item": item,
            "right": rs[0]["right"],
            "wrong": rs[0]["wrong"],
            "rolled": any(_rolled(r, arm) for r in rs),
            "by_nli": all(_by_nli(r, arm) for r in rs if _rolled(r, arm)),
        }
        for item, rs in grouped.items()
    ]


def counts(units: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rolled = [u for u in units if u["rolled"]]
    right, wrong = sum(u["right"] for u in units), sum(u["wrong"] for u in units)
    false_rollbacks, caught = sum(u["right"] for u in rolled), sum(u["wrong"] for u in rolled)
    return {
        "texts": len(units),
        "right": right,
        "wrong": wrong,
        "false_rollbacks": false_rollbacks,
        "caught": caught,
        "false_rollbacks_by_nli": sum(u["right"] for u in rolled if u["by_nli"]),
        "caught_by_nli": sum(u["wrong"] for u in rolled if u["by_nli"]),
        "accuracy": round((right - false_rollbacks + caught) / max(right + wrong, 1), 3),
    }


def level(records: Sequence[Mapping[str, Any]], name: str) -> dict[str, Any]:
    from nli_context import HALVE, KEEP  # noqa: PLC0415

    out: dict[str, Any] = {}
    for arm in ARMS:
        if name == "A":
            units = [{**r, "rolled": _rolled(r, arm), "by_nli": _by_nli(r, arm)} for r in records]
        else:
            units = answers(records, arm)
        out[arm] = counts(units)
    # Comparison rows: the claim check alone (V0's rollbacks not by entailment), no auditor.
    if name == "A":
        claim_only = [{**r, "rolled": _rolled(r, "V0") and not _by_nli(r, "V0")} for r in records]
    else:
        claim_only = [
            {**u, "rolled": u["rolled"] and not u["by_nli"]} for u in answers(records, "V0")
        ]
    out["claim check only"] = counts([{**u, "by_nli": False} for u in claim_only])
    out["no auditor"] = counts([{**u, "rolled": False, "by_nli": False} for u in claim_only])
    base = out["V0"]
    for arm in ARMS[1:]:
        out[arm]["passes_bar"] = (
            out[arm]["false_rollbacks"] <= HALVE * base["false_rollbacks"]
            and out[arm]["caught"] >= KEEP * base["caught"]
        )
    return out


def report() -> dict[str, Any]:
    items, _, facts = inputs()
    prompts = assert_prompts_clean(items)
    by_key = {i["key"]: i for i in items}
    lines = (OUT / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    records = [{**by_key[r["key"]], **r} for r in map(json.loads, lines)]
    fact_texts = {f["fact"] for fs in facts.values() for f in fs}
    check = json.loads((OUT / "check.json").read_text(encoding="utf-8"))
    a = [r for r in records if r["level"] == "A"]
    b = [r for r in records if r["level"] == "B"]
    out: dict[str, Any] = {
        "prompts_checked_clean": prompts,
        "facts": check,
        "nli_model": records[0]["nli_model"] if records else None,
        "A": level(a, "A"),
        "B": level(b, "B"),
    }
    out["V0_reproduces_recorded_A"] = {
        "same": sum(_rolled(r, "V0") == (r["recorded"] != "EMIT") for r in a),
        "of": len(a),
        "differ": [r["item"] for r in a if _rolled(r, "V0") != (r["recorded"] != "EMIT")],
    }
    for arm in ARMS[1:]:
        out[f"R1_{arm}_viable"] = out["A"][arm]["passes_bar"] and out["B"][arm]["passes_bar"]
    # R2: wrong texts that pass with a derived fact as the best entailing candidate.
    out["R2"] = {
        arm: [
            {"key": r["key"], "sentence": r["sentence"], "best": best(r, arm, fact_texts)}
            for r in records
            if r["wrong"] and not _rolled(r, arm) and (best(r, arm, fact_texts) or {}).get("fact")
        ]
        for arm in ARMS[1:]
    }
    # R3: false rollbacks left in S, by cause.
    r3: Counter[str] = Counter()
    for r in a + [r for r in b if r["right"]]:
        if not r["right"] or not _rolled(r, "S"):
            continue
        if not _by_nli(r, "S"):
            r3["claim check"] += 1
            continue
        aligned = r["verdicts"]["S"]["aligned"]
        passage = aligned[0] + 1 if aligned else 0
        has_fact = any(f["passage"] == passage for f in facts.get(r["id"], []))
        r3["fact present, entailment failed" if has_fact else "no fact (coverage gap)"] += 1
    out["R3_S_false_rollback_sentences"] = dict(r3)
    out["nli_ms_per_sentence"] = {
        arm: round(sum(r["verdicts"][arm]["nli_ms"] for r in records) / len(records), 1)
        for arm in ARMS
    }
    return out


def main() -> None:
    out = report()
    (OUT / "report.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in out.items() if not k.startswith("R2")}, indent=1))


if __name__ == "__main__":
    main()
