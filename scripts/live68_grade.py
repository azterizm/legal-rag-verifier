"""Stop 68 grading and readings (docs/GRID.md § Stop 68).

  uv run python scripts/live68_grade.py sheet                 # the blind sheet; counts and cost
  uv run python scripts/live68_grade.py grade opus55          # first pass, one call per question
  uv run python scripts/live68_grade.py grade flash
  uv run python scripts/live68_grade.py grade opus55 --again  # items they differ on, reason first
  uv run python scripts/live68_grade.py grade flash --again
  uv run python scripts/live68_grade.py leftover              # → leftover.md and leftover.csv
  uv run python scripts/live68_grade.py report                # → results/live68_report.json

Each distinct sentence of a question is one item, graded once. A sentence an earlier sheet graded
for the same question keeps that grade. The engine's fixed refusal is not graded.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import statistics
import sys
import threading
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "batteries/verifier"))

import auditor_judge as aj  # type: ignore[import-not-found]  # noqa: E402
import live68 as l68  # type: ignore[import-not-found]  # noqa: E402

from legal_rag_verifier.segmenter import split_sentences  # noqa: E402

OUT = ROOT / "results/live68"
REPORT = ROOT / "results/live68_report.json"
GRADES = ("yes", "no", "unsure")
GRADERS = ("opus55", "flash")
OPUS_STOP = 39.0  # USD, GRID § Stop 68
SHEETS = ("fresh", "fresh2", "fresh2-q27", "fresh2-live", "fresh2-short-live")
SHEET_SEED = 20261017
WORKERS = 4
ALPHA = 0.05
REFUSAL_MARGIN = 0.05
RULE = (
    'For each numbered sentence, grade it: "yes" if every claim in the sentence matches the source '
    'shown, "no" if any claim does not, "unsure" otherwise. A sentence with no claim (a link or a '
    'refusal) is "yes" unless it misstates the source.'
)
SYSTEM = "You grade sentences of answers against a source. Reply with a single JSON object."
USER = (
    "{rule}\n\n{block}\n\nReturn a JSON object with one key per numbered sentence (for example "
    '"Q001A1") and the value "yes", "no" or "unsure".'
)
AGAIN = (
    "{rule}\n\n{block}\n\nGrade only these sentences: {items}.\n\nReturn a JSON object with one "
    'key per listed sentence. Each value is an object with "reason" (one sentence, written before '
    'you decide) and "grade" ("yes", "no" or "unsure").'
)
_ITEM = re.compile(r"\*\*(Q\d+[A-Z]\d+)\.\*\*")
_lock = threading.Lock()


def refusals() -> set[str]:
    import live_loop as ll  # type: ignore[import-not-found]  # noqa: PLC0415

    return set(ll.REFUSALS.values())


def sentences(text: str) -> list[str]:
    return [s.text.strip() for s in split_sentences(text) if s.text.strip()]


STORE: Any = l68  # the answers graded: stop 68's, or stop 70's after ``use(70)``
EXTRA: dict[tuple[str, str], str] = {}  # further grades carried (stop 70: stop 68's)


def use(stop: int) -> None:
    """Point the sheet, the graders and the readings at stop 70's answers and files."""
    global OUT, REPORT, STORE, EXTRA  # noqa: PLW0603 - one switch, as pool2.activate
    if stop == 70:  # noqa: PLR2004
        import live70  # type: ignore[import-not-found]  # noqa: PLC0415

        EXTRA = grades_by_sentence()  # stop 68's grades, carried by question and sentence
        OUT, REPORT, STORE = live70.OUT, ROOT / "results/live70_report.json", live70


def answers() -> list[dict[str, Any]]:
    """Every final answer of every generator, with its generator."""
    out = []
    for g in STORE.GENERATORS:
        out += [{**r, "gen": g} for r in STORE.done(g).values()]
    return out


def carried() -> dict[tuple[str, str], str]:
    """(question id, sentence) → grade from every earlier sheet; a sentence graded two ways is
    left out."""
    seen: dict[tuple[str, str], set[str]] = {}
    for name in SHEETS:
        folder = ROOT / "results" / name
        key = json.loads((folder / "key.json").read_text(encoding="utf-8"))
        with (folder / "grades.csv").open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                grade = row["correct"].strip().lower()
                if grade in GRADES:
                    k = key[row["item"]]
                    seen.setdefault((k["id"], k["text"].strip()), set()).add(grade)
    for k, g in EXTRA.items():
        seen.setdefault(k, set()).add(g)
    return {k: next(iter(v)) for k, v in seen.items() if len(v) == 1}


