"""Stop 66: two hosted decision APIs as the judge (docs/GRID.md § Stop 66).

Each clause of the short-reply arm is sent once to each API with two typed questions (the label
and the passage that decides it). The reply is scored like any other judge's labels: same
replay, strict placement, your grades.

  uv run python scripts/decisions.py label luna         # OpenAI Decisions API, gpt-6-luna
  uv run python scripts/decisions.py label jev          # Jev 1.13 through OpenRouter
  uv run python scripts/decisions.py label luna --seq   # 40 clauses one at a time, for timing
  uv run python scripts/decisions.py report             # → results/<set>_arms/decisions.json

``FRESH_SET`` picks the test. Keys come from ``OPENAI_API_KEY`` and ``OPENROUTER_API_KEY`` and
are never printed. Every reply is appended as it returns; a rerun asks only what is missing.
"""

from __future__ import annotations

import argparse
import fcntl
import http.client
import json
import os
import random
import re
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

import auditor_judge as aj  # type: ignore[import-not-found]  # noqa: E402
import fresh_arms as fa  # type: ignore[import-not-found]  # noqa: E402
import fresh_battery as fb  # type: ignore[import-not-found]  # noqa: E402
import fresh_eval as fe  # type: ignore[import-not-found]  # noqa: E402
import fresh_report as fr  # type: ignore[import-not-found]  # noqa: E402

LUNA = "luna-decisions"
JEV = "jev-decisions"
# host, path, model, the environment variable holding the key
APIS = {
    LUNA: ("api.openai.com", "/v1/decisions", "gpt-6-luna", "OPENAI_API_KEY"),
    JEV: ("openrouter.ai", "/api/alpha/decisions", "typesafe/jev-1.13", "OPENROUTER_API_KEY"),
}
SHORT = {"luna": LUNA, "jev": JEV}
TITLES = {LUNA: "OpenAI Decisions (gpt-6-luna)", JEV: "Jev 1.13 (OpenRouter)"}
LUNA_USD_PER_M = 0.10  # list price per million input tokens; Jev's cost comes back in the reply
CAP_USD = 2.0  # per API; a call that could pass it is not made
WORST_CALL_USD = 0.01
WORKERS = 4
ATTEMPTS = 6
RETRY_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504, 524, 529})
LEDGER = ROOT / "results/decisions/ledger.json"
THRESHOLDS = tuple(round(0.05 * n, 2) for n in range(1, 20))
TUNED_ON = "fresh"  # the threshold is chosen on test 1 and applied to the others

LABEL_INSTRUCTIONS = (
    "Is the sentence to check supported by the passages? Use only the passages, not your own "
    "knowledge. The answer so far is not evidence."
)
PASSAGE_INSTRUCTIONS = "Which numbered passage decides the label? Choose 0 if none does."
_lock = threading.Lock()
_local = threading.local()


class BudgetExceededError(RuntimeError):
    """The next call could take an API past its cap."""


class ApiError(RuntimeError):
    """A call still failed after every retry, or was refused outright."""


# ---------------------------------------------------------------------- the request


def descriptions() -> dict[str, str]:
    """The three label definitions, word for word from the stop 42 prompt."""
    block = aj.USER[aj.USER.index("Labels:") : aj.USER.index("Return JSON")]
    found = dict(re.findall(r'^- "(\w+)": (.+)$', block, flags=re.MULTILINE))
    return {label: found[label] for label in aj.LABELS}


def state(clause: str, candidates: Sequence[str], prefix: str) -> str:
    """What the judge reads: the stop 42 prompt up to its label list (passages, the answer so
    far, the sentence to check)."""
    head, _ = aj.user_prompt(clause, candidates, prefix).rsplit("\n\nLabels:", 1)
    return str(head)


def passages(n: int) -> dict[str, str]:
    return {"0": "No single passage decides it."} | {
        str(i): f"Passage [{i}]." for i in range(1, n + 1)
    }


