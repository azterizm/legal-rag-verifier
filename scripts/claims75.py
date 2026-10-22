"""Stop 75 (docs/GRID.md § Stop 75): French figure formats in the claim check.

The regression gate: the claims of every English text in the batteries and the answers, read before
and after the change and compared as (kind, value, start, end); and the golden and negative pairs,
shared with the tests.

  uv run python scripts/claims75.py snapshot before   # on the 0.2.0 code
  uv run python scripts/claims75.py snapshot after    # on the new code
  uv run python scripts/claims75.py diff              # → results/claims75.json

The guard on the corpus: every text of ``data/uk`` read by the 0.2.0 code and by the new code.

  uv run python scripts/claims75.py corpus            # → results/claims75_corpus.json
  uv run python scripts/claims75.py corpus-report     # again, with results/claims75_grades.csv

The narrower rules (GRID § Stop 75: the narrower rules), checked the same way:

  uv run python scripts/claims75.py snapshot narrow   # on the narrowed code
  uv run python scripts/claims75.py diff --run 76     # → results/claims75_narrow.json
  uv run python scripts/claims75.py corpus --run 76   # → results/claims75_corpus76.json

And "an" before listed punctuation only: ``snapshot narrow2``, ``diff --run 77``,
``corpus --run 77``; "0," and three digits a decimal: ``narrow3``, ``--run 78``.

Snapshots (``results/raw/claims75/``, git-ignored) hold a hash of each text, never the text: the
premises quote statute text and the fresh and stop 71 answers stay local. The corpus diff there
holds excerpts and stays local too; the committed sample quotes short excerpts with coordinates.
"""

from __future__ import annotations

import argparse
import csv
import functools
import hashlib
import json
import random
import re
import subprocess
import sys
import types
from collections import Counter
from collections.abc import Callable, Iterator, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
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


def diff(run: Run) -> dict[str, Any]:
    out = compare(read_jsonl(RAW / "before.jsonl"), read_jsonl(RAW / f"{run.snapshot}.jsonl"))
    run.gate.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


# ---------------------------------------------------------------- the guard on the corpus
CORPUS_RAW = RAW / "corpus.jsonl"
CORPUS_REPORT = ROOT / "results/claims75_corpus.json"
GRADES = ROOT / "results/claims75_grades.csv"
# claims.py and numbers.py of v0.2.0; citations.py has not changed since.
OLD_BLOBS = {
    "numbers": "59d9a489e905fe94bcb93f59e4ff07fcbacd09fc",
    "claims": "91827b81d5d0257325ef0d71a2980f3585530094",
}
CORPUS_FIELDS = ("text", "text_after", "title", "crossheading", "long_title")
RULES = {
    "trailing currency": "cur",
    "French unit": "unit",
    "French date": "date",
    "space groups": "space",
    "decimal three places": "dec3",
    "decimal comma": "dec",
    "other": "other",
}
GRADE_NAMES = ("right", "wrong", "unclear")
SAMPLE = 40
SEED = 75
EXCERPT = 60  # characters kept each side of a changed claim in the local diff
SHORT = 40  # and in the committed sample


class Run(NamedTuple):
    """One check of a build against 0.2.0: its gate snapshot, its corpus diff, report and grades."""

    snapshot: str
    gate: Path
    raw: Path
    report: Path
    grades: Path
    seed: int


RUNS = {
    "75": Run("after", REPORT, CORPUS_RAW, CORPUS_REPORT, GRADES, SEED),
    "76": Run(
        "narrow",
        ROOT / "results/claims75_narrow.json",
        RAW / "corpus76.jsonl",
        ROOT / "results/claims75_corpus76.json",
        ROOT / "results/claims75_grades76.csv",
        76,
    ),
    "77": Run(
        "narrow2",
        ROOT / "results/claims75_narrow2.json",
        RAW / "corpus77.jsonl",
        ROOT / "results/claims75_corpus77.json",
        ROOT / "results/claims75_grades77.csv",
        77,
    ),
    "78": Run(
        "narrow3",
        ROOT / "results/claims75_narrow3.json",
        RAW / "corpus78.jsonl",
        ROOT / "results/claims75_corpus78.json",
        ROOT / "results/claims75_grades78.csv",
        78,
    ),
}

Reading = list[tuple[str, str, int, int]]

