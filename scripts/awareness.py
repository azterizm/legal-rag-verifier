"""Stops 48 and 49: an awareness signal for the auditor (docs/GRID.md § Stops 48 and 49).

The measures are read on Modal (``scripts/awareness_replay.py``). This file builds what is sent,
and scores what comes back against your grades. Its top-level imports are stdlib only: the
container imports the helpers at the top.

  uv run --with modal modal run scripts/modal_distill.py::awareness         # stop 48 (paid)
  uv run python scripts/awareness.py report48     # → results/awareness/report48.json
  uv run --with modal modal run scripts/modal_distill.py::awareness_retry   # stop 49 (paid)
  uv run python scripts/awareness.py report49     # → results/awareness/report49.json
"""

from __future__ import annotations

import argparse
import functools
import json
import random
import statistics
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, TypeVar

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results/awareness"
CANDIDATES = ("att_all", "att_low", "att_mid", "att_high", "dep")
INPUT_SPANS = ("passages", "sentence")
FOLD_SEED = 20261010
PARSE_SEEDS = (0, 100, 200)
RETRY_SEEDS = (1, 2, 3, 4, 5)
GATE_EACH = 0.65
GATE_MEAN = 0.70
GAIN_POINTS = 1.0
JUDGES = ("k2-low", "qwen27-nothink")
T = TypeVar("T")


# ---------------------------------------------------------------------- helpers (also on Modal)


def token_spans(
    offsets: Sequence[Sequence[int]], ranges: Sequence[tuple[int, int]]
) -> list[list[int]]:
    """Token ranges covering the character ranges (a token counts if it overlaps one)."""
    spans = []
    for start, end in ranges:
        hit = [i for i, (s, e) in enumerate(offsets) if s < end and e > start]
        if hit:
            spans.append([hit[0], hit[-1] + 1])
    return spans


def partition(offsets: Sequence[Sequence[int]], ends: Sequence[int]) -> list[list[int]]:
    """Token indices per sentence: a token belongs to the sentence in which it starts. Tokens
    that start after the last sentence are left out."""
    groups: list[list[int]] = [[] for _ in ends]
    for i, (start, _) in enumerate(offsets):
        for n, end in enumerate(ends):
            if start < end:
                groups[n].append(i)
                break
    return groups


def summarise(m: Mapping[str, Any]) -> dict[str, float | None]:
    """The five candidates of one text. ``attention`` is a share per layer, or one per span."""
    out: dict[str, float | None] = dict.fromkeys(CANDIDATES)
    layers = m.get("attention")
    if isinstance(layers, Mapping):
        named = [layers[s] for s in INPUT_SPANS if s in layers]
        layers = [sum(v) for v in zip(*named, strict=True)] if named else None
    if layers:
        n = len(layers)
        low, high = n // 3, 2 * n // 3
        out["att_all"] = statistics.fmean(layers)
        out["att_low"] = statistics.fmean(layers[:low])
        out["att_mid"] = statistics.fmean(layers[low:high])
        out["att_high"] = statistics.fmean(layers[high:])
    if m.get("tokens") and m.get("logp") is not None and m.get("logp_without") is not None:
        out["dep"] = (m["logp"] - m["logp_without"]) / m["tokens"]
    return out


def auroc(right: Sequence[float], wrong: Sequence[float]) -> float | None:
    """P(a right item scores above a wrong one), ties half."""
    return auroc_within([(right, wrong)])


def auroc_within(strata: Sequence[tuple[Sequence[float], Sequence[float]]]) -> float | None:
    """AUROC over pairs of a right and a wrong item from the same stratum only."""
    wins = pairs = 0.0
    for right, wrong in strata:
        wins += sum((r > w) + 0.5 * (r == w) for r in right for w in wrong)
        pairs += len(right) * len(wrong)
    return round(wins / pairs, 4) if pairs else None


