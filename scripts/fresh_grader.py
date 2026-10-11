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
AGREE = 0.95  # GRID § Stop 57: the gate of step 1, and of the two graders together (G1)
OPUS_STOP = 17.0  # the Opus 5.5 ledger stops here for stop 57
NOTE = "graded by Opus 5.5"
GRADERS = ("opus55", "gemini-pro-low")  # file names; the router models are in ``_model``
SETTLED = {"first": "Opus 5.5 and Gemini 3.1 Pro agree", "again": "they agree when asked again"}
AGAIN_USER = """Grade the sentences listed at the end against the source shown: "yes" if every \
claim in the sentence matches the source, "no" if any claim does not, "unsure" otherwise. A \
sentence with no claim (a link or a refusal) is "yes" unless it misstates the source.

{block}

Grade only these sentences: {items}.

Return a JSON object with one key per listed sentence. Each value is an object with "reason" (one \
sentence, written before you decide) and "grade" ("yes", "no" or "unsure")."""
SYSTEM = "You grade sentences of answers against a source. Reply with a single JSON object."
USER = """For each numbered sentence below, grade it: "yes" if every claim in the sentence matches \
the source shown, "no" if any claim does not, "unsure" otherwise. A sentence with no claim (a link \
or a refusal) is "yes" unless it misstates the source.

{block}

Return a JSON object with one key per numbered sentence (for example "Q01A1") and the value "yes", \
"no" or "unsure"."""
PROMPT_SHA = hashlib.sha256((SYSTEM + USER).encode()).hexdigest()
AGAIN_SHA = hashlib.sha256((SYSTEM + AGAIN_USER).encode()).hexdigest()
_ITEM = re.compile(r"\*\*(Q\d+[AB]\d+)\.\*\*")


def path(grader: str = "opus55", *, again: bool = False) -> Path:
    return Path(fb.OUT) / f"grader-{grader}{'.again' if again else ''}.jsonl"


def _model(grader: str) -> str:
    import router  # type: ignore[import-not-found]  # noqa: PLC0415

    return str({"opus55": router.OPUS55, "gemini-pro-low": router.PRO}[grader])


def blocks() -> dict[str, str]:
    """Question number → its block of the sheet (question, source, both answers), as you saw it."""
    text = (Path(fb.OUT) / "sheet.md").read_text(encoding="utf-8")
    parts = re.split(r"(?m)^## (Q\d+)\. ", text)[1:]
    return {q: f"{q}. {body.strip()}" for q, body in zip(parts[::2], parts[1::2], strict=True)}


def done(grader: str = "opus55", *, again: bool = False) -> dict[str, str]:
    """Item → grade, from the replies kept so far."""
    out: dict[str, str] = {}
    file = path(grader, again=again)
    if file.exists():
        for row in map(json.loads, file.read_text(encoding="utf-8").splitlines()):
            out |= row["grades"]
    return out


def parse(text: str, items: list[str]) -> dict[str, str]:
    """A reply as ``{item: grade}`` for exactly the block's items; ValueError otherwise."""
    reply = aj.extract_json(text)
    grades = {k: str(reply.get(k, "")).strip().lower() for k in items}
    if any(g not in GRADES for g in grades.values()):
        raise ValueError("a sentence has no valid grade")
    return grades


def parse_again(text: str, items: list[str]) -> tuple[dict[str, str], dict[str, str]]:
    reply = aj.extract_json(text)
    grades, reasons = {}, {}
    for k in items:
        value = reply.get(k)
        if not isinstance(value, dict) or str(value.get("grade", "")).strip().lower() not in GRADES:
            raise ValueError(f"{k} has no valid grade")
        grades[k] = str(value["grade"]).strip().lower()
        reasons[k] = str(value.get("reason", ""))[:400]
    return grades, reasons


def open_items() -> list[str]:
    """Sentences the first pass does not settle: the two differ, or either is unsure."""
    first = [done(g) for g in GRADERS]
    return [k for k in first[0] if not (first[0][k] == first[1].get(k) != "unsure")]


def grade(grader: str = "opus55", *, again: bool = False) -> None:
    """The first pass (every sentence, one call per question), or with ``again`` the second ask
    (only the sentences still open, with a reason before each grade)."""
    import router  # noqa: PLC0415

    router.CAPS[router.OPUS55] = min(router.CAPS[router.OPUS55], OPUS_STOP)
    model = _model(grader)
    have = done(grader, again=again)
    wanted = set(open_items()) if again else None
    todo = {}
    for q, block in blocks().items():
        items = [k for k in _ITEM.findall(block) if wanted is None or k in wanted]
        if items and not set(items) <= set(have):
            todo[q] = (block, items)
    print(f"{fb.SET} {grader}{' again' if again else ''}: {len(todo)} questions to ask", flush=True)
    for q, (block, items) in todo.items():
        user = (
            AGAIN_USER.format(block=block, items=", ".join(items))
            if again
            else USER.format(block=block)
        )
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
        for _ in range(3):
            try:
                content = router.chat(model, messages)["content"]
                row: dict[str, Any] = {"q": q}
                if again:
                    row["grades"], row["reasons"] = parse_again(content, items)
                else:
                    row["grades"] = parse(content, items)
            except (ValueError, json.JSONDecodeError, router.RouterError):
                continue
            with path(grader, again=again).open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            break
        else:
            print(f"{q}: no valid reply, asked again on the next run", flush=True)
    print(json.dumps({"ledger": router.ledger().get(model, {})}))


