"""Stop 42: a reasoning LLM as the auditor's judge (docs/GRID.md § Stop 42).

The judge takes the place of the entailment model for each clause the auditor sends to its
entailment check. It sees the clause, the auditor's own candidates as numbered passages and the
answer so far (to resolve references only), and says supported, contradicted or not stated.

- Replace: the judge decides every clause in place of DeBERTa (``JudgeScorer``, an ``NLIScorer``);
- Appeal: V0's verdicts, except an entailment-only rollback is lifted when the judge supports
  every clause of the sentence.

Controls: MiniCheck and ModernBERT-large NLI in DeBERTa's place, thresholds from a dev sweep. All
model work is on Modal or the router; this machine records what is sent, replays the verifier
from the returned labels and scores, and scores the result.

  uv run python scripts/auditor_judge.py record   # what each text sends (counts; inputs to Modal)
  uv run python scripts/auditor_judge.py pilot    # 5 dev texts to Gemini (paid)
  uv run python scripts/auditor_judge.py gemini   # every clause to Gemini (paid)
  uv run python scripts/auditor_judge.py report   # replay and score → results/auditor_judge/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "batteries/verifier"))

from legal_rag_verifier.premise import Premise  # noqa: E402
from legal_rag_verifier.verifier import NLIProbs, NLIScorer, Verifier, VerifierConfig  # noqa: E402

OUT = ROOT / "results/auditor_judge"
LABELS = ("supported", "contradicted", "not_stated")
GEMINI = "gemini-3.8-flash-high"
QWEN = "Qwen/Qwen3.8-27B-FP8"
QWEN_REVISION = "017b9c7af6b5689d5dd426a76e0bc077eb5ca20a"
# Each judge run: (file stem, effort, seed). Part A only for the repeat.
QWEN_RUNS = (("qwen-low", "low", 0), ("qwen-xhigh", "xhigh", 0), ("qwen-xhigh-2", "xhigh", 1))
JUDGES = ("gemini", "qwen-low", "qwen-xhigh")
# The entailment models replayed from score tables. V0 is today's; the other two are controls.
CLASSIFIERS: dict[str, dict[str, Any]] = {
    "v0": {
        "model": "cross-encoder/nli-deberta-v3-base",
        "revision": "6c749ce3425cd33b46d187e45b92bbf96ee12ec7",
        "max_length": 512,
        "two_way": False,
    },
    "minicheck": {
        "model": "lytang/MiniCheck-DeBERTa-v3-Large",
        "revision": "2f2d01a54fa022a7ffadb76260e1ea8bc88c82bb",
        "max_length": 512,
        "two_way": True,  # 0 unsupported, 1 supported; no contradiction class
    },
    "modernbert": {
        "model": "tasksource/ModernBERT-large-nli",
        "revision": "ca476cb923a8637073d4ceb0f19f7fc236e260d4",
        "max_length": 2048,
        "two_way": False,
    },
}
ENTAILS = (0.5, 0.6, 0.7, 0.8, 0.9)
CONTRADICTS = (0.3, 0.4, 0.5, 0.6, 0.7)
NLI_REASONS = frozenset({"NLI_CONTRADICTION", "NLI_NOT_ENTAILED", "NEUTRAL_STRICT"})
DEFAULT = VerifierConfig()
STRICT = VerifierConfig(neutral_policy="strict", neutral_with_grounded_claim="rollback")
BOOTSTRAP = 2000
SEED = 42

SYSTEM = (
    "You check whether a sentence is supported by source passages. Use only the passages, not "
    "your own knowledge. Reply with a single JSON object."
)
USER = """Passages:
{passages}

Answer so far. Use it only to work out what words such as "it" or "this" refer to. It is not \
evidence.
<<<
{prefix}
>>>

Sentence to check:
<<<
{sentence}
>>>

Labels:
- "supported": a passage states the sentence, or the sentence follows from the passages by \
reasoning, such as applying a default, substituting a definition, following a reference to another \
passage, converting units or doing arithmetic.
- "contradicted": the passages state or imply something incompatible with the sentence, such as a \
different figure, condition, scope or outcome.
- "not_stated": neither. Use this when the sentence may be true but the passages do not establish \
it.