def folds(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Question id → fold 0 or 1, half of each domain in each fold."""
    out: dict[str, int] = {}
    rng = random.Random(FOLD_SEED)  # noqa: S311 - a split, not a secret
    for domain in sorted({r["domain"] for r in rows}):
        ids = sorted(r["id"] for r in rows if r["domain"] == domain)
        rng.shuffle(ids)
        half = len(ids) // 2
        out |= {i: int(n >= half) for n, i in enumerate(ids)}
    return out


def choose_candidate(scores: Mapping[str, float | None]) -> str | None:
    """The candidate with the highest AUROC; a tie goes to the earlier in ``CANDIDATES``."""
    have = [c for c in CANDIDATES if scores.get(c) is not None]
    return max(have, key=lambda c: scores[c] or 0.0) if have else None


def choose_threshold(
    items: Sequence[tuple[float, T]], gain: Callable[[list[T], list[T]], float]
) -> float:
    """The threshold with the highest ``gain(flagged, kept)``, an item being flagged when its
    value is under the threshold. A tie goes to the lower threshold."""
    values = sorted({v for v, _ in items})
    best, best_gain = float("-inf"), None
    for cut in [float("-inf"), *values[1:], float("inf")]:
        g = gain([p for v, p in items if v < cut], [p for v, p in items if v >= cut])
        if best_gain is None or g > best_gain:
            best, best_gain = cut, g
    return best


def gate(scores: Sequence[float | None]) -> bool:
    """Stop 48's gate over the two cross-fold AUROCs."""
    if any(s is None for s in scores):
        return False
    known = [s for s in scores if s is not None]
    return min(known) >= GATE_EACH and statistics.fmean(known) >= GATE_MEAN


def keep(attempts: Sequence[Mapping[str, Any]], threshold: float) -> dict[str, Any]:
    """Stop 49's rule over a clause's attempts, in order: the first at or over the threshold,
    else the one with the highest awareness (``exhausted``). An attempt with no measure, or
    whose reply never parsed, is used only when nothing else exists."""

    def value(a: Mapping[str, Any]) -> float:
        usable = a["awareness"] is not None and not a.get("unparsed")
        return float(a["awareness"]) if usable else float("-inf")

    for a in attempts:
        if value(a) >= threshold:
            return {**a, "exhausted": False}
    best = attempts[0]
    for a in attempts[1:]:
        if value(a) > value(best):
            best = a
    return {**best, "exhausted": True}


def read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def append_rows(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def attempts_of(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[int, dict[str, Any]]]:
    """``{sha: {attempt: sample}}``: per attempt the first sample that parsed, else the last one
    as not stated (``unparsed``)."""
    grouped: dict[str, dict[int, list[Mapping[str, Any]]]] = {}
    for r in rows:
        grouped.setdefault(r["sha"], {}).setdefault(r["attempt"], []).append(r)
    out: dict[str, dict[int, dict[str, Any]]] = {}
    for sha, by_attempt in grouped.items():
        out[sha] = {}
        for attempt, samples in by_attempt.items():
            ordered = sorted(samples, key=lambda r: r["seed"])
            parsed = [r for r in ordered if r["label"] != "error"]
            out[sha][attempt] = (
                {**parsed[0], "unparsed": False}
                if parsed
                else {**ordered[-1], "label": "not_stated", "passage": 0, "unparsed": True}
            )
    return out


# ---------------------------------------------------------------------- what is sent (laptop)


def _local() -> tuple[Any, Any, Any, Any]:
    sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT / "batteries/verifier")]
    import auditor_judge as aj  # type: ignore[import-not-found]  # noqa: PLC0415
    import fresh_battery as fb  # type: ignore[import-not-found]  # noqa: PLC0415
    import fresh_eval as fe  # type: ignore[import-not-found]  # noqa: PLC0415
    import fresh_report as fr  # type: ignore[import-not-found]  # noqa: PLC0415

    return aj, fb, fe, fr