def body(judge: str, clause: str, candidates: Sequence[str], prefix: str) -> dict[str, Any]:
    """One request: the same text and the same two questions, in each API's own shape."""
    text = state(clause, candidates, prefix)
    labels, numbers = descriptions(), passages(len(candidates))
    model = APIS[judge][2]
    if judge == LUNA:
        questions = [
            {
                "type": "choice",
                "name": "label",
                "instructions": LABEL_INSTRUCTIONS,
                "choices": [{"value": k, "description": v} for k, v in labels.items()],
            },
            {
                "type": "choice",
                "name": "passage",
                "instructions": PASSAGE_INSTRUCTIONS,
                "choices": [{"value": k, "description": v} for k, v in numbers.items()],
            },
        ]
        return {"model": model, "input": text, "questions": questions}
    return {
        "model": model,
        "state": text,
        "provider": {"data_collection": "deny"},
        "questions": {
            "label": {"type": "choice", "instructions": LABEL_INSTRUCTIONS, "criteria": labels},
            "passage": {
                "type": "choice",
                "instructions": PASSAGE_INSTRUCTIONS,
                "criteria": numbers,
            },
        },
    }


def parse(judge: str, reply: Mapping[str, Any]) -> dict[str, Any]:
    """A reply as ``{label, passage, probabilities, confidence}``. A refused or missing label is
    ``refusal``; a refused passage is 0."""
    answers = reply["answers"]
    if judge == LUNA:
        answers = {a.get("name"): a for a in answers}
    label, passage = answers.get("label") or {}, answers.get("passage") or {}
    if label.get("type") != "choice" or label.get("choice") not in aj.LABELS:
        return {"label": "refusal", "passage": 0, "reason": str(label.get("type"))}
    probabilities = label.get("probabilities") or {}
    if isinstance(probabilities, list):
        probabilities = {p["value"]: p["probability"] for p in probabilities}
    try:
        number = int(passage.get("choice") or 0)
    except (TypeError, ValueError):
        number = 0
    return {
        "label": label["choice"],
        "passage": number,
        "probabilities": {k: float(probabilities.get(k, 0.0)) for k in aj.LABELS},
        "confidence": label.get("confidence"),
    }


# ---------------------------------------------------------------------- calls and the ledger


def ledger() -> dict[str, dict[str, float]]:
    if not LEDGER.exists():
        return {}
    data: dict[str, dict[str, float]] = json.loads(LEDGER.read_text(encoding="utf-8"))
    return data


def usd(judge: str, usage: Mapping[str, Any]) -> float:
    if judge == LUNA:
        return float(usage.get("input_tokens") or 0) * LUNA_USD_PER_M / 1e6
    return float(usage.get("cost") or 0.0)


