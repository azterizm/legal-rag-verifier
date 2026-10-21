"""Stop 73: ConSens per sentence (docs/GRID.md § Stop 73).

ConSens (Vankov, Ivanov, Correia and Botev 2025, arXiv 2505.00065) compares the perplexity of a text
after its source with its perplexity after an empty source, read from a small evaluator model:
Llama 3.2 1B Instruct, as in the paper. Here the text is one sentence, after the question and the
answer so far. The scores are read on Modal (``scripts/modal_distill.py`` § stop 73). This file
builds what is sent, and scores what comes back against your grades. Its top-level imports are
stdlib only: the container imports it for ``measure``.

  FRESH_SET=fresh uv run --with modal modal run scripts/modal_distill.py::consens --limit 5  # smoke
  FRESH_SET=fresh uv run --with modal modal run scripts/modal_distill.py::consens   # first test
  FRESH_SET=fresh uv run python scripts/consens.py calibrate   # → results/fresh_arms/consens.json
  FRESH_SET=fresh2 uv run --with modal modal run scripts/modal_distill.py::consens  # second test
  FRESH_SET=fresh2 uv run python scripts/consens.py report     # → results/fresh2_arms/consens.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import statistics
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import awareness as aw  # type: ignore[import-not-found]  # noqa: E402

MODEL = "meta-llama/Llama-3.2-1B-Instruct"  # the paper's footnote 1
REVISION = "9213176726f574b556790deb65791e0c5aa438b6"  # read from the Hub on 2026-10-21
# The paper's template (§ 3, six lines in the arXiv HTML), as raw text; the answer after "Answer:".
TEMPLATE = (
    "Consider the following context:\nContext:\n{context}\n"
    "Please answer the following question:\n{question}\nAnswer: "
)
WORD = re.compile(r"[A-Za-z0-9]+(?:['’.\-][A-Za-z0-9]+)*")
# Closed-class words (the paper: "pronouns, determiners, and conjunctions", punctuation; its list is
# not published). Prepositions are closed-class too. Auxiliaries and negation are kept: the paper's
# example drops "is" only because the question holds it.
_CLOSED_WORDS = """
    i me my mine myself we us our ours ourselves you your yours yourself yourselves he him his
    himself she her hers herself it its itself they them their theirs themselves who whom whose
    which what whoever whatever whichever anyone anything everyone everything someone something
    nobody nothing
    a an the this that these those some any no every each either neither all both another such
    and or but nor so yet if because although though while whereas unless until since whether than
    as when where
    about above across after against along amid among around at before behind below beneath beside
    besides between beyond by despite down during except for from in inside into like near of off
    on onto out outside over past per regarding through throughout to toward towards under
    underneath unlike up upon via with within without
"""
CLOSED = frozenset(_CLOSED_WORDS.split())
WARMUP = 10  # calls measured and dropped before the timed run
SET = os.environ.get("FRESH_SET", "fresh")
DEV, TEST = "fresh", "fresh2"
JUDGE = "qwen27-ar4"  # stop 61: short reply, figures to the judge
# The committed figures the comparison rows must reproduce (stops 60 and 61), second test.
AS_COMMITTED = {"judge": 0.901, "V0": 0.583, "claim check only": 0.623, "no auditor": 0.556}
# sha256 of results/fresh_arms/consens.json once the thresholds are fixed (commit 2, GRID).
THRESHOLDS_SHA = ""


# ---------------------------------------------------------------------- helpers (also on Modal)


def kept(sentence: str, question: str) -> tuple[list[tuple[int, int]], bool]:
    """Character ranges of the sentence's words that are scored, and whether the fallback was
    used: every word of the sentence when none is left after the closed-class and question
    words are dropped."""
    asked = {m[0].casefold() for m in WORD.finditer(question)}
    words = list(WORD.finditer(sentence))
    keep = [m.span() for m in words if m[0].casefold() not in CLOSED | asked]
    if keep or not words:
        return keep, False
    return [m.span() for m in words], True


def prompt(context: str, question: str, prefix: str) -> str:
    """Everything before the sentence: the template, then the answer so far."""
    head = TEMPLATE.format(context=context, question=question)
    return f"{head}{prefix} " if prefix else head


def perplexity(logps: Sequence[float]) -> float | None:
    """The paper's text perplexity: the mean over tokens of 1 / p(token)."""
    return statistics.fmean(math.exp(-lp) for lp in logps) if logps else None


