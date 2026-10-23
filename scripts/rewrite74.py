"""Stop 74 (docs/GRID.md § Stop 74): a rejected sentence rewritten, with the source as a user turn
at the cut, instead of dropped. Stop 71's unchecked answers; no Opus 4.6 call.

  Pair A: Opus 4.6's answers, Flash judging and rewriting; drop arm stop 71's ``opus46+flash``.
  Pair B: Flash's answers, Qwen 3.8 27B judging (Groq and Cloudflare in rotation), Flash
  rewriting; its drop arm made again with the Qwen judge.

  uv run python scripts/rewrite74.py rebuild          # pair A's drop arm from stop 71's labels
  uv run python scripts/rewrite74.py smoke            # each host alone, then 2 questions per pair
  uv run python scripts/rewrite74.py drop B           # router and hosts, resumable
  uv run python scripts/rewrite74.py rewrite B
  uv run python scripts/rewrite74.py rewrite A
  uv run python scripts/live68_grade.py sheet --stop 74
  uv run python scripts/live68_grade.py grade opus55 --stop 74 --opus-stop 45
  uv run python scripts/live68_grade.py leftover --stop 74
  uv run python scripts/rewrite74.py report           # → results/rewrite74_report.json

Answers, rewrites and labels quote statute text and stay git-ignored (``results/rewrite74/``).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "batteries/verifier"))

import auditor_judge as aj  # type: ignore[import-not-found]  # noqa: E402
import hosted  # type: ignore[import-not-found]  # noqa: E402
import live68 as l68  # type: ignore[import-not-found]  # noqa: E402
import sota71  # type: ignore[import-not-found]  # noqa: E402

from legal_rag_verifier.premise import Premise  # noqa: E402
from legal_rag_verifier.segmenter import split_sentences  # noqa: E402
from legal_rag_verifier.verifier import Reason, Verdict, Verifier  # noqa: E402

OUT = ROOT / "results/rewrite74"
REPORT = ROOT / "results/rewrite74_report.json"
SETS = l68.SETS
ARMS = ("none",)
TEMPERATURES = (0.0, 1.0, 1.0)  # GRID § Stop 74: 3 tries, the same turn, try 1 greedy
INJECT_WINDOWS = 2  # the engine's default
SOURCE_CHARS = 3200  # the engine cuts at 800 tokens; no hosted tokenizer here
MARGIN = sota71.MARGIN  # stop 71's 4 points
ALPHA = 0.05
WORKERS = 4
QWEN = "qwen3.8-27b"


@dataclass(frozen=True)
class Pair:
    answers: str  # stop 71's unchecked arm
    judge: str  # "flash" or "qwen27"
    drop: str  # the drop arm's generator name
    rewrite: str  # the rewrite arm's generator name
    stop71_labels: str | None  # stop 71's labels this judge gave, reused by prompt


PAIRS = {
    "A": Pair("opus46", "flash", "opus46+flash", "opus46+flash~rw", "labels.flash.jsonl"),
    "B": Pair("flash", "qwen27", "flash+qwen27", "flash+qwen27~rw", None),
}
GENERATORS = ("flash+qwen27", "flash+qwen27~rw", "opus46+flash~rw")  # graded in stop 74
JUDGED = frozenset({Reason.NLI_CONTRADICTION, Reason.NLI_NOT_ENTAILED, Reason.NEUTRAL_STRICT})
items = l68.items
rows = l68.rows
key = l68.key
read_jsonl = l68.read_jsonl
_lock = threading.Lock()


def path(generator: str) -> Path:
    return OUT / f"{generator.replace('+', '_').replace('~', '.')}.jsonl"


def append(generator: str, records: Sequence[Mapping[str, Any]]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with _lock, path(generator).open("a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def done(generator: str) -> dict[str, dict[str, Any]]:
    return {r["key"]: r for r in read_jsonl(path(generator)) if r.get("text") is not None}


# ---------------------------------------------------------------------- the judge


class MissingLabelError(RuntimeError):
    """An offline judge met a prompt with no stored label."""


class Labels:
    """A judge's labels by prompt hash: stop 71's (read only) and this stop's (appended)."""

    def __init__(self, judge: str, stop71: str | None) -> None:
        self.file = OUT / f"labels.{judge}.jsonl"
        self.by: dict[str, dict[str, Any]] = {}
        if stop71:
            self.by |= {r["sha"]: r for r in read_jsonl(sota71.OUT / stop71)}
        self.by |= {r["sha"]: r for r in read_jsonl(self.file)}
        self.asked = 0

    def get(self, sha: str) -> dict[str, Any] | None:
        label = self.by.get(sha)
        return label if label is not None and label["label"] in aj.LABELS else None

    def put(self, sha: str, label: Mapping[str, Any]) -> None:
        with _lock:
            self.by[sha] = dict(label)
            self.asked += 1
            OUT.mkdir(parents=True, exist_ok=True)
            with self.file.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"sha": sha, **label}, ensure_ascii=False) + "\n")