def _record(judge: str, usage: Mapping[str, Any]) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with _lock, LEDGER.with_suffix(".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = ledger()
        entry = data.setdefault(judge, {"calls": 0, "input_tokens": 0, "usd": 0.0})
        entry["calls"] += 1
        entry["input_tokens"] += float(usage.get("input_tokens") or 0)
        entry["usd"] = round(entry["usd"] + usd(judge, usage), 8)
        tmp = LEDGER.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(LEDGER)


def _reserve(judge: str) -> None:
    spent = ledger().get(judge, {}).get("usd", 0.0)
    if spent + WORST_CALL_USD > CAP_USD:
        raise BudgetExceededError(f"{judge}: ${spent:.2f} spent, cap ${CAP_USD:.2f}")


def _connection(host: str, *, fresh: bool = False) -> http.client.HTTPSConnection:
    """One kept-alive connection per thread, so a timed call does not pay for a handshake."""
    held: dict[str, http.client.HTTPSConnection] = _local.__dict__.setdefault("held", {})
    if fresh and host in held:
        held.pop(host).close()
    if host not in held:
        held[host] = http.client.HTTPSConnection(host, timeout=180)
    return held[host]


def _backoff(attempt: int, retry_after: str | None) -> float:
    if retry_after and retry_after.isdigit():
        return min(float(retry_after), 300.0)
    return float(min(300.0, 5 * 2**attempt + random.uniform(0, 3)))  # noqa: S311 - jitter


def call(judge: str, request: Mapping[str, Any]) -> dict[str, Any]:
    """One reply: the parsed answer with ``ms``, ``server_ms``, ``tokens``, ``usd`` and the
    model the API says answered. Rate limits, server errors and timeouts back off and retry."""
    host, path, _, variable = APIS[judge]
    _reserve(judge)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {os.environ[variable]}",
    }
    payload = json.dumps(request).encode()
    failure = ""
    for attempt in range(ATTEMPTS):
        retry_after = None
        try:
            connection = _connection(host, fresh=attempt > 0)
            t0 = time.perf_counter()
            connection.request("POST", path, body=payload, headers=headers)
            response = connection.getresponse()
            raw = response.read()
            ms = (time.perf_counter() - t0) * 1000
        except (OSError, http.client.HTTPException) as exc:
            failure = repr(exc)
        else:
            if response.status == 200:  # noqa: PLR2004
                reply = json.loads(raw)
                usage = reply.get("usage") or {}
                _record(judge, usage)
                server = response.getheader("openai-processing-ms")
                return {
                    **parse(judge, reply),
                    "ms": ms,
                    "server_ms": float(server) if server else None,
                    "tokens": usage.get("input_tokens"),
                    "usd": usd(judge, usage),
                    "model": reply.get("model"),
                    "attempts": attempt + 1,
                }
            failure = f"HTTP {response.status}"
            if response.status not in RETRY_STATUS:
                raise ApiError(f"{judge}: {failure} {raw[:200].decode(errors='replace')}")
            retry_after = response.getheader("Retry-After")
        wait = _backoff(attempt, retry_after)
        print(f"{judge}: {failure}, retry in {wait:.0f} s", file=sys.stderr, flush=True)
        time.sleep(wait)
    raise ApiError(f"{judge}: still failing after {ATTEMPTS} attempts ({failure})")


# ---------------------------------------------------------------------- labelling


def clauses(kind: str, data: Mapping[str, Any]) -> dict[str, tuple[str, tuple[str, ...], str]]:
    """``{sha: (clause, candidates, answer so far)}`` for every prompt of ``kind``. The sha is
    the short-reply prompt's, so the labels replay like any other judge's."""
    wanted = fa.requests(kind, data)
    out = {}
    for u in data["units"]:
        key = u["key"]
        for r in (data["calls"][key], data["free"].get(key)):
            for clause, candidates in (r or {}).get("calls", []):
                sha = aj.prompt_key(fa.short_prompt(clause, candidates, u["prefix"]))
                if sha in wanted:
                    out[sha] = (clause, tuple(candidates), u["prefix"])
    if set(out) != set(wanted):
        raise RuntimeError(f"{len(set(wanted) - set(out))} prompts of {kind!r} not rebuilt")
    return {sha: out[sha] for sha in wanted}