def score(ppl_empty: float | None, ppl_context: float | None) -> float | None:
    """ConSens = 2 / (1 + e^-r) - 1 with r = ln(P_E / P_C); written as tanh(r / 2)."""
    if ppl_empty is None or ppl_context is None:
        return None
    return math.tanh((math.log(ppl_empty) - math.log(ppl_context)) / 2)


def load(revision: str = REVISION, device: str = "cuda") -> tuple[Any, Any, Any]:
    import torch  # noqa: PLC0415
    import transformers  # noqa: PLC0415

    tokenizer = transformers.AutoTokenizer.from_pretrained(MODEL, revision=revision)
    model: Any = transformers.AutoModelForCausalLM.from_pretrained(
        MODEL, revision=revision, dtype=torch.bfloat16, device_map=device
    )
    model.eval()
    return model, tokenizer, torch


def _logps(model: Any, tokenizer: Any, torch: Any, head: str, item: Mapping[str, Any]) -> Any:
    """Log-probabilities of the scored tokens of the sentence after ``head``."""
    text = head + item["sentence"]
    enc = tokenizer(text, return_offsets_mapping=True)  # with the BOS token, as the model reads
    ids, offsets = list(enc["input_ids"]), [(int(s), int(e)) for s, e in enc["offset_mapping"]]
    start = len(head)
    ranges = [(start + s, start + e) for s, e in item["keep"]]
    chosen = sorted({i for a, b in aw.token_spans(offsets, ranges) for i in range(a, b)})
    if not chosen:
        return [], len(ids)
    keep = len(ids) - chosen[0] + 1  # the logits that predict the first scored token onwards
    base = len(ids) - keep
    with torch.no_grad():
        logits = model(
            input_ids=torch.tensor([ids], device=model.device), logits_to_keep=keep
        ).logits[0]
    logp = torch.log_softmax(logits.float(), -1)
    return [round(float(logp[i - 1 - base, ids[i]]), 6) for i in chosen], len(ids)


def measure(model: Any, tokenizer: Any, torch: Any, item: Mapping[str, Any]) -> dict[str, Any]:
    """One sentence, both conditions. The time covers tokenisation, both forward passes and the
    log-softmax, device-synchronised (CUDA; the CPU test needs no sync)."""
    sync = torch.cuda.synchronize if torch.cuda.is_available() else lambda: None
    sync()
    t0 = time.perf_counter_ns()
    with_source, prompt_tokens = _logps(model, tokenizer, torch, item["with"], item)
    without, _ = _logps(model, tokenizer, torch, item["without"], item)
    sync()
    return {
        "key": item["key"],
        "sha": item["sha"],
        "logp_context": with_source,
        "logp_empty": without,
        "prompt_tokens": prompt_tokens,
        "ms": round((time.perf_counter_ns() - t0) / 1e6, 2),
    }


def measure_all(
    model: Any, tokenizer: Any, torch: Any, items: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    for item in items[:WARMUP]:
        measure(model, tokenizer, torch, item)
    return [measure(model, tokenizer, torch, item) for item in items]


def entry(row: Mapping[str, Any], *, fallback: bool) -> dict[str, Any]:
    """A row from the container as kept in the scores file (no text)."""
    pc, pe = perplexity(row["logp_context"]), perplexity(row["logp_empty"])
    value = score(pe, pc)
    return {
        "sha": row["sha"],
        "consens": None if value is None else round(value, 6),
        "ppl_context": pc,
        "ppl_empty": pe,
        "tokens": len(row["logp_context"]),
        "fallback": fallback,
        "prompt_tokens": row["prompt_tokens"],
        "ms": row["ms"],
        "logp_context": row["logp_context"],
        "logp_empty": row["logp_empty"],
    }


# ---------------------------------------------------------------------- laptop


def _local() -> tuple[Any, Any, Any, Any]:
    sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT / "batteries/verifier")]
    import auditor_judge as aj  # type: ignore[import-not-found]  # noqa: PLC0415
    import fresh_arms as fa  # type: ignore[import-not-found]  # noqa: PLC0415
    import fresh_eval as fe  # type: ignore[import-not-found]  # noqa: PLC0415
    import fresh_report as fr  # type: ignore[import-not-found]  # noqa: PLC0415

    return aj, fa, fe, fr


