"""Stop 41: derived facts for the entailment check (docs/GRID.md § Stop 41).

A strong model reads each source once, at ingestion, and writes the facts that follow from it:
defaults applied, definitions substituted, references between passages joined, unit equivalences
stated, arithmetic done. Code then checks every fact (``check_fact``) and drops any that fails.
The approach is the teacher precompute of blind-counsel (ephemeral-dynamic-llms) and
blind-adapters; no dependency on either and no code taken from them.

  uv run python scripts/normalise_sources.py --pilot      # 3 statute dev provisions, not scored
  uv run python scripts/normalise_sources.py              # the 40 software sources

One call per source to ``gemini-3.8-flash-high`` through the user's local router (the client of
``enrich_premises.py``). Only documentation text is sent: no question, answer or label. Replies are
cached under ``results/normalise/<model>/`` keyed by the source's sha256, so no source is paid for
twice.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from enrich_premises import ask_with  # type: ignore[import-not-found]  # noqa: E402

from legal_rag_verifier.claims import ClaimKind, extract_claims  # noqa: E402
from legal_rag_verifier.enrichment import normalise  # noqa: E402
from legal_rag_verifier.numbers import (  # noqa: E402
    NUMBER_WORDS_RE,
    canonical_decimal,
    parse_number_words,
)

MODEL = "gemini-3.8-flash-high"
OUT = ROOT / "results/normalise"
CACHE = OUT / MODEL
MIN_QUOTE = 8  # as enrichment._MIN_QUOTE

SYSTEM = (
    "You are a senior engineer writing a reference manual. Use ONLY the documentation you are "
    "given. Reply with a single JSON object."
)
USER = """Documentation, as numbered passages:

{source}

Go through the passages one by one. For each passage, write every fact that follows from it as a
standalone plain sentence that names what it applies to (never "it" or "this parameter" alone).
Write the facts a careful reader would work out, not only what the text says word for word:
- defaults applied: when a result depends on a parameter that has a default, state the result at
  the default;
- definitions substituted: when a term is defined, state the facts with the definition in place;
- references joined: when a passage refers to something stated in another passage, state the
  combined fact;
- unit equivalences: state a quantity in the other units a reader may use;
- arithmetic done: state the result of any calculation the text implies.
Also restate each rule, condition, exception and default the passage states directly.