# ---------------------------------------------------------------------- the sheet


def build() -> dict[str, Any]:
    """The blind sheet: per question, the distinct answers lettered at random; each distinct
    sentence numbered once (a repeat points to its first number); carried and refusal sentences
    are shown but not numbered."""
    import distill_data as dd  # type: ignore[import-not-found]  # noqa: PLC0415
    import fresh_battery as fb  # type: ignore[import-not-found]  # noqa: PLC0415

    refusal = refusals()
    old = carried()
    by_question: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for a in answers():
        by_question.setdefault((a["set"], a["id"]), []).append(a)
    rng = random.Random(SHEET_SEED)  # noqa: S311 - a shuffle, not a secret
    order = sorted(by_question)
    rng.shuffle(order)
    lines = ["# Stop 68: sentences to grade", "", RULE, ""]
    key: dict[str, Any] = {}
    counts = {"questions": len(order), "items": 0, "carried": 0, "refusals": 0, "repeats": 0}
    for q, (set_name, row_id) in enumerate(order, 1):
        row = next(r for r in l68.rows(set_name) if r["id"] == row_id)
        source = dd.source_text(row) if set_name == "pool" else fb.source_text(row)
        texts: dict[str, list[str]] = {}
        for a in by_question[(set_name, row_id)]:
            texts.setdefault(a["text"].strip(), []).append(f"{a['gen']}:{a['arm']}")
        group = sorted(texts)
        rng.shuffle(group)
        block = [f"## Q{q:03d}. {row['query']}", "", "Source:", "", "```", source, "```", ""]
        first: dict[str, str] = {}
        for letter, text in zip("ABCDEFGHIJKLMNOP", group, strict=False):
            block += [f"**Answer {letter}**", ""]
            for n, s in enumerate(sentences(text), 1):
                code = f"Q{q:03d}{letter}{n}"
                if s in refusal:
                    block.append(f"- (refusal, not graded) {s}")
                    counts["refusals"] += 1
                elif (row_id, s) in old:
                    block.append(f"- (graded before) {s}")
                    counts["carried"] += 1
                elif s in first:
                    block.append(f"- (= {first[s]}) {s}")
                    counts["repeats"] += 1
                else:
                    first[s] = code
                    block.append(f"- **{code}.** {s}")
                    key[code] = {"set": set_name, "id": row_id, "text": s, "answers": texts[text]}
                    counts["items"] += 1
            block.append("")
        lines += block
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sheet.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (OUT / "key.json").write_text(json.dumps(key, indent=1, ensure_ascii=False) + "\n", "utf-8")
    return counts


def blocks() -> dict[str, str]:
    text = (OUT / "sheet.md").read_text(encoding="utf-8")
    parts = re.split(r"(?m)^## (Q\d+)\. ", text)[1:]
    return {q: f"{q}. {body.strip()}" for q, body in zip(parts[::2], parts[1::2], strict=True)}


# ---------------------------------------------------------------------- graders


def path(grader: str, *, again: bool = False) -> Path:
    return OUT / f"grader-{grader}{'.again' if again else ''}.jsonl"


def done(grader: str, *, again: bool = False) -> dict[str, str]:
    out: dict[str, str] = {}
    file = path(grader, again=again)
    if file.exists():
        for row in map(json.loads, file.read_text(encoding="utf-8").splitlines()):
            out |= row["grades"]
    return out


def open_items() -> list[str]:
    first = [done(g) for g in GRADERS]
    return [k for k in first[0] if not (first[0][k] == first[1].get(k) != "unsure")]


def parse(reply: Mapping[str, Any], items: Sequence[str], *, again: bool) -> dict[str, str]:
    out = {}
    for k in items:
        value = reply.get(k)
        grade = value.get("grade", "") if again and isinstance(value, Mapping) else value
        grade = str(grade or "").strip().lower()
        if grade not in GRADES:
            raise ValueError(f"{k} has no valid grade")
        out[k] = grade
    return out


