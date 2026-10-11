"""Stop 57: Opus 5.5 grades a fresh sheet as the hand grader did (docs/GRID.md § Stop 57).

One call per question: the rule of the sheet, the question, the source and both answers lettered
as on the sheet. No hand grade is in any prompt. Each reply is appended as it returns; a rerun
asks only the questions not done, and the model stops cleanly at its ledger stop.

  FRESH_SET=fresh2     uv run python scripts/fresh_grader.py grade   # then: check
  FRESH_SET=fresh2     uv run python scripts/fresh_grader.py check   # against your grades
  FRESH_SET=fresh2-q27 uv run python scripts/fresh_grader.py grade   # then: fill
  FRESH_SET=fresh2-q27 uv run python scripts/fresh_grader.py fill    # → grades.csv, noted as Opus
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import auditor_judge as aj  # type: ignore[import-not-found]  # noqa: E402
import fresh_battery as fb  # type: ignore[import-not-found]  # noqa: E402

GRADES = ("yes", "no", "unsure")
AGREE = 0.95  # GRID § Stop 57: below this Opus is not used as the grader
OPUS_STOP = 17.0  # the Opus 5.5 ledger stops here for stop 57
NOTE = "graded by Opus 5.5"
SYSTEM = "You grade sentences of answers against a source. Reply with a single JSON object."
USER = """For each numbered sentence below, grade it: "yes" if every claim in the sentence matches \
the source shown, "no" if any claim does not, "unsure" otherwise. A sentence with no claim (a link \
or a refusal) is "yes" unless it misstates the source.

{block}

Return a JSON object with one key per numbered sentence (for example "Q01A1") and the value "yes", \
"no" or "unsure"."""
PROMPT_SHA = hashlib.sha256((SYSTEM + USER).encode()).hexdigest()
_ITEM = re.compile(r"\*\*(Q\d+[AB]\d+)\.\*\*")


def path() -> Path:
    return Path(fb.OUT) / "grader-opus55.jsonl"


def blocks() -> dict[str, str]:
    """Question number → its block of the sheet (question, source, both answers), as you saw it."""
    text = (Path(fb.OUT) / "sheet.md").read_text(encoding="utf-8")
    parts = re.split(r"(?m)^## (Q\d+)\. ", text)[1:]
    return {q: f"{q}. {body.strip()}" for q, body in zip(parts[::2], parts[1::2], strict=True)}


def done() -> dict[str, str]:
    """Item → grade, from the replies kept so far."""
    out: dict[str, str] = {}
    if path().exists():
        for row in map(json.loads, path().read_text(encoding="utf-8").splitlines()):
            out |= row["grades"]
    return out


def parse(text: str, items: list[str]) -> dict[str, str]:
    """A reply as ``{item: grade}`` for exactly the block's items; ValueError otherwise."""
    reply = aj.extract_json(text)
    grades = {k: str(reply.get(k, "")).strip().lower() for k in items}
    if any(g not in GRADES for g in grades.values()):
        raise ValueError("a sentence has no valid grade")
    return grades


def grade() -> None:
    import router  # type: ignore[import-not-found]  # noqa: PLC0415

    router.CAPS[router.OPUS55] = min(router.CAPS[router.OPUS55], OPUS_STOP)
    have = done()
    todo = {q: b for q, b in blocks().items() if not set(_ITEM.findall(b)) <= set(have)}
    print(f"{fb.SET}: {len(blocks())} questions, {len(todo)} to grade", flush=True)
    for q, block in todo.items():
        items = _ITEM.findall(block)
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": USER.format(block=block)},
        ]
        for _ in range(3):
            try:
                grades = parse(router.chat(router.OPUS55, messages)["content"], items)
            except (ValueError, json.JSONDecodeError, router.RouterError):
                continue
            with path().open("a", encoding="utf-8") as f:
                f.write(json.dumps({"q": q, "grades": grades}) + "\n")
            break
        else:
            print(f"{q}: no valid reply, asked again on the next run", flush=True)
    left = sum(not set(_ITEM.findall(b)) <= set(done()) for b in blocks().values())
    print(json.dumps({"left": left, "ledger": router.ledger().get(router.OPUS55, {})}))


def hand() -> dict[str, str]:
    with (Path(fb.OUT) / "grades.csv").open(encoding="utf-8") as f:
        return {r["item"]: r["correct"].strip().lower() for r in csv.DictReader(f)}


def agreement(yours: dict[str, str], theirs: dict[str, str]) -> dict[str, Any]:
    both = [k for k in yours if k in theirs]
    same = sum(yours[k] == theirs[k] for k in both)
    differ = Counter(f"you {yours[k]} / opus {theirs[k]}" for k in both if yours[k] != theirs[k])
    rate = same / max(len(both), 1)
    return {
        "sentences": len(both),
        "same": same,
        "rate": round(rate, 3),
        "differ": dict(differ),
        "used_as_grader": bool(len(both) == len(yours) and rate >= AGREE),
    }


def check() -> None:
    """Step 1: Opus's grades against yours on this set. → results/<set>_arms/grader.json"""
    yours, theirs = hand(), done()
    if any(g not in GRADES for g in yours.values()):
        raise SystemExit("this set has no hand grades")
    out = {"set": fb.SET, "prompt_sha256": PROMPT_SHA, **agreement(yours, theirs)}
    out["items_differing"] = sorted(k for k in yours if k in theirs and yours[k] != theirs[k])
    target = ROOT / "results" / f"{fb.SET}_arms"
    target.mkdir(parents=True, exist_ok=True)
    (target / "grader.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1))


def fill() -> None:
    """Step 2: write Opus's grades as this set's grades, each row noted. Only for a set that has
    no hand grades and whose name marks its generator (``fresh2-q27``)."""
    if "-" not in fb.SET:
        raise SystemExit("this set is graded by hand; its grades are never overwritten")
    yours, theirs = hand(), done()
    if any(g and g not in GRADES for g in yours.values()) or any(
        g for k, g in yours.items() if g and theirs.get(k) != g
    ):
        raise SystemExit("grades.csv holds grades that are not Opus's")
    missing = [k for k in yours if k not in theirs]
    if missing:
        raise SystemExit(f"{len(missing)} sentences have no grade yet; rerun grade")
    with (Path(fb.OUT) / "grades.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["item", "correct", "note"])
        writer.writeheader()
        writer.writerows({"item": k, "correct": theirs[k], "note": NOTE} for k in yours)
    print(json.dumps({"set": fb.SET, "grades": dict(Counter(theirs[k] for k in yours))}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["grade", "check", "fill"])
    command = parser.parse_args().command
    {"grade": grade, "check": check, "fill": fill}[command]()


if __name__ == "__main__":
    main()