# Rule 1's form, overlapping: a digit, a comma, 1 or 2 digits and no further digit.
_RULE_1 = re.compile(r"(?=\d(,\d{1,2})(?!\d))")
_TRAILING = re.compile(r"\d\s?(?:[€£$]|EUR|USD|GBP)$")
_FRENCH_UNIT = re.compile(r"\b(?:heures?|jours?|semaines?|mois|années?|ans?)\b", re.IGNORECASE)
_FRENCH_DATE = re.compile(
    r"\b(?:janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|"
    r"d[ée]cembre)\b|\der\b",
    re.IGNORECASE,
)
_SPACE_GROUP = re.compile(r"\d[ \u00a0\u202f]\d")
_DECIMAL = re.compile(r"\d,\d{1,2}(?!\d)")
_DECIMAL_3 = re.compile(r"(?<![\d,])0,\d{3}(?!\d)")


@functools.cache
def old_extractor() -> Callable[[str], list[Any]]:
    """``extract_claims`` of 0.2.0, built from its git blobs."""

    def source(blob: str) -> str:
        return subprocess.run(  # noqa: S603
            ["git", "cat-file", "blob", blob],  # noqa: S607
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout

    numbers = types.ModuleType("claims75_numbers_020")
    sys.modules[numbers.__name__] = numbers
    exec(compile(source(OLD_BLOBS["numbers"]), "numbers.py@0.2.0", "exec"), numbers.__dict__)  # noqa: S102
    claims = types.ModuleType("claims75_claims_020")
    sys.modules[claims.__name__] = claims
    text = source(OLD_BLOBS["claims"])
    target = "from legal_rag_verifier.numbers import"
    if text.count(target) != 1:
        raise ValueError("unexpected imports in claims.py@0.2.0")
    text = text.replace(target, f"from {numbers.__name__} import")
    exec(compile(text, "claims.py@0.2.0", "exec"), claims.__dict__)  # noqa: S102
    extract: Callable[[str], list[Any]] = claims.extract_claims
    return extract


def reading(claims: Sequence[Any]) -> Reading:
    return [(c.kind.value, c.value, c.start, c.end) for c in claims]


def rule_of(kind: str, span: str) -> str:
    """The new rule that made a claim, read from the claim's own text; first match wins."""
    tests = (
        ("trailing currency", bool(_TRAILING.search(span))),
        ("French unit", kind == "DURATION" and bool(_FRENCH_UNIT.search(span))),
        ("French date", kind == "DATE" and bool(_FRENCH_DATE.search(span))),
        ("space groups", bool(_SPACE_GROUP.search(span))),
        ("decimal three places", bool(_DECIMAL_3.search(span))),
        ("decimal comma", bool(_DECIMAL.search(span))),
    )
    return next((rule for rule, hit in tests if hit), "other")


def guard_forms(text: str) -> Counter[str]:
    """Rule 1's forms by what follows the digits: the guard keeps the first three apart."""
    out: Counter[str] = Counter()
    for m in _RULE_1.finditer(text):
        after = text[m.end(1) :]
        if re.match(r",\d", after):
            out["comma and digit"] += 1
        elif after.startswith(("'", "’")):
            out["prime"] += 1
        elif re.match(r"[-‐]\s?[^\W\d_]", after):
            out["hyphen and letter"] += 1
        else:
            out["decimal"] += 1
    return out


def changed_record(
    record: Mapping[str, Any], field: str, text: str, before: Reading, after: Reading
) -> dict[str, Any]:
    old = set(before)
    added = [
        {
            "claim": list(c),
            "rule": rule_of(c[0], text[c[2] : c[3]]),
            "excerpt": [
                text[max(0, c[2] - EXCERPT) : c[2]],
                text[c[2] : c[3]],
                text[c[3] : c[3] + EXCERPT],
            ],
            "before": [list(b) for b in before if b[2] < c[3] and c[2] < b[3]],
        }
        for c in after
        if c not in old
    ]
    return {
        "coordinate": record.get("coordinate"),
        "field": field,
        "source_url": record.get("source_url"),
        "before": [list(b) for b in before],
        "after": [list(a) for a in after],
        "added": added,
    }


def compare_file(path: str) -> dict[str, Any]:
    """Both readings of every text in one instrument file; the texts whose claims differ."""
    old = old_extractor()
    texts = claims_before = claims_after = 0
    guard: Counter[str] = Counter()
    changed = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        for field in CORPUS_FIELDS:
            text = record.get(field)
            if not isinstance(text, str) or not text:
                continue
            texts += 1
            guard.update(guard_forms(text))
            before, after = reading(old(text)), reading(extract_claims(text))
            claims_before += len(before)
            claims_after += len(after)
            if before != after:
                changed.append(changed_record(record, field, text, before, after))
    return {
        "texts": texts,
        "claims_before": claims_before,
        "claims_after": claims_after,
        "guard": dict(guard),
        "changed": changed,
    }


def corpus(run: Run, workers: int) -> dict[str, Any]:
    files = sorted(str(p) for p in (ROOT / "data/uk").rglob("*.jsonl"))
    totals: Counter[str] = Counter()
    guard: Counter[str] = Counter()
    RAW.mkdir(parents=True, exist_ok=True)
    with run.raw.open("w", encoding="utf-8") as raw, ProcessPoolExecutor(workers) as pool:
        for result in pool.map(compare_file, files, chunksize=64):
            totals["files"] += 1
            for key in ("texts", "claims_before", "claims_after"):
                totals[key] += result[key]
            guard.update(result["guard"])
            for c in result["changed"]:
                raw.write(json.dumps(c, ensure_ascii=False) + "\n")
    counts = {"files": totals["files"], "texts": totals["texts"]}
    counts |= {"claims_before": totals["claims_before"], "claims_after": totals["claims_after"]}
    return corpus_report(run, counts | {"guard": dict(guard)})


def read_grades(path: Path = GRADES) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as f:
        rows = {r["id"]: r for r in csv.DictReader(f)}
    if bad := [i for i, r in rows.items() if r["grade"] not in GRADE_NAMES]:
        raise ValueError(f"unknown grades for {bad}")
    return rows


def sample_items(changed: Sequence[Mapping[str, Any]], seed: int = SEED) -> list[dict[str, Any]]:
    """Up to ``SAMPLE`` changed claims under each rule, drawn with ``seed``."""
    pools: dict[str, list[tuple[Mapping[str, Any], Mapping[str, Any]]]] = {r: [] for r in RULES}
    for record in changed:
        for added in record["added"]:
            pools[added["rule"]].append((record, added))
    rng = random.Random(seed)  # noqa: S311 - a seeded sample, not a secret
    items = []
    for rule, code in RULES.items():
        pool = pools[rule]
        picked = sorted(rng.sample(range(len(pool)), min(SAMPLE, len(pool))))
        for k, i in enumerate(picked, 1):
            record, added = pool[i]
            left, span, right = added["excerpt"]
            items.append(
                {
                    "id": f"{code}-{k:02d}",
                    "rule": rule,
                    "coordinate": record["coordinate"],
                    "source_url": record["source_url"],
                    "field": record["field"],
                    "new": added["claim"][:2],
                    "old": [b[:2] for b in added["before"]],
                    "excerpt": left[-SHORT:] + "[" + span + "]" + right[:SHORT],
                }
            )
    return items


def corpus_report(run: Run, counts: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Counts by rule, the graded sample and the grades' tally; rewrites the committed report."""
    if counts is None:
        counts = json.loads(run.report.read_text(encoding="utf-8"))["counts"]
    changed = read_jsonl(run.raw)
    by_rule: dict[str, dict[str, int]] = {r: {"claims": 0, "texts": 0} for r in RULES}
    for record in changed:
        rules = {a["rule"] for a in record["added"]}
        for added in record["added"]:
            by_rule[added["rule"]]["claims"] += 1
        for rule in rules:
            by_rule[rule]["texts"] += 1
    removed_only = sum(not r["added"] for r in changed)
    grades = read_grades(run.grades)
    items = sample_items(changed, run.seed)
    tally: dict[str, Counter[str]] = {r: Counter() for r in RULES}
    for item in items:
        graded = grades.get(item["id"])
        item["grade"] = graded["grade"] if graded else None
        item["note"] = graded["note"] if graded else ""
        if graded:
            tally[item["rule"]][graded["grade"]] += 1
    out = {
        "counts": dict(counts),
        "changed_texts": len(changed),
        "removed_only": removed_only,
        "by_rule": by_rule,
        "graded": {r: dict(t) for r, t in tally.items() if t},
        "sample": items,
    }
    run.report.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["snapshot", "diff", "corpus", "corpus-report"])
    names = ["before", "after", "narrow", "narrow2", "narrow3"]
    parser.add_argument("name", nargs="?", choices=names)
    parser.add_argument("--run", choices=sorted(RUNS), default="75")
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()
    run = RUNS[args.run]
    if args.command == "snapshot":
        if args.name is None:
            parser.error("snapshot needs a name: before, after or narrow, narrow2, narrow3")
        print(snapshot(args.name))
    elif args.command == "diff":
        out = diff(run)
        print(json.dumps({"sets": out["sets"], "changed_texts": out["changed_texts"]}, indent=1))
    else:
        out = corpus(run, args.workers) if args.command == "corpus" else corpus_report(run)
        keys = ("counts", "changed_texts", "removed_only", "by_rule", "graded")
        print(json.dumps({k: out[k] for k in keys}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