class Judge:
    """The verifier's judge, the short reply, one per answer. ``ask`` returns ``{content, ms,
    tokens}`` (and ``provider`` for the hosts); ``rotate`` moves the hosts on after a reply with no
    valid label. ``offline`` raises instead of asking."""

    def __init__(
        self,
        labels: Labels,
        ask: Callable[[list[dict[str, str]]], dict[str, Any]] | None,
        model: str,
        *,
        rotate: Callable[[], None] | None = None,
    ) -> None:
        self.labels = labels
        self.ask = ask
        self.model_id = model
        self.rotate = rotate
        self.prefix = ""
        self.provider = ""

    def _chat(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        if self.ask is None:
            raise MissingLabelError("an offline judge does not ask")
        out = self.ask(messages)
        self.provider = str(out.get("provider") or "")
        return out

    def score(self, premises: Sequence[str], hypothesis: str) -> list[Any]:
        user = aj.short_prompt(hypothesis, premises, self.prefix)
        sha = aj.prompt_key(user)
        label = self.labels.get(sha)
        if label is None:
            if self.ask is None:
                raise MissingLabelError(sha)
            label = aj.ask(self._chat, user)
            if label["label"] not in aj.LABELS and self.rotate is not None:
                self.rotate()  # GRID: no valid label after 3 asks, the other host asks again
                label = aj.ask(self._chat, user)
            label = {**label, "model": self.model_id, "provider": self.provider}
            self.labels.put(sha, label)
        name = label["label"] if label["label"] in aj.LABELS else "not_stated"
        return list(aj.one_hot(name, int(label.get("passage") or 0), len(premises)))


_ROTATION: hosted.Rotation | None = None


def rotation() -> hosted.Rotation:
    global _ROTATION  # noqa: PLW0603 - one rotation shared by every worker
    if _ROTATION is None:
        _ROTATION = hosted.Rotation()
    return _ROTATION


def judge_for(pair: Pair, labels: Labels, *, offline: bool = False) -> Judge:
    if offline:
        return Judge(labels, None, pair.judge)
    if pair.judge == "flash":
        return Judge(labels, sota71.chat("flash"), sota71.MODELS["flash"])
    r = rotation()
    return Judge(labels, hosted.judge_chat(r), QWEN, rotate=r.next)


# ---------------------------------------------------------------------- the rewrite


def what(domain: str) -> str:
    return "documentation" if domain == "software" else "provision"


def source_text(premise: Premise, aligned: Sequence[int], limit: int = SOURCE_CHARS) -> str:
    """X's aligned windows, the first ``INJECT_WINDOWS``, rendered as the engine renders them
    (``InFlightGenerator._source_text``), cut at ``limit`` characters at a word boundary."""
    passages = [premise.passages[i] for i in list(aligned)[:INJECT_WINDOWS]]
    source = "\n\n".join(f"[{p.heading}]\n{p.text}" if p.heading else p.text for p in passages)
    if len(source) > limit:
        cut = source[:limit]
        source = (cut.rsplit(None, 1)[0] if " " in cut else cut).rstrip() + " …"
    return source


def turn(item: Mapping[str, Any], source: str) -> str:
    import live_loop as ll  # type: ignore[import-not-found]  # noqa: PLC0415

    template = str(ll._TURN_USER).format(what=what(item["domain"]))
    return template.format(query=item["query"], source=source)


def rewrite_messages(
    item: Mapping[str, Any], kept: Sequence[str], source: str
) -> list[dict[str, str]]:
    """Stop 71's prompt, the sentences kept so far as the assistant's turn (none when nothing is
    kept), then stop 30's turn with the source."""
    out: list[dict[str, str]] = list(sota71.messages(item))
    if kept:
        out.append({"role": "assistant", "content": " ".join(kept)})
    out.append({"role": "user", "content": turn(item, source)})
    return out


def first_sentence(reply: str) -> str:
    texts = [s.text.strip() for s in split_sentences(hosted.strip_thinking(reply or ""))]
    return next((t for t in texts if t), "")


Rewriter = Callable[[list[dict[str, str]], float], str]


def flash_rewriter(messages: list[dict[str, str]], temperature: float) -> str:
    import router  # type: ignore[import-not-found]  # noqa: PLC0415

    return str(router.chat(router.GEMINI, messages, temperature=temperature)["content"] or "")


def walk(
    item: Mapping[str, Any], text: str, judge: Judge, rewrite: Rewriter | None
) -> dict[str, Any]:
    """The answer's sentences checked in order; a rejected one dropped (``rewrite`` None) or given
    up to 3 tries. Returns the kept text and one record per rejected sentence."""
    verifier = Verifier(judge, aj.STRICT_FIGURES)
    premise, query = item["premise"], item["query"]
    kept: list[str] = []
    points: list[dict[str, Any]] = []
    for n, s in enumerate(split_sentences(text)):
        judge.prefix = " ".join(kept)
        v = verifier.check_sentence(premise, s.text, query=query)
        if v.verdict is Verdict.EMIT:
            kept.append(s.text)
            continue
        point: dict[str, Any] = {
            "n": n,
            "x": s.text,
            "reasons": [r.value for r in v.reasons],
            "by": "judge" if set(v.reasons) & JUDGED else "claims",
            "aligned": list(v.aligned),
            "outcome": "dropped",
            "tries": [],
        }
        points.append(point)
        if rewrite is None:
            continue
        source = source_text(premise, v.aligned) if v.aligned else ""
        if not source:
            point["outcome"] = "no_window"
            continue
        point["source"] = source
        messages = rewrite_messages(item, kept, source)
        for t, temperature in enumerate(TEMPERATURES, 1):
            t0 = time.perf_counter()
            reply = rewrite(messages, temperature)
            r = first_sentence(reply)
            attempt: dict[str, Any] = {"temperature": temperature, "text": r, "reply": reply}
            if r:
                judge.prefix = " ".join(kept)
                rv = verifier.check_sentence(premise, r, query=query)
                attempt |= {"verdict": rv.verdict.value, "reasons": [x.value for x in rv.reasons]}
            attempt["seconds"] = round(time.perf_counter() - t0, 3)
            point["tries"].append(attempt)
            if attempt.get("verdict") == Verdict.EMIT.value:
                point["outcome"] = f"try{t}"
                point["repeats_kept"] = r in kept
                kept.append(r)
                break
    return {"text": " ".join(kept), "points": points}


# ---------------------------------------------------------------------- runs


def stopping_errors() -> tuple[type[BaseException], ...]:
    import router  # noqa: PLC0415

    return (router.BudgetExceededError, router.RouterError, hosted.HostedError)


def run(
    pair_name: str,
    *,
    rewrite: bool,
    only: Sequence[str] | None = None,
    workers: int = WORKERS,
) -> None:
    """One arm of a pair over stop 71's unchecked answers, appended as each answer finishes. A
    router or host failure past every retry stops the run cleanly; a rerun skips what is done."""
    pair = PAIRS[pair_name]
    arm = pair.rewrite if rewrite else pair.drop
    if not rewrite and pair.stop71_labels:
        raise SystemExit(f"{arm} is stop 71's arm; it is not made again")
    labels = Labels(pair.judge, pair.stop71_labels)
    answers = sota71.done(pair.answers)
    have = done(arm)
    by_set = {s: {i["id"]: i for i in items(s)} for s in SETS}
    todo = [a for k, a in answers.items() if k not in have and (only is None or k in only)]
    print(f"{arm}: {len(todo)} to do", flush=True)
    stopped: list[str] = []
    errors = stopping_errors()

    def one(a: Mapping[str, Any]) -> None:
        if stopped:
            return
        item = by_set[a["set"]][a["id"]]
        judge = judge_for(pair, labels)
        t0 = time.perf_counter()
        try:
            out = walk(item, a["text"], judge, flash_rewriter if rewrite else None)
        except errors as exc:
            stopped.append(repr(exc)[:300])
            return
        check = time.perf_counter() - t0
        append(
            arm,
            [
                {
                    **{k: a[k] for k in ("key", "set", "id", "arm")},
                    "text": out["text"],
                    "points": out["points"],
                    "dropped": sum(p["outcome"] in ("dropped", "no_window") for p in out["points"]),
                    "rewritten": sum(p["outcome"].startswith("try") for p in out["points"]),
                    "check_seconds": round(check, 3),
                    "seconds": round(float(a.get("seconds") or 0) + check, 3),
                    "judge": judge.model_id,
                }
            ],
        )

    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(one, todo))
    if stopped:
        print(f"STOPPED: {stopped[0]}", flush=True)
    print(f"{arm}: {len(done(arm))} done; judge labels asked {labels.asked}", flush=True)
    if _ROTATION is not None:
        print(f"host failures: {_ROTATION.failures}", flush=True)


