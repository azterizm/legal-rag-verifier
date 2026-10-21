"""Stop 75 (docs/GRID.md § Stop 75): French figure formats in the claim check.

The regression gate: the claims of every English text in the batteries and the answers, read before
and after the change and compared as (kind, value, start, end); and the golden and negative pairs,
shared with the tests.

  uv run python scripts/claims75.py snapshot before   # on the 0.2.0 code
  uv run python scripts/claims75.py snapshot after    # on the new code
  uv run python scripts/claims75.py diff              # → results/claims75.json

Snapshots (``results/raw/claims75/``, git-ignored) hold a hash of each text, never the text: the
premises quote statute text and the fresh and stop 71 answers stay local.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "batteries/verifier"))

from legal_rag_verifier.claims import extract_claims  # noqa: E402
from legal_rag_verifier.premise import Premise  # noqa: E402
from legal_rag_verifier.segmenter import split_sentences  # noqa: E402
from legal_rag_verifier.verifier import Verifier  # noqa: E402

RAW = ROOT / "results/raw/claims75"
REPORT = ROOT / "results/claims75.json"
# The gate's sets and their tier: 1 as planned, 2 added by your choice (stop 71's frontier answers).
TIERS = {"dev": 1, "heldout": 1, "fresh": 1, "fresh2": 1, "software": 1, "sota71": 2}
DETECTOR = {"dev": "dev.jsonl", "heldout": "heldout_draft.jsonl"}
SOFTWARE_CELLS = ("4B", "4D", "4B-inject-v2")
SOTA71 = ("flash", "opus46", "flash_opus46", "opus46_flash")


class Pair(NamedTuple):
    """A French-format listing as the source, an English sentence as the answer."""

    id: str
    listing: str
    answer: str
    verdict: str
    reason: str


class Text(NamedTuple):
    set: str
    id: str
    field: str
    text: str


_MONEY = ("€279.99", "279,99 €", "279.99 euros", "279,99 EUR")
_SPACES = {"space": " ", "nbsp": " ", "nnbsp": " "}
_SAME = (
    ("hours", "Autonomie : 30 heures.", "The battery lasts 30 hours."),
    ("date", "Livré le 5 novembre 2026.", "It arrives on 5 November 2026."),
    ("first", "Disponible le 1er mars 2026.", "It is available on 1 March 2026."),
    ("years", "Garantie 2 ans.", "It has a 2-year warranty."),
    ("working-days", "Livraison sous 3 à 5 jours ouvrés.", "Delivery takes 3 to 5 working days."),
    ("weight", "Poids : 1,2 kg.", "It weighs 1.2 kg."),
)
_WRONG = (
    ("price-wrong", "Prix : 279,99 €.", "It costs €289.99."),
    ("hours-wrong", "Autonomie : 30 heures.", "The battery lasts 40 hours."),
    ("date-wrong", "Livré le 5 novembre 2026.", "It arrives on 6 November 2026."),
)
PAIRS = (
    *(
        Pair(f"money-{i}{j}", f"Prix : {a}.", f"It costs {b}.", "EMIT", "GROUNDED")
        for i, a in enumerate(_MONEY)
        for j, b in enumerate(_MONEY)
    ),
    *(
        Pair(f"spaced-{name}", f"Prix : 1{sp}299,99 €.", "It costs €1,299.99.", "EMIT", "GROUNDED")
        for name, sp in _SPACES.items()
    ),
    *(
        Pair(
            f"spaced-{name}-answer",
            "Price: €1,299.99.",
            f"It costs 1{sp}299,99 €.",
            "EMIT",
            "GROUNDED",
        )
        for name, sp in _SPACES.items()
    ),
    *(Pair(i, listing, answer, "EMIT", "GROUNDED") for i, listing, answer in _SAME),
    *(Pair(i, listing, answer, "ROLLBACK", "UNGROUNDED_FIGURE") for i, listing, answer in _WRONG),
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def latest(path: Path, field: str = "text") -> dict[str, dict[str, Any]]:
    """Answer records by key, the last one kept, as the stop scripts read them."""
    return {r["key"]: r for r in read_jsonl(path) if r.get(field) is not None}


def premise_texts(premise: Premise) -> Iterator[tuple[str, str]]:
    """Every text of a premise the claim check reads: passages, headings, list items, elements."""
    for i, p in enumerate(premise.passages):
        yield f"passage{i}", p.text
        if p.heading:
            yield f"passage{i}.heading", p.heading
        for j, limb in enumerate(p.limbs):
            yield f"passage{i}.limb{j}", limb
        for j, element in enumerate(p.elements):
            yield f"passage{i}.element{j}", element


def answer_texts(name: str, key: str, answer: str) -> Iterator[Text]:
    for i, s in enumerate(split_sentences(answer)):
        yield Text(name, key, f"sentence{i}", s.text)


def detector(name: str) -> Iterator[Text]:
    import premises  # noqa: PLC0415
    from grid_prompts import ENRICHMENT  # type: ignore[import-not-found]  # noqa: PLC0415

    for row in read_jsonl(ROOT / "batteries/verifier" / DETECTOR[name]):
        for field in ("sentence", "query", "excerpt"):
            if row.get(field):
                yield Text(name, row["id"], field, row[field])
        built, _ = premises.build(row, ROOT / "data", ENRICHMENT)
        for field, text in premise_texts(built):
            yield Text(name, row["id"], f"premise.{field}", text)


def fresh(name: str) -> Iterator[Text]:
    import fresh_battery as fb  # type: ignore[import-not-found]  # noqa: PLC0415

    for file, domain in (("software", "software"), ("statutes", "legal")):
        for row in read_jsonl(ROOT / "batteries" / name / f"{file}.jsonl"):
            row = {**row, "domain": domain}  # noqa: PLW2901
            yield Text(name, row["id"], "query", row["query"])
            for field, text in premise_texts(fb.premise(row)):
                yield Text(name, row["id"], f"premise.{field}", text)
    for key, r in latest(ROOT / "results" / name / "answers.jsonl").items():
        yield from answer_texts(name, key, r["text"])


def software() -> Iterator[Text]:
    import software_battery as sb  # type: ignore[import-not-found]  # noqa: PLC0415

    for row in sb.rows():
        yield Text("software", row["id"], "query", row["query"])
        for field, text in premise_texts(sb.premise(row)):
            yield Text("software", row["id"], f"premise.{field}", text)
    for cell in SOFTWARE_CELLS:
        for r in read_jsonl(ROOT / "results/software" / f"{cell}.jsonl"):
            yield from answer_texts("software", f"{cell}:{r['id']}", r["answer"])


def sota71() -> Iterator[Text]:
    for name in SOTA71:
        for key, r in latest(ROOT / "results/sota71" / f"{name}.jsonl").items():
            yield from answer_texts("sota71", f"{name}:{key}", r["text"])


def texts() -> Iterator[Text]:
    """The gate's inventory, set by set (needs ``data/``, ``anchors_xml/``, the local answers)."""
    for name in DETECTOR:
        yield from detector(name)
    for name in ("fresh", "fresh2"):
        yield from fresh(name)
    yield from software()
    yield from sota71()