def generator_items() -> list[dict[str, Any]]:
    """Per answer: both prompts of its question, the answer, where the source sits in the
    with-source system prompt, and where each sentence ends."""
    _, fb, _, _ = _local()
    from legal_rag_verifier.segmenter import split_sentences  # noqa: PLC0415

    rows = {r["id"]: r for r in fb.rows()}
    messages = {r["key"]: r["messages"] for r in fb.requests()}
    out = []
    for key, a in sorted(fb.answers().items()):
        row_id, _ = key.split(":")
        source = fb.source_text(rows[row_id])
        start = messages[f"{row_id}:source"][0]["content"].index(source)
        out.append(
            {
                "key": key,
                "with": messages[f"{row_id}:source"],
                "without": messages[f"{row_id}:closed"],
                "text": a["text"],
                "span": [start, start + len(source)],
                "ends": [s.end for s in split_sentences(a["text"])],
            }
        )
    return out


def judge_item(aj: Any, clause: str, candidates: Sequence[str], prefix: str) -> dict[str, Any]:
    """One clause: the stop 42 prompt, the same prompt without passages, and where the passages
    and the sentence sit in the first."""
    user = aj.user_prompt(clause, candidates, prefix)
    passages = "\n\n".join(f"[{n}] {text}" for n, text in enumerate(candidates, 1))
    shown = prefix or "(none)"
    head, rest = aj.USER.split("{passages}")
    middle, rest = rest.split("{prefix}")
    before, _ = rest.split("{sentence}")
    at = len(head)
    sentence_at = at + len(passages) + len(middle) + len(shown) + len(before)
    spans = {
        "passages": [at, at + len(passages)],
        "sentence": [sentence_at, sentence_at + len(clause)],
    }
    if any(
        user[s:e] != text for (s, e), text in zip(spans.values(), (passages, clause), strict=True)
    ):
        raise RuntimeError("judge prompt spans do not match the prompt")
    return {
        "sha": aj.prompt_key(user),
        "user": user,
        "blank": aj.USER.format(passages="(none)", prefix=shown, sentence=clause),
        "spans": spans,
    }


@functools.cache
def judge_items() -> dict[str, dict[str, Any]]:
    """``{sha: item}`` for the 323 fresh clause prompts; ``unit`` is the sentence it checks."""
    aj, _, fe, _ = _local()
    us, _, rec = fe.recorded()
    out = {}
    for u, r in zip(us, rec, strict=True):
        for clause, candidates in r["calls"]:
            item = judge_item(aj, clause, candidates, r["prefix"])
            out[item["sha"]] = {**item, "unit": u["key"]}
    return out


# ---------------------------------------------------------------------- scoring (laptop)


def _graded() -> tuple[Any, ...]:
    aj, fb, fe, fr = _local()
    graded = fe.grades()
    us, built, rec = fe.recorded()
    by_key = {u["key"]: u for u in us}
    units = [
        {**by_key[k], "right": g == "yes", "wrong": g == "no"}
        for k, g in graded.items()
        if g != "unsure"
    ]
    fold = folds(fb.rows())
    for u in units:
        u["fold"] = fold[u["id"]]
    return aj, fe, fr, us, built, rec, units


def _split(items: Sequence[Mapping[str, Any]], c: str) -> tuple[list[float], list[float]]:
    right = [i["values"][c] for i in items if i["right"] and i["values"][c] is not None]
    wrong = [i["values"][c] for i in items if not i["right"] and i["values"][c] is not None]
    return right, wrong


def separation(
    items: Sequence[Mapping[str, Any]], strata: str | None = None
) -> dict[str, float | None]:
    """AUROC of each candidate over ``items`` (``right`` and ``values``); within ``strata`` when
    a key is named."""
    out = {}
    for c in CANDIDATES:
        if strata is None:
            out[c] = auroc(*_split(items, c))
        else:
            names = sorted({i[strata] for i in items})
            out[c] = auroc_within([_split([i for i in items if i[strata] == n], c) for n in names])
    return out