def offline(answers: str, judge: str, labels_file: str) -> dict[str, dict[str, Any]]:
    """Stop 71's unchecked answers walked in drop mode from stop 71's labels alone, no call; an
    answer meeting a prompt with no label is left out."""
    pair = Pair(answers, judge, "", "", labels_file)
    labels = Labels(judge, labels_file)
    labels.by = {r["sha"]: r for r in read_jsonl(sota71.OUT / labels_file)}  # stop 71's only
    by_set = {s: {i["id"]: i for i in items(s)} for s in SETS}
    out: dict[str, dict[str, Any]] = {}
    for k, a in sota71.done(answers).items():
        item = by_set[a["set"]][a["id"]]
        try:
            out[k] = walk(item, a["text"], judge_for(pair, labels, offline=True), None)
        except MissingLabelError:
            continue
    return out


def rebuild() -> dict[str, Any]:
    """Pair A's drop arm walked again from stop 71's labels; it must equal stop 71's."""
    pair = PAIRS["A"]
    if pair.stop71_labels is None:
        raise SystemExit("pair A reuses stop 71's labels")
    old = sota71.done(pair.drop)
    walked = offline(pair.answers, pair.judge, pair.stop71_labels)
    same = sum(w["text"] == old[k]["text"] for k, w in walked.items())
    return {
        "answers": len(old),
        "same": same,
        "differ": len(walked) - same,
        "missing": len(old) - len(walked),
    }