def label(judge: str, *, seq: bool = False) -> None:
    kind = "seq-short" if seq else "short"
    data = fa.recorded()
    asked = clauses(kind, data)
    file = fa.path(judge, kind)
    have = set(fa.read(judge, kind))
    todo = [sha for sha in asked if sha not in have]
    print(f"{fb.SET} {judge} {kind}: {len(asked)} clauses, {len(todo)} to ask", flush=True)
    counts = {"ok": 0, "refusal": 0, "failed": 0, "skipped_cap": 0}
    capped = threading.Event()

    def one(sha: str) -> None:
        if capped.is_set():
            counts["skipped_cap"] += 1
            return
        try:
            result = call(judge, body(judge, *asked[sha]))
        except BudgetExceededError as exc:
            capped.set()
            counts["skipped_cap"] += 1
            print(f"cap reached ({exc})", flush=True)
            return
        except (ApiError, KeyError, ValueError) as exc:
            result = {"label": "error", "passage": 0, "reason": repr(exc)[:300], "ms": 0}
        with _lock:
            file.parent.mkdir(parents=True, exist_ok=True)
            with file.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"sha": sha, **result}, ensure_ascii=False) + "\n")
            state = result["label"]
            counts[
                "ok" if state in aj.LABELS else "refusal" if state == "refusal" else "failed"
            ] += 1
            n = counts["ok"] + counts["refusal"] + counts["failed"]
        if n % 50 == 0:
            print(f"{judge}: {n}/{len(todo)}", flush=True)

    if seq:  # one at a time on a connection opened before the first timed call
        _connection(APIS[judge][0]).connect()
        for sha in todo:
            one(sha)
    else:
        with ThreadPoolExecutor(WORKERS) as pool:
            list(pool.map(one, todo))
    print(json.dumps({"counts": counts, "ledger": ledger().get(judge, {})}), flush=True)


# ---------------------------------------------------------------------- the report


def rows(judge: str, kind: str = "short") -> list[dict[str, Any]]:
    """The last row written for each prompt, valid or not."""
    file = fa.path(judge, kind)
    if not file.exists():
        return []
    last = {r["sha"]: r for r in map(json.loads, file.read_text("utf-8").splitlines())}
    return list(last.values())


def at_threshold(labels: Mapping[str, Mapping[str, Any]], t: float) -> dict[str, dict[str, Any]]:
    """Supported only when its probability is at least ``t``; otherwise the likelier of the
    other two labels."""
    out = {}
    for sha, r in labels.items():
        p = r["probabilities"]
        if p["supported"] >= t:
            chosen = "supported"
        else:
            chosen = "contradicted" if p["contradicted"] > p["not_stated"] else "not_stated"
        out[sha] = {**r, "label": chosen}
    return out


def chosen_threshold(sweep: Mapping[str, float]) -> float:
    """The most accurate threshold; of equals, the one nearest 0.5, then the lower."""
    best = max(sweep.values())
    return min((float(t) for t, a in sweep.items() if a == best), key=lambda t: (abs(t - 0.5), t))