def grade(grader: str, *, again: bool = False, model: str = "") -> None:
    """Ask ``grader``'s share, one call per question, appended as each returns. A rate limit that
    outlasts the router's retries, or the model's ledger stop, ends the run cleanly: no further call
    is made and what is done is kept. ``model`` puts another router model in this grader's place
    (stop 70: Opus 5.5 is replaced if it stops); each row records the model that graded it."""
    import router  # type: ignore[import-not-found]  # noqa: PLC0415

    model = model or {"opus55": router.OPUS55, "flash": router.GEMINI}[grader]
    if model not in router.MODELS:
        raise SystemExit(f"{model!r} is not a router model this repo may call")
    if model == router.OPUS55:
        router.CAPS[model] = min(router.CAPS[model], OPUS_STOP)
    have = done(grader, again=again)
    wanted = set(open_items()) if again else None
    todo = []
    for q, block in blocks().items():
        items = [k for k in _ITEM.findall(block) if wanted is None or k in wanted]
        if items and not set(items) <= set(have):
            todo.append((q, block, items))
    print(f"{grader} ({model}){' again' if again else ''}: {len(todo)} questions", flush=True)
    stopped: list[str] = []

    def one(job: tuple[str, str, list[str]]) -> None:
        if stopped:
            return
        q, block, items = job
        user = (
            AGAIN.format(rule=RULE, block=block, items=", ".join(items))
            if again
            else USER.format(rule=RULE, block=block)
        )
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
        for _ in range(3):
            if stopped:
                return
            try:
                reply = aj.extract_json(router.chat(model, messages)["content"])
                grades = parse(reply, items, again=again)
            except (router.BudgetExceededError, router.RouterError) as exc:
                stopped.append(repr(exc)[:300])  # the ledger stop, or a limit past every retry
                return
            except (ValueError, json.JSONDecodeError):
                continue
            row: dict[str, Any] = {"q": q, "grades": grades, "model": model}
            if again:
                row["reasons"] = {
                    k: str((reply.get(k) or {}).get("reason", ""))[:400] for k in items
                }
            with _lock, path(grader, again=again).open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            return
        print(f"{q}: no valid reply, asked again on the next run", flush=True)

    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(one, todo))
    left = sum(1 for q, _, items in todo if not set(items) <= set(done(grader, again=again)))
    if stopped:
        print(f"STOPPED: {stopped[0]}; {left} questions left for the next model", flush=True)
    print(json.dumps({"left": left, "ledger": router.ledger().get(model, {})}))