Return JSON with keys "label" (one of the three), "passage" (the number of the passage that \
decides it, or 0) and "reason" (one sentence)."""
PROMPT_SHA = hashlib.sha256((SYSTEM + USER).encode()).hexdigest()


# ---------------------------------------------------------------------- the judge prompt


def user_prompt(sentence: str, candidates: Sequence[str], prefix: str) -> str:
    passages = "\n\n".join(f"[{n}] {text}" for n, text in enumerate(candidates, 1))
    return USER.format(passages=passages, prefix=prefix or "(none)", sentence=sentence)


def prompt_key(user: str) -> str:
    return hashlib.sha256(f"{SYSTEM}\n{user}".encode()).hexdigest()


def extract_json(text: str) -> dict[str, Any]:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in output")
    parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("not a JSON object")  # noqa: TRY004
    return parsed


def parse_reply(text: str) -> dict[str, Any]:
    """A judge reply as ``{label, passage, reason}``; ValueError when it is not one."""
    reply = extract_json(text)
    label = str(reply.get("label", "")).strip().lower().replace(" ", "_")
    if label not in LABELS:
        raise ValueError(f"label {label!r}")
    try:
        passage = int(reply.get("passage") or 0)
    except (TypeError, ValueError):
        passage = 0
    return {"label": label, "passage": passage, "reason": str(reply.get("reason", ""))}


RETRY = "Reply with ONLY the JSON object, with keys label, passage and reason."


def ask(chat: Callable[[list[dict[str, str]]], dict[str, Any]], user: str) -> dict[str, Any]:
    """At most 3 asks for a valid reply. ``chat`` returns ``{content, ms, tokens}``."""
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    ms = tokens = 0.0
    content = ""
    for attempt in range(1, 4):
        reply = chat(messages)
        ms += reply["ms"]
        tokens += reply.get("tokens") or 0
        content = reply["content"] or ""
        try:
            return {**parse_reply(content), "attempts": attempt, "ms": ms, "tokens": tokens}
        except (ValueError, json.JSONDecodeError):
            messages = [*messages[:2], {"role": "assistant", "content": content}]
            messages.append({"role": "user", "content": RETRY})
    return {
        "label": "error",
        "passage": 0,
        "reason": content[-300:],
        "attempts": 3,
        "ms": ms,
        "tokens": tokens,
    }


# ---------------------------------------------------------------------- batched teacher calls

_LABELS_BLOCK = USER[USER.index("Labels:") : USER.index("Return JSON")]
BATCH_USER = (
    """Passages:
{passages}

Answer so far. Use it only to work out what words such as "it" or "this" refer to. It is not \
evidence.
<<<
{prefix}
>>>

Sentences to check, in the order they continue the answer. Each earlier sentence in this list \
is context for the later ones in the same way, not evidence.
{sentences}

"""
    + _LABELS_BLOCK
    + """Return a JSON object with key "results": a list with one entry per numbered sentence, \
in order, each with keys "sentence" (its number), "label" (one of the three), "passage" (the \
number of the passage that decides it, or 0) and "reason" (one sentence)."""
)
BATCH_SHA = hashlib.sha256((SYSTEM + BATCH_USER).encode()).hexdigest()
MAX_BATCH = 12


def batch_prompt(clauses: Sequence[str], candidates: Sequence[str], prefix: str) -> str:
    passages = "\n\n".join(f"[{n}] {text}" for n, text in enumerate(candidates, 1))
    sentences = "\n".join(f"[{n}] {c}" for n, c in enumerate(clauses, 1))
    return BATCH_USER.format(passages=passages, prefix=prefix or "(none)", sentences=sentences)


def batches(units: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Group clauses for one call each. ``units`` are recorded texts in answer order, each with
    ``group`` (the answer it belongs to), ``prefix`` and ``calls``. Consecutive clauses of one
    answer with the same candidates share a call, up to ``MAX_BATCH``. Each clause keeps the key
    of its stop 42 single-clause prompt, so labels map back unchanged."""
    out: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for u in units:
        for clause, candidates in u["calls"]:
            single = prompt_key(user_prompt(clause, candidates, u["prefix"]))
            same = (
                current is not None
                and current["group"] == u["group"]
                and current["candidates"] == list(candidates)
                and len(current["clauses"]) < MAX_BATCH
            )
            if not same:
                current = {
                    "group": u["group"],
                    "prefix": u["prefix"],
                    "candidates": list(candidates),
                    "clauses": [],
                    "keys": [],
                }
                out.append(current)
            assert current is not None  # noqa: S101 - set above
            if single not in current["keys"]:
                current["clauses"].append(clause)
                current["keys"].append(single)
    for b in out:
        b["user"] = batch_prompt(b["clauses"], b["candidates"], b["prefix"])
        b["key"] = prompt_key(b["user"])
    return out


def parse_batch(text: str, n: int) -> list[dict[str, Any]]:
    """A batched reply as ``n`` labels in order; ValueError unless every sentence has one."""
    reply = extract_json(text)
    results = reply.get("results")
    if not isinstance(results, list) or len(results) != n:
        raise ValueError(f"expected {n} results")
    out = []
    for item in results:
        if not isinstance(item, dict):
            raise ValueError("result is not an object")  # noqa: TRY004
        out.append(parse_reply(json.dumps(item)))
    return out


BATCH_RETRY = (
    'Reply with ONLY the JSON object {"results": [...]}, one entry per numbered sentence, in order.'
)


def ask_batch(
    chat: Callable[[list[dict[str, str]]], dict[str, Any]], batch: Mapping[str, Any]
) -> dict[str, Any]:
    """At most 3 asks for a complete batched reply. Labels in clause order, or an error."""
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": batch["user"]}]
    ms = tokens = 0.0
    content = ""
    for attempt in range(1, 4):
        reply = chat(messages)
        ms += reply["ms"]
        tokens += reply.get("tokens") or 0
        content = reply["content"] or ""
        try:
            labels = parse_batch(content, len(batch["clauses"]))
        except (ValueError, json.JSONDecodeError):
            messages = [*messages[:2], {"role": "assistant", "content": content}]
            messages.append({"role": "user", "content": BATCH_RETRY})
            continue
        return {"labels": labels, "attempts": attempt, "ms": ms, "tokens": tokens}
    return {"labels": None, "error": content[-300:], "attempts": 3, "ms": ms, "tokens": tokens}