def smoke() -> None:
    """Each host alone on one judge prompt, thinking off; then 2 questions per pair, one of them
    with its first sentence rejected in stop 71. The answers are kept."""
    flash = sota71.done("flash")
    by_set = {s: {i["id"]: i for i in items(s)} for s in SETS}
    a = next(iter(flash.values()))
    item = by_set[a["set"]][a["id"]]
    s = split_sentences(a["text"])[0].text
    premises = [p.text for p in item["premise"].passages[:3]]
    user = aj.short_prompt(s, premises, "")
    messages = [{"role": "system", "content": aj.SYSTEM}, {"role": "user", "content": user}]
    for host in hosted.HOSTS:
        try:
            out = hosted.call(host, messages, temperature=0.0, timeout=120)
        except Exception as exc:  # noqa: BLE001 - a smoke test reports every failure
            print(f"{host.name}: FAILED {hosted._describe(exc)}", flush=True)
            continue
        try:
            label = aj.parse_reply(out["content"])["label"]
        except (ValueError, json.JSONDecodeError):
            label = "unparsed"
        usage = out["usage"]
        print(
            f"{host.name}: {label} in {out['ms']:.0f} ms; completion tokens "
            f"{usage.get('completion_tokens')}; reply {out['content'][:160]!r}",
            flush=True,
        )
    picks = {}
    for name, (answers, judge, labels_file) in {
        "A": ("opus46", "flash", "labels.flash.jsonl"),
        "B": ("flash", "opus46", "labels.opus46.jsonl"),  # stop 71's rejections, to pick from
    }.items():
        walked = sorted(offline(answers, judge, labels_file).items())
        first = [k for k, w in walked if w["points"] and w["points"][0]["n"] == 0]
        later = [k for k, w in walked if w["points"] and w["points"][0]["n"] > 0]
        picks[name] = first[:1] + later[:1]
    picks_a, picks_b = picks["A"], picks["B"]
    print(f"smoke A: {picks_a}; smoke B: {picks_b}", flush=True)
    run("A", rewrite=True, only=picks_a, workers=1)
    run("B", rewrite=False, only=picks_b, workers=1)
    run("B", rewrite=True, only=picks_b, workers=1)