def scores_path(*, probe: bool = False) -> Path:
    """The scores of this set; a probe (the smoke run) is kept apart and is not a result."""
    return ROOT / "results" / SET / "scores" / ("consens.probe.json" if probe else "consens.json")


def read_scores(*, probe: bool = False) -> dict[str, dict[str, Any]]:
    path = scores_path(probe=probe)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_scores(
    rows: Mapping[str, Mapping[str, Any]], run: Mapping[str, Any], *, probe: bool = False
) -> None:
    """Rows merged into the scores file; each run appended to its meta file."""
    path = scores_path(probe=probe)
    path.parent.mkdir(parents=True, exist_ok=True)
    have = read_scores(probe=probe) | dict(rows)
    path.write_text(json.dumps(dict(sorted(have.items())), indent=1) + "\n", encoding="utf-8")
    meta = path.with_suffix(".meta.json")
    runs = json.loads(meta.read_text(encoding="utf-8"))["runs"] if meta.exists() else []
    meta.write_text(json.dumps({"runs": [*runs, run]}, indent=1) + "\n", encoding="utf-8")


def items(data: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """Per segmenter sentence: both prompts, the sentence and the ranges scored. No grade."""
    if data is None:
        _, fa, _, _ = _local()
        data = fa.recorded()
    out = []
    for u in data["units"]:
        keep, fallback = kept(u["sentence"], u["query"])
        item = {
            "key": u["key"],
            "with": prompt(data["sources"][u["key"]], u["query"], u["prefix"]),
            "without": prompt("", u["query"], u["prefix"]),
            "sentence": u["sentence"],
            "keep": keep,
            "fallback": fallback,
        }
        blob = json.dumps(item, sort_keys=True, ensure_ascii=False)
        out.append({**item, "sha": hashlib.sha256(blob.encode()).hexdigest()})
    return out


def _graded(fa: Any, fe: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The recorded units and the graded ones, each with its ConSens value and claim check."""
    data = fa.recorded()
    graded = fe.merged_grades(data["units"])
    table = read_scores()
    expected = {i["key"]: i["sha"] for i in items(data)}
    stale = [k for k, sha in expected.items() if k in table and table[k]["sha"] != sha]
    missing = [k for k in expected if k not in table]
    if stale or missing:
        raise RuntimeError(f"consens scores: {len(missing)} missing, {len(stale)} stale")
    units = [
        {
            **u,
            "right": graded[u["key"]] == "yes",
            "wrong": graded[u["key"]] == "no",
            "value": table[u["key"]]["consens"],
            "claim": bool(data["calls"][u["key"]]["claim_rollback"]),
        }
        for u in data["units"]
    ]
    return data, [u for u in units if u["right"] or u["wrong"]]


def threshold(units: Sequence[Mapping[str, Any]], *, claim: bool) -> float:
    """The value with the highest accuracy, ties to the lower (stop 48's A3 rule). A sentence
    with no value is never rolled back by ConSens."""
    armed = [{**u, "claim": claim and u["claim"]} for u in units if u["value"] is not None]
    return float(aw.choose_threshold([(u["value"], u) for u in armed], aw._accuracy))


def verdicts(
    units: Sequence[Mapping[str, Any]], cut: float, *, claim: bool
) -> dict[str, dict[str, Any]]:
    """Rolled back when the claim check holds it (arm A) or ConSens is under the threshold."""
    out: dict[str, dict[str, Any]] = {}
    for u in units:
        low = u["value"] is not None and u["value"] < cut
        rolled = low or (claim and u["claim"])
        out[u["key"]] = {"verdict": "ROLLBACK" if rolled else "EMIT", "reasons": []}
    return out


ARMS = {"claim check then ConSens": True, "ConSens alone": False}


def separation(units: Sequence[Mapping[str, Any]], aj: Any) -> dict[str, Any]:
    """AUROC of ConSens, right sentences above wrong ones: in total with a bootstrap interval,
    within the kind of answer, and per kind."""

    def split(us: Sequence[Mapping[str, Any]]) -> tuple[list[float], list[float]]:
        right = [u["value"] for u in us if u["right"] and u["value"] is not None]
        return right, [u["value"] for u in us if u["wrong"] and u["value"] is not None]

    kinds = {m: [u for u in units if u["mode"] == m] for m in ("source", "closed")}
    return {
        "total": aj.auc_interval(*split(units)),
        "within kind": aw.auroc_within([split(us) for us in kinds.values()]),
        **{f"{m} answers": aw.auroc(*split(us)) for m, us in kinds.items()},
    }


def calibrate() -> None:
    """The thresholds, on the first test only. → results/fresh_arms/consens.json"""
    if SET != DEV:
        raise SystemExit(f"calibrate runs on FRESH_SET={DEV}")
    aj, fa, fe, fr = _local()
    _, units = _graded(fa, fe)
    source = [u for u in units if u["mode"] == "source"]
    out: dict[str, Any] = {"set": SET, "sentences": len(units), "thresholds": {}, "arms": {}}
    for arm, claim in ARMS.items():
        cut, cut_source = threshold(units, claim=claim), threshold(source, claim=claim)
        out["thresholds"][arm] = {"all": cut, "with source": cut_source}
        out["arms"][arm] = fr.score(units, verdicts(units, cut, claim=claim))
    out["auroc"] = separation(units, aj)
    out["scores_sha256"] = hashlib.sha256(scores_path().read_bytes()).hexdigest()
    path = ROOT / "results" / f"{SET}_arms" / "consens.json"
    path.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("thresholds", "auroc")}, indent=1))
    print(f"sha256 {hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(ROOT)}")


def _fixed() -> dict[str, Any]:
    path = ROOT / "results" / f"{DEV}_arms" / "consens.json"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if not THRESHOLDS_SHA or digest != THRESHOLDS_SHA:
        raise SystemExit(f"thresholds not sealed: {path.relative_to(ROOT)} is {digest}")
    fixed: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))["thresholds"]
    return fixed


def _comparisons(
    aj: Any, fa: Any, fe: Any, data: Mapping[str, Any]
) -> dict[str, dict[str, dict[str, Any]]]:
    """The committed arms, rebuilt as stops 60 and 61 built them."""
    us, built = data["units"], data["built"]
    labels = fa.read(JUDGE, "short")
    scorer = fa.Scorer(JUDGE, "short", labels, data["sources"])
    judge = fa.replay(us, built, scorer, set(), aj.STRICT_FIGURES)
    graded_us, graded_built, _ = fe.recorded()
    table = json.loads((fe.OUT / "scores/v0.json").read_text(encoding="utf-8"))
    v0 = aj.replay(graded_us, graded_built, aj.TableScorer("v0", table))
    emit = {"verdict": "EMIT", "reasons": []}
    return {
        "judge": judge,
        "V0": v0,
        "claim check only": {
            k: emit if set(v["reasons"]) <= aj.NLI_REASONS else v for k, v in v0.items()
        },
        "no auditor": dict.fromkeys(v0, emit),
    }


def report() -> None:
    """Stop 73 on the second test, once, with the thresholds fixed on the first.
    → results/fresh2_arms/consens.json"""
    if SET != TEST:
        raise SystemExit(f"report runs on FRESH_SET={TEST}")
    fixed = _fixed()
    aj, fa, fe, fr = _local()
    data, units = _graded(fa, fe)
    others = _comparisons(aj, fa, fe, data)
    for name, want in AS_COMMITTED.items():
        got = fr.score(units, others[name])["total"]["accuracy"]
        if got != want:
            raise RuntimeError(f"{name}: {got} here, {want} as committed")
    source = [u for u in units if u["mode"] == "source"]
    arms: dict[str, dict[str, dict[str, Any]]] = {}
    for arm, claim in ARMS.items():
        arms[arm] = verdicts(units, fixed[arm]["all"], claim=claim)
        arms[f"{arm}, paper's cut 0"] = verdicts(units, 0.0, claim=claim)
    out: dict[str, Any] = {"set": SET, "sentences": len(units), "thresholds": fixed, "arms": {}}
    correct = {}
    for name, v in {**arms, **others}.items():
        s = fr.score(units, v)
        hits = s["total"]["right"] - s["total"]["false_rollbacks"] + s["total"]["caught"]
        s["total"]["interval_95"] = fa.wilson(hits, len(units))
        out["arms"][name] = s
        correct[name] = {u["key"]: fr._rolled(v[u["key"]]) == u["wrong"] for u in units}
    out["with source only"] = {}
    for arm, claim in ARMS.items():
        v = verdicts(source, fixed[arm]["with source"], claim=claim)
        rows = [{**u, "rolled": fr._rolled(v[u["key"]]), "by_nli": False} for u in source]
        out["with source only"][arm] = aj.counts(rows)
    out["auroc"] = separation(units, aj)
    judge_acc = out["arms"]["judge"]["total"]["accuracy"]
    v0_acc = out["arms"]["V0"]["total"]["accuracy"]
    out["paired"], out["fixed_reading"] = {}, {}
    for arm in ARMS:
        acc = out["arms"][arm]["total"]["accuracy"]
        tests = {other: fa.paired(correct[arm], correct[other]) for other in others}
        out["paired"][arm] = tests
        out["fixed_reading"][arm] = {
            "near_the_judge": bool(judge_acc - acc <= fa.NEAR and tests["judge"]["p"] >= fa.ALPHA),
            "clearly_above_V0": bool(acc - v0_acc >= fa.ABOVE_V0),
        }
    table = read_scores()
    measured = [table[u["key"]] for u in data["units"]]
    out["values"] = {
        "no_value": sum(r["consens"] is None for r in measured),
        "fallback": sum(bool(r["fallback"]) for r in measured),
        "tokens_scored": aw._percentiles([r["tokens"] for r in measured]),
    }
    out["time"] = {
        "ms_per_sentence": aw._percentiles([r["ms"] for r in measured]),
        "prompt_tokens": aw._percentiles([r["prompt_tokens"] for r in measured]),
    }
    meta = scores_path().with_suffix(".meta.json")
    out["run"] = json.loads(meta.read_text(encoding="utf-8"))
    path = ROOT / "results" / f"{SET}_arms" / "consens.json"
    path.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    for name, s in out["arms"].items():
        cells = "  ".join(
            f"{g}: {s[g]['false_rollbacks']}/{s[g]['caught']} {s[g]['accuracy']}"
            for g in ("source answers", "closed answers", "total")
        )
        print(f"{name:44} {cells}  {s['total']['interval_95']}")
    show = ("with source only", "auroc", "paired", "fixed_reading", "values", "time")
    print(json.dumps({k: out[k] for k in show}, indent=1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["items", "calibrate", "report"])
    command = parser.parse_args().command
    if command == "items":
        built = items()
        counts = {
            "set": SET,
            "sentences": len(built),
            "prompt_chars_max": max(len(i["with"]) for i in built),
            "fallback": sum(i["fallback"] for i in built),
            "no_word": sum(not i["keep"] for i in built),
        }
        print(json.dumps(counts))
    elif command == "calibrate":
        calibrate()
    else:
        report()


if __name__ == "__main__":
    main()