def claim_list(text: str) -> list[list[Any]]:
    return [[c.kind.value, c.value, c.start, c.end] for c in extract_claims(text)]


def pair_record(pair: Pair) -> dict[str, Any]:
    verdict = Verifier().check_sentence(Premise.from_text(pair.listing), pair.answer)
    return {
        "set": "pairs",
        "id": pair.id,
        "verdict": verdict.verdict.name,
        "reasons": sorted(r.name for r in verdict.reasons),
        "listing": [c[:2] for c in claim_list(pair.listing)],
        "answer": [c[:2] for c in claim_list(pair.answer)],
    }


def snapshot(name: str) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    out = RAW / f"{name}.jsonl"
    seen: set[tuple[str, str, str]] = set()
    with out.open("w", encoding="utf-8") as f:
        for t in texts():
            key = (t.set, t.id, t.field)
            if key in seen:
                raise ValueError(f"duplicate text key {key}")
            seen.add(key)
            record = {
                "set": t.set,
                "id": t.id,
                "field": t.field,
                "sha": hashlib.sha256(t.text.encode()).hexdigest(),
                "claims": claim_list(t.text),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        for pair in PAIRS:
            f.write(json.dumps(pair_record(pair), ensure_ascii=False) + "\n")
    return out


def compare(
    before: Sequence[Mapping[str, Any]], after: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Counts per set, every text whose claims changed, and the pairs before and after."""

    def by_key(records: Sequence[Mapping[str, Any]]) -> dict[tuple[str, ...], Mapping[str, Any]]:
        return {(r["set"], r["id"], r["field"]): r for r in records if r["set"] != "pairs"}

    old, new = by_key(before), by_key(after)
    if old.keys() != new.keys():
        raise ValueError("the snapshots hold different texts")
    if moved := [k for k in old if old[k]["sha"] != new[k]["sha"]]:
        raise ValueError(f"{len(moved)} texts differ between snapshots, first {moved[0]}")
    sets: dict[str, dict[str, int]] = {}
    changed = []
    for key, b in old.items():
        a = new[key]
        row = sets.setdefault(
            key[0],
            {"tier": TIERS.get(key[0], 0), "texts": 0, "claims_before": 0, "claims_after": 0},
        )
        row["texts"] += 1
        row["claims_before"] += len(b["claims"])
        row["claims_after"] += len(a["claims"])
        if b["claims"] != a["claims"]:
            row["changed"] = row.get("changed", 0) + 1
            changed.append(
                {
                    "set": key[0],
                    "id": key[1],
                    "field": key[2],
                    "before": b["claims"],
                    "after": a["claims"],
                }
            )
    for row in sets.values():
        row.setdefault("changed", 0)
    pairs_before = {r["id"]: r for r in before if r["set"] == "pairs"}
    pairs_after = {r["id"]: r for r in after if r["set"] == "pairs"}
    pairs = [
        {
            "id": p.id,
            "expected": [p.verdict, p.reason],
            "before": _pair_view(pairs_before.get(p.id)),
            "after": _pair_view(pairs_after.get(p.id)),
        }
        for p in PAIRS
    ]
    return {
        "sets": sets,
        "changed_texts": len(changed),
        "changed": changed,
        "pairs": pairs,
    }


def _pair_view(record: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if record is None:
        return None
    return {k: record[k] for k in ("verdict", "reasons", "listing", "answer")}


def diff() -> dict[str, Any]:
    out = compare(read_jsonl(RAW / "before.jsonl"), read_jsonl(RAW / "after.jsonl"))
    REPORT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["snapshot", "diff"])
    parser.add_argument("name", nargs="?", choices=["before", "after"])
    args = parser.parse_args()
    if args.command == "snapshot":
        if args.name is None:
            parser.error("snapshot needs a name: before or after")
        print(snapshot(args.name))
    else:
        out = diff()
        print(json.dumps({"sets": out["sets"], "changed_texts": out["changed_texts"]}, indent=1))


if __name__ == "__main__":
    main()