# ---------------------------------------------------------------------- readings


def copies(rewrite: str, source: str) -> bool:
    import retry_states  # type: ignore[import-not-found]  # noqa: PLC0415

    return bool(retry_states.copies(rewrite, source))


def mcnemar(only_a: int, only_b: int) -> float:
    from retry_report import mcnemar as exact  # type: ignore[import-not-found]  # noqa: PLC0415

    return float(exact(only_a, only_b))


def compare(
    rewrite: Sequence[Mapping[str, Any]], drop: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """The fixed readings, rewrite against drop, rows paired by question."""
    wrong = [int(r["wrong"] > 0) - int(d["wrong"] > 0) for r, d in zip(rewrite, drop, strict=True)]
    empty_r = [r["sentences"] == 0 for r in rewrite]
    empty_d = [d["sentences"] == 0 for d in drop]
    only_r = sum(a and not b for a, b in zip(empty_r, empty_d, strict=True))
    only_d = sum(b and not a for a, b in zip(empty_r, empty_d, strict=True))
    right = [r["right"] - d["right"] for r, d in zip(rewrite, drop, strict=True)]
    w_low, w_high = sota71.bootstrap(wrong)
    r_low, r_high = sota71.bootstrap(right)
    p_empty = mcnemar(only_r, only_d)
    keeps = w_high <= MARGIN
    fewer = only_r < only_d and p_empty < ALPHA
    more = r_low > 0
    return {
        "wrong": {
            "difference": round(sum(wrong) / len(wrong), 4),
            "interval_95": [w_low, w_high],
            "only_rewrite_wrong": sum(d == 1 for d in wrong),
            "only_drop_wrong": sum(d == -1 for d in wrong),
            "keeps": bool(keeps),
        },
        "empty": {
            "rewrite": sum(empty_r),
            "drop": sum(empty_d),
            "only_rewrite_empty": only_r,
            "only_drop_empty": only_d,
            "p": round(p_empty, 6),
            "fewer": bool(fewer),
        },
        "right": {
            "rewrite": sum(r["right"] for r in rewrite),
            "drop": sum(d["right"] for d in drop),
            "difference_per_answer": round(sum(right) / len(right), 4),
            "interval_95": [r_low, r_high],
            "more": bool(more),
        },
        "better_than_dropping": bool(keeps and fewer and more),
    }


def points_summary(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    points = [p for r in records for p in r.get("points", [])]
    outcomes = Counter(p["outcome"] for p in points)
    kept = [p for p in points if p["outcome"].startswith("try")]
    return {
        "rejected": len(points),
        "rejected_by": dict(Counter(p["by"] for p in points)),
        "outcomes": dict(sorted(outcomes.items())),
        "tries": sum(len(p["tries"]) for p in points),
        "empty_tries": sum(not t["text"] for p in points for t in p["tries"]),
        "rewrites_kept_copying_source": sum(
            copies(p["tries"][-1]["text"], p["source"]) for p in kept
        ),
        "rewrites_kept_repeating_a_kept_sentence": sum(bool(p.get("repeats_kept")) for p in kept),
    }


def seconds_drop_plus_rewrites(
    drop: Mapping[str, Mapping[str, Any]], rewrite: Mapping[str, Mapping[str, Any]]
) -> float:
    """Per answer: the drop arm's seconds plus every rewrite try's seconds; the median."""
    return float(
        round(
            statistics.median(
                float(drop[k].get("seconds") or 0)
                + sum(t["seconds"] for p in r["points"] for t in p["tries"])
                for k, r in rewrite.items()
            ),
            3,
        )
    )


def provider_split(judge: str) -> dict[str, int]:
    return dict(
        Counter(r.get("provider") or "?" for r in read_jsonl(OUT / f"labels.{judge}.jsonl"))
    )


def report() -> dict[str, Any]:
    import live68_grade as lg  # type: ignore[import-not-found]  # noqa: PLC0415

    lg.use(74)
    grades = lg.grades_by_sentence()
    by = lg.scored(grades)
    lg.STORE = sota71  # stop 71's arms, scored with the same grades
    by |= lg.scored(grades)
    questions = [f"{s}:{r['id']}" for s in SETS for r in rows(s)]
    out: dict[str, Any] = {"pairs": {}}
    for name, pair in PAIRS.items():
        table = {
            arm: [by[f"{arm}:{q}:none"] for q in questions]
            for arm in (pair.answers, pair.drop, pair.rewrite)
        }
        arms = {
            arm: {**lg.summary(r), "empty": sum(x["sentences"] == 0 for x in r)}
            for arm, r in table.items()
        }
        unchecked_right = arms[pair.answers]["right"]
        for arm in (pair.drop, pair.rewrite):
            arms[arm]["right_lost_against_unchecked"] = unchecked_right - arms[arm]["right"]
        drop_records = (
            offline(pair.answers, pair.judge, pair.stop71_labels)
            if pair.stop71_labels
            else done(pair.drop)
        )
        records = {
            pair.drop: list(drop_records.values()),
            pair.rewrite: list(done(pair.rewrite).values()),
        }
        out["pairs"][name] = {
            "answers": pair.answers,
            "judge": pair.judge,
            "rewriter": "flash",
            "arms": arms,
            "readings": compare(table[pair.rewrite], table[pair.drop]),
            "rewrite_points": points_summary(records[pair.rewrite]),
            "drop_points": points_summary(records[pair.drop]),
            "check_seconds_p50": {
                arm: round(statistics.median(r.get("check_seconds") or 0 for r in recs), 3)
                for arm, recs in {
                    pair.drop: list((done(pair.drop) or sota71.done(pair.drop)).values()),
                    pair.rewrite: records[pair.rewrite],
                }.items()
                if recs
            },
            # The rewrite arm reused the drop arm's labels, so its own seconds leave out the
            # judge's time on every sentence before a rejection: comparable is the drop arm's
            # seconds plus the time of the rewrite tries.
            "seconds_p50_drop_plus_rewrites": seconds_drop_plus_rewrites(
                (done(pair.drop) or sota71.done(pair.drop)), done(pair.rewrite)
            ),
        }
    out["qwen_judge_providers"] = provider_split("qwen27")
    REPORT.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["rebuild", "smoke", "drop", "rewrite", "report"])
    parser.add_argument("pair", nargs="?", choices=sorted(PAIRS))
    parser.add_argument("--workers", type=int, default=WORKERS)
    args = parser.parse_args()
    if args.command == "rebuild":
        print(json.dumps(rebuild()))
    elif args.command == "smoke":
        smoke()
    elif args.command in ("drop", "rewrite"):
        if args.pair is None:
            raise SystemExit("name the pair: A or B")
        run(args.pair, rewrite=args.command == "rewrite", workers=args.workers)
    else:
        out = report()
        print(json.dumps({k: v["readings"] for k, v in out["pairs"].items()}, indent=1))


if __name__ == "__main__":
    main()