def consensus() -> dict[str, dict[str, Any]]:
    first = [done(g) for g in GRADERS]
    second = [done(g, again=True) for g in GRADERS]
    key = json.loads((OUT / "key.json").read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    for k in key:
        a, b = first[0].get(k), first[1].get(k)
        if a is None or b is None:
            raise SystemExit(f"{k} has not been graded by both yet")
        if a == b != "unsure":
            out[k] = {"grade": a, "by": "first"}
            continue
        a2, b2 = second[0].get(k), second[1].get(k)
        out[k] = {"grade": a2, "by": "again"} if a2 is not None and a2 == b2 != "unsure" else {}
    return out


def leftover() -> None:
    settled = consensus()
    left = {k for k, v in settled.items() if not v}
    lines = ["# Stop 68: sentences left for you", "", RULE, ""]
    for block in blocks().values():
        mine = [k for k in _ITEM.findall(block) if k in left]
        if not mine:
            continue
        kept = [
            line
            for line in block.splitlines()
            if not line.startswith("- **Q") or any(f"**{k}.**" in line for k in mine)
        ]
        lines += [f"## {kept[0]}", *kept[1:], ""]
    (OUT / "leftover.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with (OUT / "leftover.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["item", "correct", "note"])
        writer.writeheader()
        writer.writerows({"item": k, "correct": "", "note": ""} for k in sorted(left))
    by = {"first": 0, "again": 0}
    for v in settled.values():
        if v:
            by[v["by"]] += 1
    print(json.dumps({"items": len(settled), **by, "left": len(left)}))


# ---------------------------------------------------------------------- readings


def mcnemar(only_a: int, only_b: int) -> float:
    from retry_report import mcnemar as exact  # type: ignore[import-not-found]  # noqa: PLC0415

    return float(exact(only_a, only_b))


def holm(p: Mapping[str, float]) -> dict[str, float]:
    from retry_report import holm as adjust  # noqa: PLC0415

    return dict(adjust(p))


def grades_by_sentence() -> dict[tuple[str, str], str]:
    """(question id, sentence) → yes / no / unsure: carried, the graders, then yours."""
    key = json.loads((OUT / "key.json").read_text(encoding="utf-8"))
    settled = consensus()
    yours: dict[str, str] = {}
    file = OUT / "leftover.csv"
    if file.exists():
        with file.open(encoding="utf-8") as f:
            yours = {r["item"]: r["correct"].strip().lower() for r in csv.DictReader(f)}
    out = dict(carried())
    for code, item in key.items():
        g = settled[code].get("grade") if settled[code] else yours.get(code, "")
        if g not in GRADES:
            raise SystemExit(f"{code} has no grade")
        out[(item["id"], item["text"])] = g
    return out


def scored(grades: Mapping[tuple[str, str], str]) -> dict[str, dict[str, Any]]:
    """Per answer key ``gen:set:id:arm``: its sentences' grades and counts."""
    refusal = refusals()
    out = {}
    for a in answers():
        ss = sentences(a["text"])
        g = [grades[(a["id"], s)] for s in ss if s not in refusal]
        trace = a.get("trace") or {}
        out[f"{a['gen']}:{a['key']}"] = {
            "gen": a["gen"],
            "set": a["set"],
            "id": a["id"],
            "arm": a["arm"],
            "sentences": len(ss),
            "refusals": sum(s in refusal for s in ss),
            "right": g.count("yes"),
            "wrong": g.count("no"),
            "unsure": g.count("unsure"),
            "only_refusal": bool(ss) and all(s in refusal for s in ss),
            "rollbacks": (trace.get("totals") or {}).get("rollbacks"),
            "seconds": a.get("seconds"),
        }
    return out


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [0.0, 0.0]
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / (1 + z * z / n)
    return [round(centre - half, 4), round(centre + half, 4)]


def summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    graded = sum(r["right"] + r["wrong"] + r["unsure"] for r in rows)
    wrong = sum(r["wrong"] for r in rows)
    sentences_all = sum(r["sentences"] for r in rows)
    refused = sum(r["refusals"] for r in rows)
    seconds = [r["seconds"] for r in rows if r["seconds"] is not None]
    return {
        "answers": len(rows),
        "answers_with_a_wrong_sentence": sum(r["wrong"] > 0 for r in rows),
        "sentences": sentences_all,
        "graded": graded,
        "wrong": wrong,
        "wrong_share": round(wrong / graded, 4) if graded else None,
        "wrong_interval_95": wilson(wrong, graded),
        "unsure": sum(r["unsure"] for r in rows),
        "right": sum(r["right"] for r in rows),
        "right_per_answer": round(sum(r["right"] for r in rows) / len(rows), 3) if rows else None,
        "refusal_sentences": refused,
        "refusal_share": round(refused / sentences_all, 4) if sentences_all else None,
        "only_refusal": sum(r["only_refusal"] for r in rows),
        "rollbacks": sum(r["rollbacks"] or 0 for r in rows),
        "seconds_p50": round(statistics.median(seconds), 3) if seconds else None,
    }


def paired(
    by: Mapping[str, Mapping[str, Any]], gen: str, a: str, b: str, questions: Sequence[str]
) -> dict[str, Any]:
    """Answers with a wrong sentence, ``a`` against ``b``, paired by question."""
    xa = [by[f"{gen}:{q}:{a}"]["wrong"] > 0 for q in questions]
    xb = [by[f"{gen}:{q}:{b}"]["wrong"] > 0 for q in questions]
    only_a = sum(x and not y for x, y in zip(xa, xb, strict=True))
    only_b = sum(y and not x for x, y in zip(xa, xb, strict=True))
    return {"only_a_wrong": only_a, "only_b_wrong": only_b, "p": mcnemar(only_a, only_b)}


def report() -> dict[str, Any]:
    by = scored(grades_by_sentence())
    out: dict[str, Any] = {"generators": {}, "primary": {}}
    questions = [f"{s}:{r['id']}" for s in l68.SETS for r in l68.rows(s)]
    for gen in l68.GENERATORS:
        g: dict[str, Any] = {}
        for arm in l68.ARMS:
            rows = [v for v in by.values() if v["gen"] == gen and v["arm"] == arm]
            g[arm] = {"total": summary(rows)}
            for s in l68.SETS:
                g[arm][s] = summary([r for r in rows if r["set"] == s])
        have = [q for q in questions if all(f"{gen}:{q}:{arm}" in by for arm in l68.ARMS)]
        g["questions_with_all_arms"] = len(have)
        g["plain_against_turn"] = paired(by, gen, "plain", "turn", have)
        g["turn_against_none"] = paired(by, gen, "turn", "none", have)
        g["plain_against_none"] = paired(by, gen, "plain", "none", have)
        out["generators"][gen] = g
    adjusted = holm({gen: v["plain_against_turn"]["p"] for gen, v in out["generators"].items()})
    for gen, v in out["generators"].items():
        t = v["plain_against_turn"]
        share = {arm: v[arm]["total"]["refusal_share"] or 0.0 for arm in ("plain", "turn")}
        out["primary"][gen] = {
            **t,
            "holm_p": round(adjusted[gen], 6),
            "refusal_share_plain": share["plain"],
            "refusal_share_turn": share["turn"],
            "plain_better": bool(
                t["only_a_wrong"] < t["only_b_wrong"]
                and adjusted[gen] < ALPHA
                and share["plain"] - share["turn"] <= REFUSAL_MARGIN
            ),
        }
    REPORT.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return out


RIGHT_FLOOR = 0.90  # GRID § Stop 70: right sentences per answer at least this share of none's
REFUSAL_CAP = 0.05


def report70() -> dict[str, Any]:
    """Stop 70's readings: each loop against ``none`` per generator, Holm over the four."""
    by = scored(grades_by_sentence())
    out: dict[str, Any] = {"generators": {}, "primary": {}}
    questions = [f"{s}:{r['id']}" for s in STORE.SETS for r in STORE.rows(s)]
    tests: dict[str, dict[str, Any]] = {}
    for gen in STORE.GENERATORS:
        g: dict[str, Any] = {}
        for arm in STORE.ARMS:
            rows = [v for v in by.values() if v["gen"] == gen and v["arm"] == arm]
            g[arm] = {"total": summary(rows)}
            for s in STORE.SETS:
                g[arm][s] = summary([r for r in rows if r["set"] == s])
        have = [q for q in questions if all(f"{gen}:{q}:{arm}" in by for arm in STORE.ARMS)]
        g["questions_with_all_arms"] = len(have)
        g["turn_against_ban"] = paired(by, gen, "turn", "ban", have)
        for arm in ("ban", "turn"):
            tests[f"{gen} {arm}"] = paired(by, gen, arm, "none", have)
        out["generators"][gen] = g
    adjusted = holm({k: v["p"] for k, v in tests.items()})
    for name, t in tests.items():
        gen, arm = name.split()
        loop, none = out["generators"][gen][arm]["total"], out["generators"][gen]["none"]["total"]
        right_ok = (loop["right_per_answer"] or 0) >= RIGHT_FLOOR * (none["right_per_answer"] or 0)
        out["primary"][name] = {
            **t,
            "holm_p": round(adjusted[name], 6),
            "refusal_share": loop["refusal_share"],
            "right_per_answer": loop["right_per_answer"],
            "right_per_answer_none": none["right_per_answer"],
            "better": bool(
                t["only_a_wrong"] < t["only_b_wrong"]
                and adjusted[name] < ALPHA
                and (loop["refusal_share"] or 0) <= REFUSAL_CAP
                and right_ok
            ),
        }
    REPORT.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["sheet", "grade", "leftover", "report"])
    parser.add_argument("grader", nargs="?", choices=GRADERS)
    parser.add_argument("--again", action="store_true")
    parser.add_argument("--stop", type=int, default=68, choices=[68, 70])
    parser.add_argument("--model", default="", help="a router model in the grader's place")
    args = parser.parse_args()
    use(args.stop)
    if args.command == "sheet":
        print(json.dumps(build(), indent=1))
    elif args.command == "grade":
        if args.grader is None:
            parser.error("grade needs a grader")
        grade(args.grader, again=args.again, model=args.model)
    elif args.command == "leftover":
        leftover()
    elif args.stop == 70:  # noqa: PLR2004
        print(json.dumps(report70()["primary"], indent=1))
    else:
        print(json.dumps(report()["primary"], indent=1))


if __name__ == "__main__":
    main()
