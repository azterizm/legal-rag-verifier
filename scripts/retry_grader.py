"""Stop 67 grading (docs/GRID.md § Stop 67: grading): Opus 5.5 and Gemini 3.8 Flash grade the retry
sheet; you settle what they leave open. (Gemini 3.1 Pro was fixed first; the router no longer
serves it.)

  uv run python scripts/retry_grader.py grade opus55            # first pass, one call per state
  uv run python scripts/retry_grader.py grade flash
  uv run python scripts/retry_grader.py grade opus55 --again    # items they differ on, reason first
  uv run python scripts/retry_grader.py grade flash --again
  uv run python scripts/retry_grader.py leftover                # → leftover.md and leftover.csv
  uv run python scripts/retry_grader.py fill                    # → grades.csv

Replies are appended as they return; a rerun asks only what is missing.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import threading
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import auditor_judge as aj  # type: ignore[import-not-found]  # noqa: E402

OUT = ROOT / "results/retry"
GRADERS = ("opus55", "flash")
NAMES = {"opus55": "Opus 5.5", "flash": "Gemini 3.8 Flash"}
STOPS = {"opus55": 19.0}  # USD, GRID § Stop 67: grading
GROUNDING = ("supported", "unsupported", "contradicted", "no_claim")
YES_NO = ("yes", "no")
WORKERS = 4
SYSTEM = "You grade sentences of answers against a source. Reply with a single JSON object."
FIELDS = """Return a JSON object with one key per lettered retry (for example "S001A"). Each \
value is an object with the keys "grounding", "on_question", "reads_on" and "same_error" ("" when \
the retry is supported or makes no claim). For a retry marked (graded wrong before) give only \
"same_error"."""
USER = "{rule}\n\n{block}\n\n" + FIELDS
AGAIN = "{rule}\n\n{block}\n\nGrade only these retries: {items}.\n\n" + FIELDS.replace(
    "an object with the keys",
    'an object with "reason" (one sentence, written before you decide) and the keys',
)
PROMPT_SHA = hashlib.sha256((SYSTEM + USER).encode()).hexdigest()
_ITEM = re.compile(r"\*\*(S\d+[A-H])\.\*\*( \(graded wrong before\))?")
_lock = threading.Lock()


def path(grader: str, *, again: bool = False) -> Path:
    return OUT / f"grader-{grader}{'.again' if again else ''}.jsonl"


def sheet() -> tuple[str, dict[str, str]]:
    """The sheet's rule, and each state's block as you would see it."""
    text = (OUT / "sheet.md").read_text(encoding="utf-8")
    head, *rest = re.split(r"(?m)^## (S\d+)\. ", text)
    rule = head.split("\n\n", 2)[1].strip()
    return rule, {s: f"{s}. {b.strip()}" for s, b in zip(rest[::2], rest[1::2], strict=True)}


def items_of(block: str) -> dict[str, bool]:
    """Item → whether it is carried as wrong (asked ``same_error`` only)."""
    return {m[1]: bool(m[2]) for m in _ITEM.finditer(block)}


def check(value: Any, carried_wrong: bool) -> dict[str, str]:  # noqa: FBT001
    """One item's grade, validated; ValueError otherwise."""
    if not isinstance(value, Mapping):
        raise ValueError("not an object")  # noqa: TRY004 - a bad reply, asked again
    g = {k: str(value.get(k, "")).strip().lower() for k in ("grounding", "on_question", "reads_on")}
    g["same_error"] = str(value.get("same_error", "")).strip().lower()
    if carried_wrong:
        if g["same_error"] not in YES_NO:
            raise ValueError("same_error missing")
        return {"grounding": "carried_wrong", "same_error": g["same_error"]}
    if g["grounding"] not in GROUNDING or not {g["on_question"], g["reads_on"]} <= set(YES_NO):
        raise ValueError("a field is missing")
    if g["grounding"] in ("unsupported", "contradicted") and g["same_error"] not in YES_NO:
        raise ValueError("same_error missing")
    return g


def outcome(g: Mapping[str, str]) -> str:
    """good, wrong_same, wrong_other or neither."""
    if g["grounding"] in ("unsupported", "contradicted", "carried_wrong"):
        return "wrong_same" if g["same_error"] == "yes" else "wrong_other"
    if g["grounding"] == "supported" and g["on_question"] == g["reads_on"] == "yes":
        return "good"
    return "neither"


def done(grader: str, *, again: bool = False) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    file = path(grader, again=again)
    if file.exists():
        for row in map(json.loads, file.read_text(encoding="utf-8").splitlines()):
            out |= row["grades"]
    return out


def open_items() -> list[str]:
    first = [done(g) for g in GRADERS]
    return [k for k in first[0] if k in first[1] and outcome(first[0][k]) != outcome(first[1][k])]


