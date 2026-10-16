"""Stop 71 (docs/GRID.md § Stop 71): two frontier models answer stop 70's questions with the source
in the prompt, alone and with the other model checking each sentence; scored against stop 70's 7B
loop.

  uv run python scripts/sota71.py answer flash        # router, resumable
  uv run python scripts/sota71.py answer opus46
  uv run python scripts/sota71.py check flash         # flash's answers, Opus 4.6 as the judge
  uv run python scripts/sota71.py check opus46        # opus46's answers, Flash as the judge
  uv run python scripts/live68_grade.py sheet --stop 71
  uv run python scripts/live68_grade.py grade opus55 --stop 71 --opus-stop 45
  uv run python scripts/live68_grade.py leftover --stop 71
  uv run python scripts/sota71.py report              # → results/sota71_report.json

Answers quote statute text and stay git-ignored (``results/sota71/``).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import threading
import time
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

from legal_rag_verifier.engine import render_premise  # noqa: E402
from legal_rag_verifier.segmenter import split_sentences  # noqa: E402
from legal_rag_verifier.verifier import Verifier  # noqa: E402

OUT = ROOT / "results/sota71"
REPORT = ROOT / "results/sota71_report.json"
SETS = l68.SETS
MODELS = {"flash": "gemini-3.8-flash-high", "opus46": "claude-opus-4-6-thinking"}
OTHER = {"flash": "opus46", "opus46": "flash"}
GENERATORS = ("flash", "opus46", "flash+opus46", "opus46+flash")
ARMS = ("none",)
WORKERS = 4
MARGIN = 0.04  # GRID § Stop 71: the loop is near if the upper end is at most 4 points
RESAMPLES = 10_000
SEED = 20261015
items = l68.items
rows = l68.rows
key = l68.key
read_jsonl = l68.read_jsonl
_lock = threading.Lock()


def path(generator: str) -> Path:
    return OUT / f"{generator.replace('+', '_')}.jsonl"


def append(generator: str, records: Sequence[Mapping[str, Any]]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with _lock, path(generator).open("a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def done(generator: str) -> dict[str, dict[str, Any]]:
    return {r["key"]: r for r in read_jsonl(path(generator)) if r.get("text") is not None}


def messages(item: Mapping[str, Any]) -> list[dict[str, str]]:
    import live_loop as ll  # type: ignore[import-not-found]  # noqa: PLC0415

    system = ll.PROMPTS[item["domain"]].format(premise=render_premise(item["premise"]))
    return [{"role": "system", "content": system}, {"role": "user", "content": item["query"]}]


def chat(name: str) -> Any:
    import teachers  # type: ignore[import-not-found]  # noqa: PLC0415

    return teachers.router_chat(MODELS[name])


def answer(name: str) -> None:
    """One answer per question from ``name``, appended as each returns."""
    import router  # type: ignore[import-not-found]  # noqa: PLC0415

    have = done(name)
    todo = [(s, i) for s in SETS for i in items(s) if key(s, i["id"], "none") not in have]
    print(f"{name}: {len(todo)} to answer", flush=True)
    stopped: list[str] = []

    def one(job: tuple[str, Mapping[str, Any]]) -> None:
        if stopped:
            return
        set_name, item = job
        t0 = time.perf_counter()
        try:
            out = router.chat(MODELS[name], messages(item))
        except (router.BudgetExceededError, router.RouterError) as exc:
            stopped.append(repr(exc)[:300])
            return
        text = (out.get("content") or "").strip()
        append(
            name,
            [
                {
                    "key": key(set_name, item["id"], "none"),
                    "set": set_name,
                    "id": item["id"],
                    "arm": "none",
                    "text": text,
                    "model": MODELS[name],
                    "seconds": round(time.perf_counter() - t0, 3),
                }
            ],
        )

    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(one, todo))
    if stopped:
        print(f"STOPPED: {stopped[0]}", flush=True)
    print(f"{name}: {len(done(name))} answers", flush=True)


class RouterJudge:
    """A frontier model as the verifier's judge, the short reply, labels kept by prompt."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.model_id = MODELS[name]
        self.chat = chat(name)
        self.file = OUT / f"labels.{name}.jsonl"
        self.labels = {r["sha"]: r for r in read_jsonl(self.file)}
        self.prefix = ""
        self.ms = 0.0

    def score(self, premises: Sequence[str], hypothesis: str) -> list[Any]:
        user = aj.short_prompt(hypothesis, premises, self.prefix)
        sha = aj.prompt_key(user)
        label = self.labels.get(sha)
        if label is None or label["label"] not in aj.LABELS:
            label = aj.ask(self.chat, user)
            self.ms += float(label.get("ms") or 0)
            with _lock:
                self.labels[sha] = label
                with self.file.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"sha": sha, **label}, ensure_ascii=False) + "\n")
        name = label["label"] if label["label"] in aj.LABELS else "not_stated"
        return list(aj.one_hot(name, int(label.get("passage") or 0), len(premises)))