def consensus() -> dict[str, dict[str, str]]:
    """Item → ``{grade, by}`` where the two graders settle it (at the first pass or when asked
    again), or ``{left: why}`` where it is left for you."""
    first = [done(g) for g in GRADERS]
    second = [done(g, again=True) for g in GRADERS]
    out: dict[str, dict[str, str]] = {}
    for k in first[0]:
        a, b = first[0][k], first[1].get(k)
        if b is None:
            raise SystemExit(f"{GRADERS[1]} has not graded {k} yet")
        if a == b != "unsure":
            out[k] = {"grade": a, "by": "first"}
            continue
        a2, b2 = second[0].get(k), second[1].get(k)
        if a2 is None or b2 is None:
            raise SystemExit(f"{k} is open and has not been asked again yet")
        if a2 == b2 != "unsure":
            out[k] = {"grade": a2, "by": "again"}
        else:
            out[k] = {"left": "unsure" if "unsure" in (a2, b2) else "the two differ"}
    return out


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


def check_pair() -> None:
    """G1 and G2: what the two graders settle against your grades. → <set>_arms/graders.json"""
    yours, agreed = hand(), consensus()
    if any(g not in GRADES for g in yours.values()):
        raise SystemExit("this set has no hand grades")
    settled = {k: v for k, v in agreed.items() if "grade" in v}
    left = {k: v["left"] for k, v in agreed.items() if "left" in v}
    same = sum(yours[k] == v["grade"] for k, v in settled.items())
    rate = same / max(len(settled), 1)
    out = {
        "set": fb.SET,
        "prompt_sha256": PROMPT_SHA,
        "again_prompt_sha256": AGAIN_SHA,
        "sentences": len(yours),
        "settled": len(settled),
        "settled_at_first_pass": sum(v["by"] == "first" for v in settled.values()),
        "settled_when_asked_again": sum(v["by"] == "again" for v in settled.values()),
        "G1_same_as_you": same,
        "G1_rate": round(rate, 3),
        "G1_passes": bool(rate >= AGREE),
        "settled_but_not_your_grade": {
            k: f"you {yours[k]} / graders {v['grade']}"
            for k, v in sorted(settled.items())
            if yours[k] != v["grade"]
        },
        "G2_left_for_you": len(left),
        "left_why": dict(Counter(left.values())),
        "left_your_grades": dict(Counter(yours[k] for k in left)),
        "each_grader_alone": {g: sum(yours[k] == done(g)[k] for k in yours) for g in GRADERS},
    }
    target = ROOT / "results" / f"{fb.SET}_arms"
    target.mkdir(parents=True, exist_ok=True)
    (target / "graders.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1))


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


def leftover() -> None:
    """Your sheet for a set the two graders grade: only the sentences they leave open, with the
    question, the source and both answers, and without their grades."""
    if "-" not in fb.SET:
        raise SystemExit("this set is graded by hand")
    left = sorted(k for k, v in consensus().items() if "left" in v)
    lines = [
        f"# Sentences left for you ({fb.SET})",
        "",
        (
            "Opus 5.5 and Gemini 3.1 Pro did not settle these. Fill `correct` in `leftover.csv` "
            "for the sentences marked with an arrow: yes if every claim in the sentence matches "
            "the source shown, no if any claim does not, unsure otherwise. A sentence with no "
            "claim (a link or a refusal) is yes unless it misstates the source."
        ),
        "",
    ]
    for q, block in blocks().items():
        if not any(k.startswith(q) for k in left):
            continue
        marked = block
        for k in left:
            marked = marked.replace(f"- **{k}.**", f"- → **{k}.**")
        lines += [f"## {marked}", ""]
    out = Path(fb.OUT)
    (out / "leftover.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    file = out / "leftover.csv"
    kept = {}
    if file.exists():
        with file.open(encoding="utf-8") as f:
            kept = {r["item"]: r for r in csv.DictReader(f)}
    with file.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["item", "correct", "note"])
        writer.writeheader()
        writer.writerows(kept.get(k, {"item": k, "correct": "", "note": ""}) for k in left)
    print(json.dumps({"set": fb.SET, "left_for_you": len(left), "sheet": str(out / "leftover.md")}))


def fill() -> None:
    """Write this set's grades: what the two graders settle, and your grades for the rest. Each
    row says who graded it. Only for a set named for its generator (``fresh2-q27``)."""
    if "-" not in fb.SET:
        raise SystemExit("this set is graded by hand; its grades are never overwritten")
    agreed = consensus()
    with (Path(fb.OUT) / "leftover.csv").open(encoding="utf-8") as f:
        yours = {r["item"]: r["correct"].strip().lower() for r in csv.DictReader(f)}
    rows = []
    for k in hand():
        v = agreed[k]
        if "grade" in v:
            rows.append({"item": k, "correct": v["grade"], "note": SETTLED[v["by"]]})
        elif yours.get(k) in GRADES:
            rows.append({"item": k, "correct": yours[k], "note": f"you ({v['left']})"})
        else:
            raise SystemExit(f"{k} is left for you and has no grade in leftover.csv yet")
    with (Path(fb.OUT) / "grades.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["item", "correct", "note"])
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"set": fb.SET, "by": dict(Counter(r["note"].split(" (")[0] for r in rows))}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = ["grade", "again", "check", "pair", "leftover", "fill"]
    parser.add_argument("command", choices=commands)
    parser.add_argument("grader", nargs="?", default="opus55", choices=GRADERS)
    args = parser.parse_args()
    if args.command == "grade":
        grade(args.grader)
    elif args.command == "again":
        grade(args.grader, again=True)
    else:
        {"check": check, "pair": check_pair, "leftover": leftover, "fill": fill}[args.command]()


if __name__ == "__main__":
    main()