def gemini_chat(messages: list[dict[str, str]]) -> dict[str, Any]:
    """One router call (``enrich_premises._chat``: chat/completions, gemini-3.8-flash-high, T 0)."""
    from enrich_premises import _chat  # type: ignore[import-not-found]  # noqa: PLC0415

    t0 = time.perf_counter()
    content = _chat(messages)
    return {"content": content, "ms": (time.perf_counter() - t0) * 1000, "tokens": None}


def server_chat(
    url: str, model: str, sampling: Mapping[str, Any], template: Mapping[str, Any]
) -> Callable[[list[dict[str, str]]], dict[str, Any]]:
    """A chat function against an SGLang server on Modal, with given sampling and template
    arguments (``chat_template_kwargs``)."""

    def chat(messages: list[dict[str, str]]) -> dict[str, Any]:
        body = {
            "model": model,
            "messages": messages,
            **sampling,
            "chat_template_kwargs": dict(template),
        }
        request = urllib.request.Request(  # noqa: S310 - the Modal-local SGLang server
            f"{url}/v1/chat/completions",
            data=json.dumps(body).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        t0 = time.perf_counter()
        with urllib.request.urlopen(request, timeout=1800) as response:  # noqa: S310
            out = json.loads(response.read())
        ms = (time.perf_counter() - t0) * 1000
        message = out["choices"][0]["message"]
        return {
            "content": message.get("content") or "",
            "ms": ms,
            "tokens": out.get("usage", {}).get("completion_tokens"),
            "finish": out["choices"][0].get("finish_reason"),
        }

    return chat


def qwen_chat(url: str, effort: str, seed: int) -> Callable[[list[dict[str, str]]], dict[str, Any]]:
    """Qwen3.8 27B with thinking on at the card's sampling (stop 42)."""
    sampling = {"temperature": 1.0, "top_p": 0.95, "top_k": 20, "min_p": 0.0}
    sampling |= {"max_tokens": 16384, "seed": seed}
    return server_chat(url, QWEN, sampling, {"enable_thinking": True, "reasoning_effort": effort})


def judge_all(
    requests: Mapping[str, str],
    chat: Callable[[list[dict[str, str]]], dict[str, Any]],
    workers: int,
    done: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, dict[str, Any]]:
    """Every ``{sha: user prompt}``, ``workers`` at a time; network errors count as attempts."""

    def one(sha: str) -> tuple[str, dict[str, Any]]:
        for _ in range(3):
            try:
                return sha, ask(chat, requests[sha])
            except (urllib.error.URLError, TimeoutError, KeyError) as exc:
                failure = repr(exc)
        return sha, {"label": "error", "passage": 0, "reason": failure, "attempts": 3, "ms": 0}

    out: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(workers) as pool:
        for n, (sha, result) in enumerate(pool.map(one, list(requests)), 1):
            out[sha] = result
            if done:
                done(sha, result)
            if n % 25 == 0:
                print(f"{n}/{len(requests)}", flush=True)
    return out


# ---------------------------------------------------------------------- scorers


def one_hot(label: str, passage: int, n: int) -> list[NLIProbs]:
    """A judge label as entailment-model output over ``n`` candidates. Supported: entailment 1
    on its passage; contradicted: contradiction 1 there; otherwise neutral 1 everywhere. A
    passage number out of range applies the label to every candidate."""
    neutral = NLIProbs(0.0, 1.0, 0.0)
    if label == "supported":
        hit = NLIProbs(1.0, 0.0, 0.0)
    elif label == "contradicted":
        hit = NLIProbs(0.0, 0.0, 1.0)
    else:
        return [neutral] * n
    if not 1 <= passage <= n:
        return [hit] * n
    return [hit if i == passage - 1 else neutral for i in range(n)]


class RecordingScorer:
    """Lists each (clause, candidates) the verifier sends to its entailment check."""

    model_id = "recording"

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def score(self, premises: Sequence[str], hypothesis: str) -> list[NLIProbs]:
        self.calls.append((hypothesis, tuple(premises)))
        return [NLIProbs(0.0, 1.0, 0.0)] * len(premises)


def pair_key(premise: str, hypothesis: str) -> str:
    return hashlib.sha256(f"{premise}\x00{hypothesis}".encode()).hexdigest()


class TableScorer:
    """Scores looked up from a table keyed by ``pair_key`` (filled on Modal)."""

    def __init__(self, model_id: str, table: Mapping[str, Sequence[float]]) -> None:
        self.model_id = model_id
        self.table = table

    def score(self, premises: Sequence[str], hypothesis: str) -> list[NLIProbs]:
        return [NLIProbs(*self.table[pair_key(p, hypothesis)]) for p in premises]


class JudgeScorer:
    """The judge in DeBERTa's place. ``prefix`` is set per text before it is checked."""

    def __init__(self, name: str, labels: Mapping[str, Mapping[str, Any]]) -> None:
        self.model_id = name
        self.labels = labels
        self.prefix = ""

    def score(self, premises: Sequence[str], hypothesis: str) -> list[NLIProbs]:
        label = self.labels[prompt_key(user_prompt(hypothesis, premises, self.prefix))]
        return one_hot(label["label"], label["passage"], len(premises))


# ---------------------------------------------------------------------- sets (laptop)


def items() -> list[dict[str, Any]]:
    """Part A and statutes as stop 40 read them; Part B as stop 41, with its answer so far."""
    from nli_context import (  # type: ignore[import-not-found]  # noqa: PLC0415
        software_items,
        statute_items,
    )
    from nli_normalised import part_b  # type: ignore[import-not-found]  # noqa: PLC0415

    out = [{**i, "key": f"A:{i['item']}", "level": "A"} for i in software_items()]
    sentences: dict[str, list[str]] = {}
    for i in part_b():
        done = sentences.setdefault(i["item"], [])
        out.append({**i, "prefix": " ".join(done)})
        done.append(i["sentence"])
    out += [{**i, "key": f"S:{i['item']}", "level": "S"} for i in statute_items()]
    return out


def premises(units: Sequence[Mapping[str, Any]]) -> dict[str, Premise]:
    """Each text's premise, keyed by ``key`` (software as stop 41's V0, statutes as run)."""
    import grid_prompts  # type: ignore[import-not-found]  # noqa: PLC0415
    import software_battery  # type: ignore[import-not-found]  # noqa: PLC0415

    software = {r["id"]: software_battery.premise(r) for r in software_battery.rows()}
    wanted = {i["id"] for i in units if i["level"] == "S"}
    statutes = {
        r["id"]: grid_prompts.premise(r) for r in grid_prompts.rows("test") if r["id"] in wanted
    }
    return {i["key"]: (statutes if i["level"] == "S" else software)[i["id"]] for i in units}


def dev_rows() -> tuple[list[dict[str, Any]], dict[str, Premise]]:
    """The dev battery with the run's enrichment layer, keyed as ``run_battery`` keys it."""
    import premises as battery_premises  # noqa: PLC0415
    from run_battery import (  # type: ignore[import-not-found]  # noqa: PLC0415
        load_rows,
        premises_for,
    )

    rows = load_rows(ROOT / "batteries/verifier/dev.jsonl")
    if any(r.get("split") != "dev" for r in rows):
        raise RuntimeError("the control sweep runs on the dev split only")
    built = premises_for(rows, ROOT / "data", ROOT / "enrichment" / GEMINI)
    return [{**r, "key": battery_premises.premise_key(r)} for r in rows], built


def record(
    units: Sequence[Mapping[str, Any]], built: Mapping[str, Premise], *, dev: bool = False
) -> list[dict[str, Any]]:
    """Per text: the claim check verdict when it rolls back, else the calls to the entailment
    check (the clauses and candidates do not depend on the scores)."""
    out = []
    for u in units:
        scorer = RecordingScorer()
        v = Verifier(scorer).check_sentence(built[u["key"]], u["sentence"], query=u["query"])
        out.append(
            {
                "key": u["id"] if dev else u["key"],
                "prefix": "" if dev else u["prefix"],
                "calls": [[h, list(c)] for h, c in scorer.calls],
                "claim_rollback": not scorer.calls and v.verdict.name != "EMIT",
            }
        )
    return out


def requests(recorded: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """Unique judge prompts, ``{sha: user prompt}``."""
    out: dict[str, str] = {}
    for r in recorded:
        for clause, candidates in r["calls"]:
            user = user_prompt(clause, candidates, r["prefix"])
            out[prompt_key(user)] = user
    return out


def pairs(recorded: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    """Unique (candidate, clause) pairs for the classifiers, ``{pair_key: [premise, clause]}``."""
    return {
        pair_key(p, clause): [p, clause]
        for r in recorded
        for clause, candidates in r["calls"]
        for p in candidates
    }


# ---------------------------------------------------------------------- replay and scoring


def replay(
    units: Sequence[Mapping[str, Any]],
    built: Mapping[str, Premise],
    scorer: NLIScorer,
    config: VerifierConfig = DEFAULT,
) -> dict[str, dict[str, Any]]:
    verifier = Verifier(scorer, config)
    out = {}
    for u in units:
        if isinstance(scorer, JudgeScorer):
            scorer.prefix = u.get("prefix", "")
        v = verifier.check_sentence(built[u["key"]], u["sentence"], query=u["query"])
        out[u["key"]] = {"verdict": v.verdict.name, "reasons": [r.name for r in v.reasons]}
    return out


def appeal(
    v0: Mapping[str, Mapping[str, Any]],
    recorded: Mapping[str, Mapping[str, Any]],
    labels: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """V0's verdicts; an entailment-only rollback is lifted when the judge supports every clause
    the sentence sent to the entailment check. Claim check rollbacks stand."""
    out = {}
    for key, v in v0.items():
        r = recorded[key]
        nli_only = v["verdict"] != "EMIT" and set(v["reasons"]) <= NLI_REASONS
        lifted = nli_only and all(
            labels[prompt_key(user_prompt(c, cands, r["prefix"]))]["label"] == "supported"
            for c, cands in r["calls"]
        )
        out[key] = {"verdict": "EMIT", "reasons": ["APPEAL"]} if lifted else dict(v)
    return out


def _units(
    texts: Sequence[Mapping[str, Any]], verdicts: Mapping[str, Mapping[str, Any]], level: str
) -> list[dict[str, Any]]:
    """Scoring units: sentences (A, statutes) or answers (B, rolled back if any sentence is)."""

    def rolled(t: Mapping[str, Any]) -> bool:
        return bool(verdicts[t["key"]]["verdict"] != "EMIT")

    def by_nli(t: Mapping[str, Any]) -> bool:
        return set(verdicts[t["key"]]["reasons"]) <= NLI_REASONS

    if level != "B":
        return [{**t, "rolled": rolled(t), "by_nli": by_nli(t)} for t in texts]
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for t in texts:
        grouped.setdefault(t["item"], []).append(t)
    return [
        {
            "item": item,
            "right": ts[0]["right"],
            "wrong": ts[0]["wrong"],
            "rolled": any(rolled(t) for t in ts),
            "by_nli": all(by_nli(t) for t in ts if rolled(t)),
        }
        for item, ts in grouped.items()
    ]


def counts(units: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rolled = [u for u in units if u["rolled"]]
    right, wrong = sum(u["right"] for u in units), sum(u["wrong"] for u in units)
    false_rollbacks, caught = sum(u["right"] for u in rolled), sum(u["wrong"] for u in rolled)
    return {
        "texts": len(units),
        "right": right,
        "wrong": wrong,
        "false_rollbacks": false_rollbacks,
        "caught": caught,
        "false_rollbacks_by_nli": sum(u["right"] for u in rolled if u["by_nli"]),
        "caught_by_nli": sum(u["wrong"] for u in rolled if u["by_nli"]),
        "accuracy": round((right - false_rollbacks + caught) / max(right + wrong, 1), 3),
    }


def passes_bar(arm: Mapping[str, Any], base: Mapping[str, Any]) -> bool:
    from nli_context import HALVE, KEEP  # noqa: PLC0415

    return bool(
        arm["false_rollbacks"] <= HALVE * base["false_rollbacks"]
        and arm["caught"] >= KEEP * base["caught"]
    )


def auc(right: Sequence[float], wrong: Sequence[float]) -> float | None:
    """P(a right text scores above a wrong one), ties half."""
    if not right or not wrong:
        return None
    wins = sum((r > w) + 0.5 * (r == w) for r in right for w in wrong)
    return wins / (len(right) * len(wrong))


def auc_interval(right: Sequence[float], wrong: Sequence[float]) -> dict[str, Any]:
    """AUC with a 95 % percentile bootstrap interval (texts resampled within each class)."""
    point = auc(right, wrong)
    if point is None:
        return {"auc": None}
    rng = random.Random(SEED)  # noqa: S311 - a bootstrap, not a secret
    draws = sorted(
        auc(rng.choices(right, k=len(right)), rng.choices(wrong, k=len(wrong))) or 0.0
        for _ in range(BOOTSTRAP)
    )
    return {
        "auc": round(point, 3),
        "low": round(draws[int(0.025 * BOOTSTRAP)], 3),
        "high": round(draws[int(0.975 * BOOTSTRAP) - 1], 3),
        "right": len(right),
        "wrong": len(wrong),
    }


def support(r: Mapping[str, Any], table: Mapping[str, Sequence[float]]) -> float | None:
    """A text's support score: over its clauses, the lowest best entailment over candidates.
    None when the claim check decided it (nothing reached the entailment check)."""
    if not r["calls"]:
        return None
    return min(max(table[pair_key(p, c)][0] for p in cands) for c, cands in r["calls"])


def sweep(
    rows: Sequence[Mapping[str, Any]], built: Mapping[str, Premise], scorer: NLIScorer
) -> list[dict[str, Any]]:
    """The dev battery under each (entail, contradict) pair, the rest as run."""
    from run_battery import Outcome, summarise  # noqa: PLC0415

    out = []
    for e in ENTAILS:
        for c in CONTRADICTS:
            verifier = Verifier(scorer, VerifierConfig(e, c))
            outcomes = []
            for row in rows:
                v = verifier.check_sentence(built[row["key"]], row["sentence"], query=row["query"])
                reasons = tuple(r.value for r in v.reasons)
                outcomes.append(
                    Outcome(row["id"], row["class"], row["expected"], v.verdict.value, reasons)
                )
            out.append({"entail": e, "contradict": c, **summarise(outcomes)["headline"]})
    return out


def choose(grid: Sequence[Mapping[str, Any]], recall: float) -> dict[str, Any]:
    """Lowest pass-class false rollbacks with failure recall at least V0's; if none, the highest
    recall. Ties go to the configuration closest to 0.70 / 0.40."""

    def distance(g: Mapping[str, Any]) -> float:
        return float(abs(g["entail"] - 0.70) + abs(g["contradict"] - 0.40))

    qualified = [g for g in grid if g["failure_recall"] >= recall]
    if qualified:
        best = min(qualified, key=lambda g: (g["pass_false_rollback_rate"], distance(g)))
    else:
        best = min(grid, key=lambda g: (-g["failure_recall"], distance(g)))
    return {**best, "qualified": bool(qualified)}


def latency(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ms = sorted(r["ms"] for r in records if r.get("ms"))
    tokens = [r["tokens"] for r in records if r.get("tokens")]
    if not ms:
        return {}
    return {
        "calls": len(ms),
        "p50_ms": round(statistics.median(ms)),
        "p95_ms": round(ms[min(len(ms) - 1, int(0.95 * len(ms)))]),
        "mean_tokens": round(statistics.mean(tokens)) if tokens else None,
    }


# ---------------------------------------------------------------------- files


def write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8"
    )


def read_labels(name: str) -> dict[str, dict[str, Any]]:
    path = OUT / "labels" / f"{name}.jsonl"
    if not path.exists():
        return {}
    return {r["sha"]: r for r in map(json.loads, path.read_text(encoding="utf-8").splitlines())}


def read_table(name: str) -> dict[str, list[float]]:
    path = OUT / "scores" / f"{name}.json"
    table: dict[str, list[float]] = json.loads(path.read_text(encoding="utf-8"))
    return table


def recorded_sets() -> tuple[list[dict[str, Any]], dict[str, Premise], list[dict[str, Any]]]:
    texts = items()
    built = premises(texts)
    return texts, built, record(texts, built)


def assert_prompts_clean(texts: Sequence[Mapping[str, Any]], asked: Mapping[str, str]) -> int:
    """Each prompt is the frozen template filled with a clause, its candidates and the answer
    so far, and no question appears in it. Labels and grades are never inputs to it."""
    queries = {t["query"] for t in texts}
    bad = [sha for sha, user in asked.items() if any(q in user for q in queries)]
    bad += [sha for sha, user in asked.items() if prompt_key(user) != sha]
    if bad:
        raise RuntimeError(f"{len(bad)} prompts hold more than their inputs")
    return len(asked)


# ---------------------------------------------------------------------- commands


def pilot_texts() -> tuple[dict[str, str], list[dict[str, Any]]]:
    """The first 5 dev battery texts that reach the entailment check, one prompt per clause."""
    rows, built = dev_rows()
    picked: list[dict[str, Any]] = []
    for row in rows:
        r = record([row], built, dev=True)[0]
        if r["calls"]:
            picked.append({**r, "sentence": row["sentence"]})
        if len(picked) == 5:  # noqa: PLR2004
            break
    return requests(picked), picked


def cmd_record() -> None:
    texts, _, recorded = recorded_sets()
    asked = requests(recorded)
    assert_prompts_clean(texts, asked)
    by_level: dict[str, Any] = {}
    for level in ("A", "B", "S"):
        rs = [r for r, t in zip(recorded, texts, strict=True) if t["level"] == level]
        by_level[level] = {
            "texts": len(rs),
            "claim_rollbacks": sum(r["claim_rollback"] for r in rs),
            "reach_entailment": sum(bool(r["calls"]) for r in rs),
            "clauses": sum(len(r["calls"]) for r in rs),
            "prompts": len(requests(rs)),
            "pairs": len(pairs(rs)),
        }
    rows, built = dev_rows()
    dev = record(rows, built, dev=True)
    by_level["dev"] = {"texts": len(dev), "pairs": len(pairs(dev))}
    by_level["all_prompts"] = len(asked)
    by_level["all_pairs"] = len(pairs(recorded) | pairs(dev))
    by_level["prompt_sha256"] = PROMPT_SHA
    print(json.dumps(by_level, indent=1))


def cmd_pilot() -> None:
    asked, picked = pilot_texts()
    results = judge_all(asked, gemini_chat, 1)
    out = OUT / "pilot"  # git-ignored: the prompts quote full statute text
    write_jsonl(
        out / "gemini.jsonl",
        [{"sha": s, "prompt": asked[s], **results[s]} for s in asked],
    )
    for p in picked:
        print(p["key"], p["sentence"])
    for sha in asked:
        r = results[sha]
        print(f"{r['label']:13} p{r['passage']} {r['ms']:.0f} ms  {r['reason']}")


def cmd_gemini() -> None:
    texts, _, recorded = recorded_sets()
    asked = requests(recorded)
    assert_prompts_clean(texts, asked)
    have = read_labels("gemini")
    todo = {s: u for s, u in asked.items() if s not in have}
    print(f"{len(asked)} prompts, {len(have)} cached, {len(todo)} to ask", flush=True)
    path = OUT / "labels" / "gemini.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)

    def done(sha: str, result: Mapping[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"sha": sha, **result}, ensure_ascii=False) + "\n")

    judge_all(todo, gemini_chat, 4, done)


def _p95(values: Sequence[float]) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]


def reproduces(
    texts: Sequence[Mapping[str, Any]], v0: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    """The table-replayed V0 against the verdicts as run (A and statutes: recorded; B: stop 41)."""
    lines = (ROOT / "results/normalise/audit.jsonl").read_text(encoding="utf-8").splitlines()
    stop41 = {r["key"]: r["verdicts"]["V0"]["verdict"] for r in map(json.loads, lines)}
    out = {}
    for level in ("A", "B", "S"):
        same, differ = 0, []
        for t in texts:
            if t["level"] != level:
                continue
            was = stop41[t["key"]] if level == "B" else t["recorded"]
            if was not in ("EMIT", "ROLLBACK"):
                continue
            if (was == "EMIT") == (v0[t["key"]]["verdict"] == "EMIT"):
                same += 1
            else:
                differ.append(t["key"])
        out[level] = {"same": same, "of": same + len(differ), "differ": differ}
    return out


def judged_errors(
    texts: Sequence[Mapping[str, Any]],
    rec: Mapping[str, Mapping[str, Any]],
    verdicts: Mapping[str, Mapping[str, Any]],
    labels: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """R5: wrong texts passed and right texts rolled back (B: by answer), with the judge's
    label and reason for each clause."""

    def clauses(t: Mapping[str, Any]) -> list[dict[str, Any]]:
        r = rec[t["key"]]
        out = []
        for c, cands in r["calls"]:
            label = labels[prompt_key(user_prompt(c, cands, r["prefix"]))]
            out.append({"clause": c, **{k: label[k] for k in ("label", "passage", "reason")}})
        return out

    errors = []
    by_answer: dict[str, list[Mapping[str, Any]]] = {}
    for t in texts:
        if t["level"] == "B":
            by_answer.setdefault(t["item"], []).append(t)
            continue
        rolled = verdicts[t["key"]]["verdict"] != "EMIT"
        if (t["wrong"] and not rolled) or (t["right"] and rolled):
            errors.append(
                {
                    "key": t["key"],
                    "error": "wrong passed" if t["wrong"] else "right rolled back",
                    "sentence": t["sentence"],
                    "reasons": verdicts[t["key"]]["reasons"],
                    "judge": clauses(t),
                }
            )
    for item, ts in by_answer.items():
        rolled_ts = [t for t in ts if verdicts[t["key"]]["verdict"] != "EMIT"]
        if ts[0]["wrong"] and not rolled_ts:
            shown = ts
        elif ts[0]["right"] and rolled_ts:
            shown = rolled_ts
        else:
            continue
        errors.append(
            {
                "key": f"B:{item}",
                "error": "wrong passed" if ts[0]["wrong"] else "right rolled back",
                "sentences": [
                    {
                        "sentence": t["sentence"],
                        "reasons": verdicts[t["key"]]["reasons"],
                        "judge": clauses(t),
                    }
                    for t in shown
                ],
            }
        )
    return errors


def added_time(
    texts: Sequence[Mapping[str, Any]],
    rec: Mapping[str, Mapping[str, Any]],
    v0: Mapping[str, Mapping[str, Any]],
    labels: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """R3: judge time added per Part B answer, clauses judged one after another. Replace judges
    every clause that reaches the entailment check; Appeal only those of V0's entailment-only
    rollbacks."""

    def ms(t: Mapping[str, Any]) -> float:
        r = rec[t["key"]]
        return sum(
            float(labels[prompt_key(user_prompt(c, cands, r["prefix"]))].get("ms") or 0)
            for c, cands in r["calls"]
        )

    b = [t for t in texts if t["level"] == "B"]
    appealed = {
        t["key"]
        for t in b
        if v0[t["key"]]["verdict"] != "EMIT" and set(v0[t["key"]]["reasons"]) <= NLI_REASONS
    }
    out: dict[str, Any] = {}
    for placement, chosen in (
        ("replace", [t for t in b if rec[t["key"]]["calls"]]),
        ("appeal", [t for t in b if t["key"] in appealed]),
    ):
        per_answer: dict[str, float] = {t["item"]: 0.0 for t in b}
        for t in chosen:
            per_answer[t["item"]] += ms(t)
        values = list(per_answer.values())
        out[placement] = {
            "sentences_judged": len(chosen),
            "of_sentences": len(b),
            "mean_s_per_answer": round(statistics.mean(values) / 1000, 1),
            "p95_s_per_answer": round(_p95(values) / 1000, 1),
        }
    return out


def cmd_report() -> None:  # noqa: PLR0912, PLR0915 - one pass over the readings
    texts, built, recorded = recorded_sets()
    asked = requests(recorded)
    rec = {t["key"]: r for t, r in zip(texts, recorded, strict=True)}
    report: dict[str, Any] = {
        "prompt_sha256": PROMPT_SHA,
        "prompts_checked_clean": assert_prompts_clean(texts, asked),
    }
    tables = {n: read_table(n) for n in CLASSIFIERS if (OUT / "scores" / f"{n}.json").exists()}
    v0 = replay(texts, built, TableScorer("v0", tables["v0"]))
    report["v0_reproduces"] = reproduces(texts, v0)
    arms: dict[str, dict[str, dict[str, Any]]] = {"V0": v0}
    arms["claim check only"] = {
        k: {"verdict": "EMIT", "reasons": []} if set(v["reasons"]) <= NLI_REASONS else v
        for k, v in v0.items()
    }
    arms["no auditor"] = {k: {"verdict": "EMIT", "reasons": []} for k in v0}

    # Controls: thresholds from the dev sweep (rule fixed in GRID), then replayed on the sets.
    rows, dev_built = dev_rows()
    dev_grid = {n: sweep(rows, dev_built, TableScorer(n, t)) for n, t in tables.items()}
    v0_dev = next(g for g in dev_grid["v0"] if (g["entail"], g["contradict"]) == (0.7, 0.4))
    report["dev"] = {"v0_at_0.70_0.40": v0_dev}
    for name in ("minicheck", "modernbert"):
        if name not in tables:
            continue
        chosen = choose(dev_grid[name], v0_dev["failure_recall"])
        report["dev"][name] = chosen
        config = VerifierConfig(chosen["entail"], chosen["contradict"])
        arms[name] = replay(texts, built, TableScorer(name, tables[name]), config)

    judges = {j: read_labels(j) for j in (*JUDGES, "qwen-xhigh-2")}
    judges = {j: labels for j, labels in judges.items() if labels}
    report["judge_errors"] = {}
    for judge in JUDGES:
        if judge not in judges:
            continue
        labels = judges[judge]
        missing = set(asked) - set(labels)
        if missing:
            raise RuntimeError(f"{judge}: {len(missing)} prompts have no label")
        report["judge_errors"][judge] = sum(labels[s]["label"] == "error" for s in asked)
        arms[f"{judge} replace"] = replay(texts, built, JudgeScorer(judge, labels))
        arms[f"{judge} replace strict"] = replay(texts, built, JudgeScorer(judge, labels), STRICT)
        arms[f"{judge} appeal"] = appeal(v0, rec, labels)

    # R1, R2, R4 counts: every arm on every level, the bar against V0.
    baselines = ("V0", "claim check only", "no auditor")
    for level in ("A", "B", "S"):
        level_texts = [t for t in texts if t["level"] == level]
        block = {name: counts(_units(level_texts, v, level)) for name, v in arms.items()}
        for name, c in block.items():
            if name not in baselines:
                c["passes_bar"] = passes_bar(c, block["V0"])
        report[level] = block
    report["R1_viable"] = {
        name: report["A"][name]["passes_bar"] and report["B"][name]["passes_bar"]
        for name in arms
        if name not in baselines and name not in ("minicheck", "modernbert")
    }
    report["R4_controls_pass_A_and_B"] = {
        name: report["A"][name]["passes_bar"] and report["B"][name]["passes_bar"]
        for name in ("minicheck", "modernbert")
        if name in arms
    }

    # R4: how well each entailment model's support score separates right from wrong texts.
    report["R4_auc"] = {}
    for name, table in tables.items():
        per_level = {}
        for level in ("A", "B", "S"):
            scored: dict[str, tuple[float, bool]] = {}
            for t in texts:
                s = support(rec[t["key"]], table)
                if t["level"] != level or s is None or not (t["right"] or t["wrong"]):
                    continue
                unit = t["item"] if level == "B" else t["key"]
                low = min(s, scored[unit][0]) if unit in scored else s
                scored[unit] = (low, bool(t["right"]))
            right = [s for s, ok in scored.values() if ok]
            wrong = [s for s, ok in scored.values() if not ok]
            per_level[level] = auc_interval(right, wrong)
        report["R4_auc"][name] = per_level

    # R3: latency per judged clause, and time added per Part B answer.
    report["R3"] = {}
    for judge, labels in judges.items():
        entry: dict[str, Any] = {"per_clause": latency([labels[s] for s in asked if s in labels])}
        if judge in JUDGES:
            entry["per_answer_B"] = added_time(texts, rec, v0, labels)
        report["R3"][judge] = entry
    for effort in ("low", "xhigh"):
        sequential = read_labels(f"sequential-{effort}")
        if sequential:
            report["R3"][f"qwen-{effort} one at a time"] = {
                "per_clause": latency(list(sequential.values()))
            }

    # R5: each judge's errors under Replace, with its reasons (written apart).
    r5 = {
        judge: judged_errors(texts, rec, arms[f"{judge} replace"], judges[judge])
        for judge in JUDGES
        if judge in judges
    }
    write_jsonl(OUT / "r5.jsonl", [{"judge": j, **e} for j, es in r5.items() for e in es])
    report["R5_errors"] = {j: len(es) for j, es in r5.items()}

    # R6: Qwen at xhigh against itself on Part A.
    if "qwen-xhigh" in judges and "qwen-xhigh-2" in judges:
        part_a = requests([rec[t["key"]] for t in texts if t["level"] == "A"])
        same = [
            judges["qwen-xhigh"][s]["label"] == judges["qwen-xhigh-2"][s]["label"] for s in part_a
        ]
        report["R6_qwen_self_agreement_A"] = {"same": sum(same), "of": len(same)}

    (OUT / "report.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in report.items() if k not in ("dev",)}, indent=1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["record", "pilot", "gemini", "report"])
    command: Literal["record", "pilot", "gemini", "report"] = parser.parse_args().command
    if command == "record":
        cmd_record()
    elif command == "pilot":
        cmd_pilot()
    elif command == "gemini":
        cmd_gemini()
    else:
        cmd_report()


if __name__ == "__main__":
    main()