def grade(grader: str, *, again: bool = False) -> None:
    import router  # type: ignore[import-not-found]  # noqa: PLC0415

    model = {"opus55": router.OPUS55, "flash": router.GEMINI}[grader]
    if grader in STOPS:  # Flash is not charged on this router
        router.CAPS[model] = STOPS[grader]
    rule, blocks = sheet()
    have = done(grader, again=again)
    wanted = set(open_items()) if again else None
    todo = []
    for s, block in blocks.items():
        items = {k: v for k, v in items_of(block).items() if wanted is None or k in wanted}
        if items and not set(items) <= set(have):
            todo.append((s, block, items))
    print(f"{grader}{' again' if again else ''}: {len(todo)} states to ask", flush=True)

    def one(job: tuple[str, str, dict[str, bool]]) -> None:
        s, block, items = job
        if again:
            user = AGAIN.format(rule=rule, block=block, items=", ".join(items))
        else:
            user = USER.format(rule=rule, block=block)
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
        for _ in range(3):
            try:
                reply = aj.extract_json(router.chat(model, messages)["content"])
                grades = {k: check(reply.get(k), carried) for k, carried in items.items()}
            except (ValueError, json.JSONDecodeError, router.RouterError):
                continue
            row: dict[str, Any] = {"state": s, "grades": grades}
            if again:
                row["reasons"] = {
                    k: str((reply.get(k) or {}).get("reason", ""))[:400] for k in items
                }
            with _lock, path(grader, again=again).open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            return
        print(f"{s}: no valid reply, asked again on the next run", flush=True)

    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(one, todo))
    print(json.dumps({"ledger": router.ledger().get(model, {})}))


def consensus() -> dict[str, dict[str, Any]]:
    """Item → ``{grade, by}`` where the graders settle it, or ``{left: True}``."""
    first = [done(g) for g in GRADERS]
    second = [done(g, again=True) for g in GRADERS]
    _, blocks = sheet()
    out: dict[str, dict[str, Any]] = {}
    for block in blocks.values():
        for k in items_of(block):
            if k not in first[0] or k not in first[1]:
                raise SystemExit(f"{k} has not been graded by both yet")
            if outcome(first[0][k]) == outcome(first[1][k]):
                out[k] = {"grade": first[0][k], "by": "first"}
            elif (
                k in second[0]
                and k in second[1]
                and (outcome(second[0][k]) == outcome(second[1][k]))
            ):
                out[k] = {"grade": second[0][k], "by": "again"}
            else:
                out[k] = {"left": True}
    return out


def leftover() -> None:
    """The open items on a short sheet of their own, and a column file for you."""
    settled = consensus()
    left = {k for k, v in settled.items() if v.get("left")}
    rule, blocks = sheet()
    lines = ["# Stop 67: retries left for you", "", rule, ""]
    rows = []
    for block in blocks.values():
        mine = [k for k in items_of(block) if k in left]
        if not mine:
            continue
        kept = [
            line
            for line in block.splitlines()
            if not line.startswith("- **S") or any(f"**{k}.**" in line for k in mine)
        ]
        lines += [f"## {kept[0]}", *kept[1:], ""]
        rows += [
            {"item": k, "grounding": "", "on_question": "", "reads_on": "", "same_error": ""}
            for k in mine
        ]
    (OUT / "leftover.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with (OUT / "leftover.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["item", "grounding", "on_question", "reads_on", "same_error"]
        )
        writer.writeheader()
        writer.writerows(rows)
    by = {"first": 0, "again": 0}
    for v in settled.values():
        if "by" in v:
            by[v["by"]] += 1
    print(
        json.dumps(
            {
                "items": len(settled),
                "settled_first": by["first"],
                "settled_again": by["again"],
                "left": len(rows),
            }
        )
    )


def fill() -> None:
    """``grades.csv`` from the graders' settled items and your leftover column file."""
    settled = consensus()
    yours: dict[str, dict[str, str]] = {}
    file = OUT / "leftover.csv"
    if file.exists():
        with file.open(encoding="utf-8") as f:
            yours = {r["item"]: r for r in csv.DictReader(f)}
    _, blocks = sheet()
    carried = {k: v for b in blocks.values() for k, v in items_of(b).items()}
    rows = []
    for k, v in settled.items():
        if "grade" in v:
            g = v["grade"]
            note = "Opus 5.5 and Gemini 3.8 Flash agree" + (
                "" if v["by"] == "first" else " when asked again"
            )
        else:
            if k not in yours:
                raise SystemExit(f"{k} is left for you and has no grade in leftover.csv")
            g = check(yours[k], carried[k])
            note = "yours"
        rows.append(
            {
                "item": k,
                "grounding": "" if g["grounding"] == "carried_wrong" else g["grounding"],
                "on_question": g.get("on_question", ""),
                "reads_on": g.get("reads_on", ""),
                "same_error": g["same_error"],
                "note": note,
            }
        )
    with (OUT / "grades.csv").open("w", encoding="utf-8", newline="") as f:
        fields = ["item", "grounding", "on_question", "reads_on", "same_error", "note"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: r["item"]))
    print(f"{len(rows)} rows → results/retry/grades.csv")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["grade", "leftover", "fill"])
    parser.add_argument("grader", nargs="?", choices=GRADERS)
    parser.add_argument("--again", action="store_true")
    args = parser.parse_args()
    if args.command == "grade":
        if args.grader is None:
            parser.error("grade needs a grader")
        grade(args.grader, again=args.again)
    elif args.command == "leftover":
        leftover()
    else:
        fill()


if __name__ == "__main__":
    main()