Return JSON: {{"facts": [{{"fact": the sentence, "passage": the number of the passage it follows
from, "quotes": [short phrases copied EXACTLY from the documentation that support it],
"calc": an arithmetic expression using only numbers that appear in the quotes and + - * / ( ),
whose result is a number in the fact, or "" when there is no calculation}}]}}
Every number, date and version in a fact must appear in one of its quotes or be the result of
its calc."""
PROMPT_SHA = hashlib.sha256((SYSTEM + USER).encode()).hexdigest()

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


# ---------------------------------------------------------------------- the check


def numbers(text: str) -> set[str]:
    """Every number in ``text``, digits or words, canonical (``1,024`` → 1024, ``zero`` → 0)."""
    words = (parse_number_words(m.group()) for m in re.finditer(NUMBER_WORDS_RE, text, re.I))
    return {_canonical(m) for m in _NUMBER.findall(text)} | {str(w) for w in words if w is not None}


def _canonical(number: str) -> str:
    return canonical_decimal(Decimal(number.replace(",", "")))


def evaluate(calc: str, allowed: set[str]) -> str:
    """The value of ``calc``: numbers from ``allowed`` and + - * / ( ) only (no eval)."""

    def walk(node: ast.AST) -> Fraction:  # noqa: PLR0911
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            text = _canonical(str(node.value))
            if text not in allowed:
                raise ValueError(f"number {text} is not in the quotes")
            return Fraction(text)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -walk(node.operand)
        if isinstance(node, ast.BinOp):
            left, right = walk(node.left), walk(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
        raise ValueError(f"not allowed in calc: {ast.dump(node)[:60]}")

    value = walk(ast.parse(calc.replace(",", ""), mode="eval"))
    if value.denominator == 1:
        return str(value.numerator)
    return canonical_decimal(round(Decimal(value.numerator) / Decimal(value.denominator), 6))


def check_fact(fact: Mapping[str, Any], passages: Sequence[str]) -> str | None:  # noqa: PLR0911
    """Why ``fact`` is dropped, or None when it passes. ``passages`` are the source's passages.

    1. ``passage`` names a passage; every quote is verbatim in the source, at least 8 characters
       (after ``enrichment.normalise``).
    2. Every figure, date and citation in the fact is in its quotes or equals ``calc``.
    3. ``calc`` uses only numbers from the quotes and + - * / ( ).
    """
    text, quotes, calc = fact.get("fact"), fact.get("quotes"), fact.get("calc") or ""
    if not isinstance(text, str) or not text.strip() or not isinstance(calc, str):
        return "shape"
    if not isinstance(quotes, list) or not quotes or not all(isinstance(q, str) for q in quotes):
        return "shape"
    if not isinstance(fact.get("passage"), int) or not 1 <= fact["passage"] <= len(passages):
        return "passage"
    source = normalise("\n".join(passages))
    if any(len(normalise(q)) < MIN_QUOTE or normalise(q) not in source for q in quotes):
        return "quote"
    joined = " ".join(quotes)
    allowed = numbers(joined)
    result = ""
    if calc.strip():
        try:
            result = evaluate(calc, allowed)
        except (ValueError, SyntaxError, ZeroDivisionError):
            return "calc"
    quoted = {(c.kind, c.value) for c in extract_claims(joined)}
    for claim in extract_claims(text):
        if (claim.kind, claim.value) in quoted:
            continue
        if claim.kind in (ClaimKind.CITATION, ClaimKind.INSTRUMENT, ClaimKind.DATE):
            return "figure"
        value = claim.value.split(":", 1)[-1] if claim.kind is ClaimKind.MONEY else claim.value
        value = value.split(":", 1)[0]
        if value != result and not (claim.kind is ClaimKind.NUMBER and value in allowed):
            return "figure"
    return None


# ---------------------------------------------------------------------- sources and calls


def render(passages: Sequence[Mapping[str, str]]) -> str:
    return "\n\n".join(
        f"[{n}] {p['heading']}\n<<<\n{p['text']}\n>>>" for n, p in enumerate(passages, 1)
    )


def flat(passages: Sequence[Mapping[str, str]]) -> list[str]:
    """Each passage as the check sees it: heading and text."""
    return [f"{p['heading']}\n{p['text']}" for p in passages]


def software_sources() -> dict[str, list[dict[str, str]]]:
    from software_battery import rows  # type: ignore[import-not-found]  # noqa: PLC0415

    return {
        r["id"]: [{"heading": p["heading"], "text": p["text"]} for p in r["passages"]]
        for r in rows()
    }


def pilot_sources() -> dict[str, list[dict[str, str]]]:
    """Three statute dev provisions (the first three enrichment units of the dev battery)."""
    sys.path.insert(0, str(ROOT / "batteries/verifier"))
    import premises  # noqa: PLC0415
    from enrich_premises import units  # noqa: PLC0415

    battery = ROOT / "batteries/verifier/dev.jsonl"
    found: dict[str, list[dict[str, str]]] = {}
    for line in battery.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if not row.get("premise") and not row.get("premise_spec"):
            continue
        premise, _ = premises.build(row, ROOT / "data")
        for key, unit in sorted(units(premise).items()):
            found.setdefault(
                f"pilot-{key}", [{"heading": unit["heading"], "text": t} for t in unit["texts"]]
            )
        if len(found) >= 3:  # noqa: PLR2004
            break
    return dict(list(found.items())[:3])


def normalise_source(name: str, passages: list[dict[str, str]]) -> dict[str, Any]:
    source = render(passages)
    sha = hashlib.sha256(source.encode()).hexdigest()
    path = CACHE / (re.sub(r"[^A-Za-z0-9]+", "_", name) + ".json")
    if path.exists():
        cached: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        if cached["source_sha256"] == sha and cached["prompt_sha256"] == PROMPT_SHA:
            return cached
    user = USER.format(source=source)
    raw, attempts = ask_with(SYSTEM, user)
    entry = {
        "source": name,
        "source_sha256": sha,
        "model": MODEL,
        "prompt_sha256": PROMPT_SHA,
        "attempts": attempts,
        "prompt": user,
        "raw": raw,
    }
    path.write_text(json.dumps(entry, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return entry


def checked(entry: Mapping[str, Any], passages: list[dict[str, str]]) -> dict[str, Any]:
    proposed = [f for f in (entry["raw"].get("facts") or []) if isinstance(f, Mapping)]
    reasons = [check_fact(f, flat(passages)) for f in proposed]
    kept = [
        {"fact": f["fact"].strip(), "passage": f["passage"], "quotes": f["quotes"],
         "calc": f.get("calc") or ""}
        for f, why in zip(proposed, reasons, strict=True)
        if why is None
    ]  # fmt: skip
    return {
        "source": entry["source"],
        "facts": kept,
        "proposed": len(proposed),
        "kept": len(kept),
        "dropped": dict(Counter(r for r in reasons if r)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", action="store_true", help="3 statute dev provisions only")
    args = parser.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    sources = pilot_sources() if args.pilot else software_sources()
    records = []
    for name, passages in sources.items():
        record = checked(normalise_source(name, passages), passages)
        records.append(record)
        print(f"{name}: kept {record['kept']}/{record['proposed']} {record['dropped']}", flush=True)
    totals = {
        "prompt_sha256": PROMPT_SHA,
        "sources": len(records),
        "proposed": sum(r["proposed"] for r in records),
        "kept": sum(r["kept"] for r in records),
        "dropped": dict(sum((Counter(r["dropped"]) for r in records), Counter())),
    }
    tag = "pilot-" if args.pilot else ""
    (OUT / f"{tag}facts.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8"
    )
    (OUT / f"{tag}check.json").write_text(json.dumps(totals, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(totals))


if __name__ == "__main__":
    main()