def check(name: str) -> None:
    """``name``'s answers checked sentence by sentence, the other model judging; dropped sentences
    are left out of the checked answer."""
    judge_name = OTHER[name]
    arm = f"{name}+{judge_name}"
    answers = done(name)
    have = done(arm)
    by_set = {s: {i["id"]: i for i in items(s)} for s in SETS}
    todo = [a for k, a in answers.items() if k not in have]
    print(f"{arm}: {len(todo)} to check", flush=True)

    def one(a: Mapping[str, Any]) -> None:
        item = by_set[a["set"]][a["id"]]
        judge = RouterJudge(judge_name)
        verifier = Verifier(judge, aj.STRICT_FIGURES)
        kept: list[str] = []
        dropped = 0
        t0 = time.perf_counter()
        for s in split_sentences(a["text"]):
            judge.prefix = " ".join(kept)
            v = verifier.check_sentence(item["premise"], s.text, query=item["query"])
            if v.verdict.name == "EMIT":
                kept.append(s.text)
            else:
                dropped += 1
        append(
            arm,
            [
                {
                    **{k: a[k] for k in ("key", "set", "id", "arm")},
                    "text": " ".join(kept),
                    "dropped": dropped,
                    "check_seconds": round(time.perf_counter() - t0, 3),
                    "seconds": round(float(a.get("seconds") or 0) + time.perf_counter() - t0, 3),
                    "judge": MODELS[judge_name],
                }
            ],
        )

    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(one, todo))
    print(f"{arm}: {len(done(arm))} checked", flush=True)


# ---------------------------------------------------------------------- readings


def bootstrap(diffs: Sequence[int], resamples: int = RESAMPLES, seed: int = SEED) -> list[float]:
    """95 % interval of the mean of paired differences, resampling questions."""
    rng = random.Random(seed)  # noqa: S311 - a resample, not a secret
    n = len(diffs)
    means = sorted(sum(diffs[rng.randrange(n)] for _ in range(n)) / n for _ in range(resamples))
    return [round(means[int(0.025 * resamples)], 4), round(means[int(0.975 * resamples) - 1], 4)]


def agreement(
    first: Mapping[str, str], key: Mapping[str, Mapping[str, Any]], final: Mapping[Any, str]
) -> dict[str, Any]:
    """Opus 5.5's first-pass grades against the final grades, on the 7B's sentences of stop 70
    (every arm, and the turn arm alone). Its unsure grades are counted apart."""
    out: dict[str, Any] = {}
    for scope, arms in {"qwen7": None, "qwen7 turn": {"qwen7:turn"}}.items():
        codes = [
            c
            for c, k in key.items()
            if c in first
            and any(a.startswith("qwen7:") and (arms is None or a in arms) for a in k["answers"])
        ]
        sure = [c for c in codes if first[c] != "unsure"]
        same = sum(first[c] == final[(key[c]["id"], key[c]["text"])] for c in sure)
        out[scope] = {
            "sentences": len(codes),
            "unsure": len(codes) - len(sure),
            "match": same,
            "match_share": round(same / len(sure), 4) if sure else None,
            "wrong_by_opus_right_final": sum(
                first[c] == "no" and final[(key[c]["id"], key[c]["text"])] == "yes" for c in sure
            ),
            "right_by_opus_wrong_final": sum(
                first[c] == "yes" and final[(key[c]["id"], key[c]["text"])] == "no" for c in sure
            ),
        }
    return out


def opus_first_pass(folder: Path) -> dict[str, str]:
    import router  # noqa: PLC0415

    out: dict[str, str] = {}
    for row in read_jsonl(folder / "grader-opus55.jsonl"):
        if row.get("model") == router.OPUS55:
            out |= row["grades"]
    return out


def report() -> dict[str, Any]:
    import live68_grade as lg  # type: ignore[import-not-found]  # noqa: PLC0415
    import live70  # type: ignore[import-not-found]  # noqa: PLC0415

    lg.use(71)  # lg.EXTRA now holds stop 70's final grades
    seventy_key = json.loads((live70.OUT / "key.json").read_text(encoding="utf-8"))
    checked = agreement(opus_first_pass(live70.OUT), seventy_key, lg.EXTRA)
    grades = lg.grades_by_sentence()
    frontier = lg.scored(grades)
    lg.STORE = live70  # the 7B loop, scored with the same grades
    loop = {k: v for k, v in lg.scored(grades).items() if k.startswith("qwen7:")}
    questions = [f"{s}:{r['id']}" for s in SETS for r in rows(s)]
    out: dict[str, Any] = {"arms": {}, "against_loop": {}, "grader_check": checked}
    arms = {"7B loop (stop 70)": ("qwen7", "turn", loop)} | {
        g: (g, "none", frontier) for g in GENERATORS
    }
    for title, (gen, arm, table) in arms.items():
        rows_ = [table[f"{gen}:{q}:{arm}"] for q in questions]
        # an answer with no sentence (a checked answer with nothing kept) counts as a refusal
        out["arms"][title] = {**lg.summary(rows_), "empty": sum(r["sentences"] == 0 for r in rows_)}
    loop_wrong = [loop[f"qwen7:{q}:turn"]["wrong"] > 0 for q in questions]
    for g in GENERATORS:
        theirs = [frontier[f"{g}:{q}:none"]["wrong"] > 0 for q in questions]
        diffs = [int(a) - int(b) for a, b in zip(loop_wrong, theirs, strict=True)]
        low, high = bootstrap(diffs)
        out["against_loop"][g] = {
            "difference": round(sum(diffs) / len(diffs), 4),
            "interval_95": [low, high],
            "near": bool(high <= MARGIN),
            "only_loop_wrong": sum(d == 1 for d in diffs),
            "only_frontier_wrong": sum(d == -1 for d in diffs),
        }
    REPORT.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["answer", "check", "report"])
    parser.add_argument("name", nargs="?", choices=sorted(MODELS))
    args = parser.parse_args()
    if args.command == "answer":
        answer(args.name)
    elif args.command == "check":
        check(args.name)
    else:
        out = report()
        print(json.dumps(out["against_loop"], indent=1))


if __name__ == "__main__":
    main()