def cross_fold(
    items: Sequence[Mapping[str, Any]], strata: str | None = None
) -> dict[str, dict[str, Any]]:
    """Per fold: the candidate chosen on it, and that candidate's AUROC on the other fold."""
    out = {}
    for f in (0, 1):
        tuned = separation([i for i in items if i["fold"] == f], strata)
        chosen = choose_candidate(tuned)
        other = separation([i for i in items if i["fold"] != f], strata)
        out[str(f)] = {
            "candidate": chosen,
            "auroc_tuning": tuned,
            "auroc_other_fold": other[chosen] if chosen else None,
        }
    return out


def _accuracy(flagged: list[Mapping[str, Any]], kept: list[Mapping[str, Any]]) -> float:
    """Sentences decided correctly when the flagged ones are rolled back."""
    return float(
        sum(not i["right"] for i in flagged)
        + sum((not i["right"]) if i["claim"] else i["right"] for i in kept)
    )


def _youden(flagged: list[Mapping[str, Any]], kept: list[Mapping[str, Any]]) -> float:
    right = sum(bool(i["right"]) for i in flagged) + sum(bool(i["right"]) for i in kept)
    wrong = len(flagged) + len(kept) - right
    flagged_right = sum(bool(i["right"]) for i in flagged)
    return (len(flagged) - flagged_right) / max(wrong, 1) - flagged_right / max(right, 1)


def _threshold(
    items: Sequence[Mapping[str, Any]],
    c: str,
    gain: Callable[[list[Mapping[str, Any]], list[Mapping[str, Any]]], float],
) -> float:
    return choose_threshold(
        [(i["values"][c], i) for i in items if i["values"][c] is not None], gain
    )