def report() -> None:  # noqa: PLR0915 - one pass over the readings
    data = fa.recorded()
    us, built = data["units"], data["built"]
    graded = fe.merged_grades(us)
    units = [
        {**u, "right": graded[u["key"]] == "yes", "wrong": graded[u["key"]] == "no"} for u in us
    ]
    units = [u for u in units if u["right"] or u["wrong"]]
    asked = fa.requests("short", data)
    teacher = fa.read(fa.TEACHER, "short")
    out: dict[str, Any] = {"set": fb.SET, "sentences": len(units), "prompts": len(asked)}
    out |= {"arms": {}, "against_qwen27": {}, "same_label_as_qwen27": {}, "replies": {}}
    out |= {"time": {}, "usd_per_1000_calls": {}, "threshold": {}}
    correct: dict[str, dict[str, bool]] = {}

    def accuracy(name: str, labels: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
        scorer = fa.Scorer(name, "short", labels, {})
        verdicts = fa.replay(us, built, scorer, set(), aj.STRICT_FIGURES)
        score: dict[str, Any] = fr.score(units, verdicts)
        correct[name] = {u["key"]: fr._rolled(verdicts[u["key"]]) == u["wrong"] for u in units}
        total = score["total"]
        hits = total["right"] - total["false_rollbacks"] + total["caught"]
        total["interval_95"] = fa.wilson(hits, len(units))
        return score

    base = "Qwen 27B 4-bit"
    out["arms"][base] = accuracy(base, teacher)
    student = fa.read("minicpm5-1b-student2", "short")
    if student:
        out["arms"]["MiniCPM5-1B, trained on more"] = accuracy("1b", student)
    for judge, title in TITLES.items():
        labels = fa.read(judge, "short")
        if not labels:
            continue
        written = rows(judge)
        out["replies"][title] = {
            "valid": len(labels),
            "refused": sum(r["label"] == "refusal" for r in written),
            "failed": sum(r["label"] == "error" for r in written),
            "not_asked": len(asked) - len(written),
            "models": sorted({str(r["model"]) for r in written if r.get("model")}),
        }
        out["arms"][title] = accuracy(title, labels)
        gap = out["arms"][base]["total"]["accuracy"] - out["arms"][title]["total"]["accuracy"]
        test = fa.paired(correct[title], correct[base])
        out["against_qwen27"][title] = {
            **test,
            "points_under_qwen27": round(100 * gap, 1),
            "near_qwen27": bool(gap <= fa.NEAR),
            "better_than_qwen27": bool(gap < 0 and test["p"] < fa.ALPHA),
        }
        both = [k for k in asked if k in labels and k in teacher]
        out["same_label_as_qwen27"][title] = {
            "same": sum(labels[k]["label"] == teacher[k]["label"] for k in both),
            "of": len(both),
        }
        paid = [r for r in written if r.get("usd") is not None]
        out["usd_per_1000_calls"][title] = round(1000 * sum(r["usd"] for r in paid) / len(paid), 4)
        timed = [r for r in rows(judge, "seq-short") if r["label"] in aj.LABELS]
        if timed:
            out["time"][title] = aj.latency(timed)
            server = sorted(r["server_ms"] for r in timed if r.get("server_ms"))
            if server:
                out["time"][title]["server_p50_ms"] = server[len(server) // 2]
        sweep = {
            f"{t:.2f}": accuracy("sweep", at_threshold(labels, t))["total"]["accuracy"]
            for t in THRESHOLDS
        }
        out["threshold"][title] = {"sweep": sweep}
        if fb.SET == TUNED_ON:
            out["threshold"][title]["chosen"] = chosen_threshold(sweep)
            continue
        tuned = ROOT / "results" / f"{TUNED_ON}_arms" / "decisions.json"
        if tuned.exists():
            t = json.loads(tuned.read_text("utf-8"))["threshold"][title]["chosen"]
            name = f"{title}, threshold from test 1"
            score = accuracy(name, at_threshold(labels, t))
            gap = out["arms"][base]["total"]["accuracy"] - score["total"]["accuracy"]
            out["threshold"][title] |= {
                "from_test_1": t,
                "total": score["total"],
                **fa.paired(correct[name], correct[base]),
                "points_under_qwen27": round(100 * gap, 1),
            }
    seq = fa.path(fa.TEACHER, "seq-short")
    if seq.exists():
        timed = [json.loads(x) for x in seq.read_text("utf-8").splitlines()]
        out["time"][base] = aj.latency([r for r in timed if r["label"] in aj.LABELS])
    out["ledger"] = ledger()
    fa.OUT.mkdir(parents=True, exist_ok=True)
    (fa.OUT / "decisions.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    for title, s in out["arms"].items():
        cells = "  ".join(
            f"{g}: {s[g]['false_rollbacks']}/{s[g]['caught']} {s[g]['accuracy']}"
            for g in ("software", "statutes", "total")
        )
        print(f"{title:32} {cells}  {s['total']['interval_95']}")
    keys = ("against_qwen27", "same_label_as_qwen27", "replies", "time", "usd_per_1000_calls")
    print(json.dumps({k: out[k] for k in keys} | {"threshold": out["threshold"]}, indent=1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["label", "report"])
    parser.add_argument("judge", nargs="?", choices=sorted(SHORT))
    parser.add_argument("--seq", action="store_true", help="40 clauses one at a time, for timing")
    args = parser.parse_args()
    if args.command == "report":
        report()
    elif not args.judge:
        parser.error("label needs a judge")
    else:
        label(SHORT[args.judge], seq=args.seq)


if __name__ == "__main__":
    main()