def _percentiles(values: Sequence[float]) -> dict[str, Any]:
    ordered = sorted(values)
    if not ordered:
        return {"n": 0}
    return {
        "n": len(ordered),
        "p50": round(ordered[len(ordered) // 2], 3),
        "p95": round(ordered[int(0.95 * len(ordered))], 3),
        "mean": round(statistics.fmean(ordered), 3),
    }


def generator_report(ctx: tuple[Any, ...]) -> dict[str, Any]:
    aj, fe, fr, us, built, _, units = ctx
    rows = {r["key"]: r for r in read_rows(OUT / "generator.jsonl")}
    values = {
        f"{key}:{n}": summarise(s) for key, r in rows.items() for n, s in enumerate(r["sentences"])
    }
    missing = [u["key"] for u in units if u["key"] not in values]
    if missing:
        return {"missing": len(missing)}
    v0 = aj.replay(
        us, built, aj.TableScorer("v0", json.loads((fe.OUT / "scores/v0.json").read_text()))
    )
    claim = {
        k: v["verdict"] != "EMIT" and not set(v["reasons"]) <= aj.NLI_REASONS for k, v in v0.items()
    }
    items = [{**u, "values": values[u["key"]], "claim": False} for u in units]
    report: dict[str, Any] = {
        "sentences": len(items),
        "no_measure": {c: sum(i["values"][c] is None for i in items) for c in CANDIDATES},
    }
    groups = {
        "total": items,
        "software": [i for i in items if i["domain"] == "software"],
        "statutes": [i for i in items if i["domain"] == "legal"],
        "with source": [i for i in items if i["mode"] == "source"],
        "closed-book": [i for i in items if i["mode"] == "closed"],
    }
    report["A1"] = {name: separation(group) for name, group in groups.items()}
    report["A1"]["within kind"] = separation(items, "mode")
    report["A1"]["counts"] = {
        name: [sum(i["right"] for i in g), sum(not i["right"] for i in g)]
        for name, g in groups.items()
    }
    report["folds"] = cross_fold(items, "mode")
    scores = [report["folds"][f]["auroc_other_fold"] for f in ("0", "1")]
    report["gate"] = {"auroc_other_fold": scores, "passes": gate(scores)}
    # Not the gate: the same choice over all pairs, where the kind of answer helps the signal.
    report["folds_total_not_the_gate"] = cross_fold(items)

    # A3: the signal as the auditor, thresholds from the other fold.
    report["A3"] = {}
    for arm, with_claim in (("signal alone", False), ("claim check then signal", True)):
        armed = [{**i, "claim": with_claim and claim[i["key"]]} for i in items]
        verdicts = {k: {"verdict": "EMIT", "reasons": []} for k in claim}
        used = {}
        for f in ("0", "1"):
            c = report["folds"][f]["candidate"]
            if c is None:
                continue
            cut = _threshold([i for i in armed if i["fold"] == int(f)], c, _accuracy)
            used[f] = {"candidate": c, "threshold": cut}
            for i in armed:
                low = i["values"][c] is not None and i["values"][c] < cut
                if i["fold"] != int(f) and (i["claim"] or low):
                    verdicts[i["key"]] = {"verdict": "ROLLBACK", "reasons": []}
        report["A3"][arm] = {"chosen": used, **fr.score(units, verdicts)}
    source = groups["with source"]
    picked = cross_fold(source)
    rolled: dict[str, bool] = {}
    for f in ("0", "1"):
        c = picked[f]["candidate"]
        if c is None:
            continue
        cut = _threshold([i for i in source if i["fold"] == int(f)], c, _accuracy)
        picked[f]["threshold"] = cut
        rolled |= {
            i["key"]: i["values"][c] is not None and i["values"][c] < cut
            for i in source
            if i["fold"] != int(f)
        }
    report["A3"]["with source only, signal alone"] = {
        "chosen": picked,
        **aj.counts(
            [{**i, "rolled": rolled.get(i["key"], False), "by_nli": False} for i in source]
        ),
    }

    # A4 and the check on the replay.
    per_sentence = [
        (r["s_with"] + r["s_without"]) / max(len(r["sentences"]), 1) for r in rows.values()
    ]
    report["A4"] = {
        "s_per_sentence": _percentiles(per_sentence),
        "s_with_per_answer": _percentiles([r["s_with"] for r in rows.values()]),
        "s_without_per_answer": _percentiles([r["s_without"] for r in rows.values()]),
    }
    top = Counter[str]()
    for key, r in rows.items():
        written = "top1_match" if key.endswith(":source") else "top1_match_without"
        top["tokens"] += sum(s["tokens"] for s in r["sentences"])
        top["top"] += sum(s[written] for s in r["sentences"])
    report["top_token_share"] = round(top["top"] / max(top["tokens"], 1), 4)
    return report


def judge_labels(name: str) -> dict[str, dict[int, dict[str, Any]]]:
    rows = read_rows(OUT / f"{name}.jsonl") + read_rows(OUT / f"{name}-retry.jsonl")
    return attempts_of(rows)


def _clauses(
    units: Sequence[Mapping[str, Any]], labels: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """One item per clause of a graded sentence: is its label right, and its five values."""
    by_key = {u["key"]: u for u in units}
    out = []
    for sha, item in judge_items().items():
        u = by_key.get(item["unit"])
        if u is None or sha not in labels:
            continue
        label = labels[sha]
        out.append(
            {
                "sha": sha,
                "key": u["key"],
                "fold": u["fold"],
                "domain": u["domain"],
                "label": label["label"],
                "sentence_right": u["right"],
                "right": (label["label"] == "supported") == u["right"],
                "values": summarise(label),
            }
        )
    return out


def _arm(
    ctx: tuple[Any, ...], name: str, labels: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    aj, _, fr, us, built, _, units = ctx
    out = {}
    for placement, config in (("strict", aj.STRICT), ("replace", aj.DEFAULT)):
        out[placement] = fr.score(units, aj.replay(us, built, aj.JudgeScorer(name, labels), config))
    return out


def judge_report(ctx: tuple[Any, ...], name: str) -> dict[str, Any]:
    aj, fe, _, _, _, rec, units = ctx
    asked = aj.requests(rec)
    first = {sha: a[0] for sha, a in judge_labels(name).items() if 0 in a}
    missing = [sha for sha in asked if sha not in first]
    if missing:
        return {"missing": len(missing)}
    recorded = fe.read(name)
    items = _clauses(units, first)
    report: dict[str, Any] = {
        "clauses": len(items),
        "labels": dict(Counter(i["label"] for i in items)),
        "right_labels": sum(i["right"] for i in items),
        "unparsed": sum(a["unparsed"] for a in first.values()),
        "attention_read": sum(a.get("attention") is not None for a in first.values()),
        "same_as_recorded": sum(first[s]["label"] == recorded[s]["label"] for s in asked),
        "prompts": len(asked),
    }
    supported = [i for i in items if i["label"] == "supported"]
    report["A2"] = {
        "total": separation(items),
        "software": separation([i for i in items if i["domain"] == "software"]),
        "statutes": separation([i for i in items if i["domain"] == "legal"]),
        "supported labels": separation(supported),
        "counts": {
            "total": [sum(i["right"] for i in items), sum(not i["right"] for i in items)],
            "supported labels": [
                sum(i["right"] for i in supported),
                sum(not i["right"] for i in supported),
            ],
        },
    }
    report["folds"] = cross_fold(items)
    for f in ("0", "1"):
        c = report["folds"][f]["candidate"]
        if c is not None:
            tuning = [i for i in items if i["fold"] == int(f)]
            report["folds"][f]["threshold"] = _threshold(tuning, c, _youden)
    scores = [report["folds"][f]["auroc_other_fold"] for f in ("0", "1")]
    report["gate"] = {"auroc_other_fold": scores, "passes": gate(scores)}
    report["arms"] = {
        "attempt 1 (transformers)": _arm(ctx, name, first),
        "recorded (SGLang, stop 47)": _arm(ctx, name, recorded),
    }
    report["A4"] = {
        "s_generate_per_clause": _percentiles([a["s_generate"] for a in first.values()]),
        "s_measure_per_clause": _percentiles([a["s_measure"] for a in first.values()]),
        "tokens": _percentiles([a["tokens"] for a in first.values()]),
    }
    return report


def report48() -> dict[str, Any]:
    ctx = _graded()
    report = {
        "units": len(ctx[-1]),
        "generator": generator_report(ctx),
        "judges": {name: judge_report(ctx, name) for name in JUDGES},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report48.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    return report


# ---------------------------------------------------------------------- stop 49


def retry_plan(name: str) -> dict[str, dict[str, Any]]:
    """Per clause of a gated judge: the candidate and threshold of the other fold, and whether
    attempt 1 is under it. Uses no grade beyond the committed stop 48 report."""
    report = json.loads((OUT / "report48.json").read_text(encoding="utf-8"))["judges"][name]
    if not report.get("gate", {}).get("passes"):
        return {}
    _, fb, fe, _ = _local()
    fold = folds(fb.rows())
    by_key = {u["key"]: u for u in fe.units()}
    first = {sha: a[0] for sha, a in judge_labels(name).items()}
    plan = {}
    for sha, item in judge_items().items():
        chosen = report["folds"][str(1 - fold[by_key[item["unit"]]["id"]])]
        value = summarise(first[sha])[chosen["candidate"]]
        plan[sha] = {
            "candidate": chosen["candidate"],
            "threshold": chosen["threshold"],
            "awareness": value,
            "retry": value is not None and value < chosen["threshold"],
        }
    return plan


def kept_labels(name: str) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """The label kept per clause after the loop, and the loop's counts."""
    plan = retry_plan(name)
    tried = judge_labels(name)
    kept: dict[str, dict[str, Any]] = {}
    stats: Counter[str] = Counter()
    seconds = []
    for sha, p in plan.items():
        ordered = [
            {**a, "awareness": summarise(a)[p["candidate"]]} for _, a in sorted(tried[sha].items())
        ]
        if not p["retry"]:
            kept[sha] = {**ordered[0], "exhausted": False}
            seconds.append(0.0)
            continue
        if len(ordered) == 1:
            raise RuntimeError(f"{name}: clause {sha[:8]} is under its threshold and has no retry")
        kept[sha] = keep(ordered, p["threshold"])
        stats["retried"] += 1
        stats["exhausted"] += kept[sha]["exhausted"]
        stats["extra_attempts"] += len(ordered) - 1
        stats["label_changed"] += kept[sha]["label"] != ordered[0]["label"]
        seconds.append(sum(a["s_generate"] + a["s_measure"] for a in ordered[1:]))
    return kept, {**stats, "clauses": len(plan), "s_added_per_clause": _percentiles(seconds)}


def report49() -> dict[str, Any]:
    ctx = _graded()
    units = ctx[-1]
    report: dict[str, Any] = {"units": len(units), "judges": {}}
    for name in JUDGES:
        if not retry_plan(name):
            report["judges"][name] = {"gate": "not passed, no loop"}
            continue
        kept, stats = kept_labels(name)
        first = {sha: a[0] for sha, a in judge_labels(name).items()}
        before = {i["sha"]: i["right"] for i in _clauses(units, first)}
        after = {i["sha"]: i["right"] for i in _clauses(units, kept)}
        arms = {"attempt 1": _arm(ctx, name, first), "retry loop": _arm(ctx, name, kept)}
        gain = 100 * (
            arms["retry loop"]["strict"]["total"]["accuracy"]
            - arms["attempt 1"]["strict"]["total"]["accuracy"]
        )
        report["judges"][name] = {
            "B1": {**arms, "gain_points": round(gain, 1), "gain": gain >= GAIN_POINTS},
            "B2": {
                **{k: v for k, v in stats.items() if k != "s_added_per_clause"},
                "to_right": sum(after[s] and not before[s] for s in before),
                "to_wrong": sum(before[s] and not after[s] for s in before),
            },
            "B3": stats["s_added_per_clause"],
        }
    (OUT / "report49.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    return report


def _show(report: Mapping[str, Any]) -> None:
    g = report["generator"]
    if "A1" in g:
        for name, scores in g["A1"].items():
            print(f"G {name:14} {scores}")
        print("G folds", json.dumps(g["folds"]), g["gate"])
        for arm, s in g["A3"].items():
            total = s.get("total", s)
            print(f"G {arm:32} {total['false_rollbacks']}/{total['caught']} {total['accuracy']}")
        print("G top-token share", g["top_token_share"], g["A4"]["s_per_sentence"])
    else:
        print("G", g)
    for name, j in report["judges"].items():
        if "A2" not in j:
            print(name, j)
            continue
        print(name, {k: v for k, v in j.items() if not isinstance(v, dict)}, j["labels"])
        for group, scores in j["A2"].items():
            print(f"  {group:18} {scores}")
        print("  folds", json.dumps(j["folds"]), j["gate"])
        for arm, s in j["arms"].items():
            cells = "  ".join(
                f"{p}: {s[p]['total']['false_rollbacks']}/{s[p]['total']['caught']} "
                f"{s[p]['total']['accuracy']}"
                for p in s
            )
            print(f"  {arm:28} {cells}")
        print("  A4", j["A4"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["items", "report48", "report49"])
    command = parser.parse_args().command
    if command == "items":
        g, j = generator_items(), judge_items()
        print(json.dumps({"answers": len(g), "clauses": len(j)}))
    elif command == "report48":
        _show(report48())
    else:
        print(json.dumps(report49(), indent=1))


if __name__ == "__main__":
    main()
