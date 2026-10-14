"""Stop 67 (docs/GRID.md § Stop 67), on this machine: the states, the judge's prompts for the
retries, and the factor for KA. The generator runs in ``scripts/kv_retry.py`` on Modal.

  FRESH_SET=fresh uv run --extra hf python scripts/retry_states.py build   # → states.fresh.jsonl
  FRESH_SET=fresh2 uv run --extra hf python scripts/retry_states.py build
  uv run --extra hf python scripts/retry_states.py pilot                   # the stop 29 states
  uv run --with modal modal run scripts/modal_distill.py::retry_pilot      # KA at three factors
  uv run --with modal modal run scripts/modal_distill.py::retry_judge --kind pilot
  uv run python scripts/retry_states.py factor                             # → factor.json

Files go to ``results/retry/``. States and retries quote statute text and stay git-ignored.
Nothing here calls a model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "batteries/verifier"))

import auditor_judge as aj  # type: ignore[import-not-found]  # noqa: E402

from legal_rag_verifier.engine import (  # noqa: E402
    INJECT_TEMPLATE,
    SYSTEM_PROMPT,
    InFlightGenerator,
    _Point,
    _Stream,
)
from legal_rag_verifier.premise import Premise  # noqa: E402
from legal_rag_verifier.verifier import SentenceVerdict, Verifier  # noqa: E402

OUT = ROOT / "results/retry"
JUDGE = "qwen27-ar4"
FACTORS = (1.5, 2.0, 4.0)
SECONDARY = 40  # false-rollback states drawn
SEED = 20261014
COPY_SHARE = 0.8  # a retry copies the passage if this share of its word 5-grams is in it
GRAM = 5
# Stop 30's turn in Qwen 2.5's chat format (scripts/grid_qwen.py, "v2"), worded per domain.
TURN = (
    '<|im_end|>\n<|im_start|>user\nThe {what} relevant to the question "{{query}}":\n'
    "{{source}}\n\nContinue your answer to the question from exactly where it stops."
    "<|im_end|>\n<|im_start|>assistant\n"
)
TURNS = {"software": TURN.format(what="documentation"), "legal": TURN.format(what="provision")}


# ---------------------------------------------------------------------- pure helpers


def state_hash(set_name: str, unit: str) -> str:
    return hashlib.sha256(f"{set_name}\x00{unit}".encode()).hexdigest()[:16]


def first_rollbacks(
    units: Sequence[Mapping[str, Any]], verdicts: Mapping[str, Mapping[str, Any]]
) -> dict[str, str]:
    """Per answer (``id:mode``), the key of its first rolled-back unit."""
    out: dict[str, str] = {}
    for u in units:
        answer = f"{u['id']}:{u['mode']}"
        if answer not in out and verdicts[u["key"]]["verdict"] != "EMIT":
            out[answer] = u["key"]
    return out


def words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def copies(retry: str, passage: str) -> bool:
    """At least 80 % of the retry's word 5-grams are in the passage (short ones never copy)."""
    w = words(retry)
    if len(w) < GRAM:
        return False
    grams = [tuple(w[i : i + GRAM]) for i in range(len(w) - GRAM + 1)]
    p = words(passage)
    have = {tuple(p[i : i + GRAM]) for i in range(len(p) - GRAM + 1)}
    return sum(g in have for g in grams) / len(grams) >= COPY_SHARE


def choose_factor(passed: Mapping[float, int]) -> float:
    """The factor with the most passed retries that do not copy; a tie goes to the smaller."""
    return min(passed, key=lambda f: (-passed[f], f))


def span_of(tokenizer: Any, text: str, start: int, end: int) -> tuple[int, int]:
    """Token indices ``[a, b)`` of ``text`` (encoded alone) over characters ``[start, end)``."""
    offsets = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)[
        "offset_mapping"
    ]
    inside = [i for i, (a, b) in enumerate(offsets) if a < end and b > start]
    return inside[0], inside[-1] + 1


# ---------------------------------------------------------------------- tokens


def local_backend() -> Any:
    from replay_states import (  # type: ignore[import-not-found]  # noqa: PLC0415
        MODEL,
        REVISION,
        LocalTokenizer,
    )
    from transformers import AutoTokenizer  # noqa: PLC0415

    return LocalTokenizer(AutoTokenizer.from_pretrained(MODEL, revision=REVISION))


def tokens(
    backend: Any,
    *,
    messages: Sequence[Mapping[str, str]],
    committed: str,
    rejected: str,
    premise: Premise,
    verdict: SentenceVerdict | None,
    aligned: Sequence[int],
    query: str,
    domain: str,
) -> dict[str, Any] | None:
    """Every token list the arms need; None when X aligned to no window."""
    engine = InFlightGenerator(backend, Verifier(), steering="allow")
    source, windows = engine._source_text(premise, aligned, set())
    if not windows:
        return None
    prompt = list(backend.chat(messages))
    system = backend.tokenizer.apply_chat_template([dict(messages[0])], tokenize=True)
    system = list(system["input_ids"] if isinstance(system, Mapping) else system)
    if prompt[: len(system)] != system:
        raise RuntimeError("the system turn is not a prefix of the prompt")
    done = list(backend.encode(committed))
    x = list(backend.encode(rejected))
    turn_text = TURNS[domain].format(query=query, source=source)
    at = turn_text.index(source)
    out: dict[str, Any] = {
        "prompt": prompt,
        "committed": done,
        "x": x,
        "x_turn": list(backend.encode(rejected.strip())),
        "turn": list(backend.encode(turn_text)),
        "turn_span": list(span_of(backend.tokenizer, turn_text, at, at + len(source))),
        "passage": list(backend.encode(INJECT_TEMPLATE.format(source=source))),
        "passage_text": source,
        "windows": windows,
        "far_at": len(system),
        "b_seed": [],
        "b_constraint": None,
        "round_trip": backend.decode(done) == committed,
    }
    if verdict is not None:
        stream = _Stream(answer=list(done), context=list(done))
        retry = engine._steer(_Point(len(done)), x, verdict, premise, stream, query=query)
        out["b_seed"] = list(retry.seed)
        out["b_constraint"] = retry.constraint.to_dict() if retry.constraint else None
        out["b_steering"] = retry.steering
    return out


# ---------------------------------------------------------------------- the test states


def build() -> dict[str, Any]:
    import random  # noqa: PLC0415

    import fresh_arms as fa  # type: ignore[import-not-found]  # noqa: PLC0415
    import fresh_battery as fb  # type: ignore[import-not-found]  # noqa: PLC0415
    import fresh_eval as fe  # type: ignore[import-not-found]  # noqa: PLC0415
    from replay_states import committed_text  # noqa: PLC0415

    data = fa.recorded()
    us, built = data["units"], data["built"]
    labels = fa.read(JUDGE, "short")
    scorer = fa.Scorer(JUDGE, "short", labels, {})
    verifier = Verifier(scorer, aj.STRICT_FIGURES)
    verdicts: dict[str, SentenceVerdict] = {}
    for u in us:
        scorer.unit = u
        verdicts[u["key"]] = verifier.check_sentence(
            built[u["key"]], u["sentence"], query=u["query"]
        )
    names = {k: {"verdict": v.verdict.name} for k, v in verdicts.items()}
    check = fa.replay(us, built, fa.Scorer(JUDGE, "short", labels, {}), set(), aj.STRICT_FIGURES)
    if any(check[k]["verdict"] != names[k]["verdict"] for k in names):
        raise RuntimeError("verdicts differ from the stop 61 replay")
    graded = fe.merged_grades(us)
    firsts = first_rollbacks(us, names)
    by_key = {u["key"]: u for u in us}
    answers = fb.answers()
    messages = {r["key"]: r["messages"] for r in fb.requests()}
    backend = local_backend()
    wrong = [k for k in firsts.values() if graded[k] == "no"]
    right = sorted(k for k in firsts.values() if graded[k] == "yes")
    rng = random.Random(SEED)  # noqa: S311 - a draw, not a secret
    drawn = sorted(rng.sample(right, min(SECONDARY, len(right))))
    counts = {
        "answers": len(answers),
        "answers_with_a_rollback": len(firsts),
        "x_wrong": len(wrong),
        "x_right": len(right),
        "x_unsure": sum(graded[k] == "unsure" for k in firsts.values()),
        "false_rollback_states_drawn": len(drawn),
        "no_aligned_window": 0,
        "round_trip_failed": 0,
    }
    states = []
    for key in [*sorted(wrong), *drawn]:
        u = by_key[key]
        answer = f"{u['id']}:{u['mode']}"
        n = int(key.rsplit(":", 1)[1])
        before = [
            p["sentence"]
            for p in us
            if p["key"].rsplit(":", 1)[0] == answer and int(p["key"].rsplit(":", 1)[1]) < n
        ]
        text = answers[answer]["text"]
        done = committed_text(text, before)
        end = text.index(u["sentence"], len(done)) + len(u["sentence"])
        v = verdicts[key]
        t = tokens(
            backend,
            messages=messages[answer],
            committed=done,
            rejected=text[len(done) : end],
            premise=built[key],
            verdict=v,
            aligned=v.aligned,
            query=u["query"],
            domain=u["domain"],
        )
        if t is None:
            counts["no_aligned_window"] += 1
            continue
        counts["round_trip_failed"] += not t["round_trip"]
        states.append(
            {
                "hash": state_hash(fb.SET, key),
                "set": fb.SET,
                "unit": key,
                "id": u["id"],
                "mode": u["mode"],
                "domain": u["domain"],
                "query": u["query"],
                "prefix": u["prefix"],
                "x_text": u["sentence"],
                "x_grade": graded[key],
                "reasons": [r.name for r in v.reasons],
                **t,
            }
        )
    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / f"states.{fb.SET}.jsonl", states)
    counts["states"] = len(states)
    return counts


def pilot() -> dict[str, Any]:
    """The 46 parity states of stop 29: the 7B with the provisions in the prompt, other
    questions."""
    from grid_prompts import premise, rows  # type: ignore[import-not-found]  # noqa: PLC0415
    from replay_states import GRID, load, shared_states  # noqa: PLC0415

    a, b = load(GRID / "4B.jsonl"), load(GRID / "4B-inject.jsonl")
    states, _ = shared_states(a, b)
    parity = {
        r["id"]: r
        for r in map(json.loads, (GRID / "replay/arms.jsonl").read_text("utf-8").splitlines())
        if r["parity"]
    }
    by_id = {r["id"]: r for r in rows("test")}
    backend = local_backend()
    engine = InFlightGenerator(backend, Verifier(), system_prompt=SYSTEM_PROMPT)
    out = []
    for s in states:
        if s.id not in parity or not s.b_retry or not s.b_retry.get("injected"):
            continue
        row = by_id[s.id]
        built = premise(row)
        t = tokens(
            backend,
            messages=engine.messages(row["query"], built),
            committed=s.committed,
            rejected=s.rejected,
            premise=built,
            verdict=None,
            aligned=s.b_retry["injected"]["windows"],
            query=row["query"],
            domain="legal",
        )
        if t is None:
            continue
        t["x"] = parity[s.id]["X"]["tokens"]  # the draft as the server wrote it
        out.append(
            {
                "hash": state_hash("pilot", s.id),
                "set": "pilot",
                "unit": s.id,
                "id": s.id,
                "domain": "legal",
                "query": row["query"],
                "prefix": s.committed,
                "x_text": s.rejected,
                **t,
            }
        )
    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "states.pilot.jsonl", out)
    return {"states": len(out)}


# ---------------------------------------------------------------------- the judge on the retries


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text("utf-8").splitlines() if x.strip()]


def write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def premises_for(states: Sequence[Mapping[str, Any]]) -> dict[str, Premise]:
    """Each state's premise, keyed by its hash."""
    out: dict[str, Premise] = {}
    pilot_rows = [s for s in states if s["set"] == "pilot"]
    if pilot_rows:
        from grid_prompts import premise, rows  # noqa: PLC0415

        by_id = {r["id"]: r for r in rows("test")}
        out |= {s["hash"]: premise(by_id[s["id"]]) for s in pilot_rows}
    fresh = [s for s in states if s["set"] != "pilot"]
    if fresh:
        import fresh_battery as fb  # noqa: PLC0415

        by_id = {r["id"]: r for r in fb.rows()}
        out |= {s["hash"]: fb.premise(by_id[s["id"]]) for s in fresh}
    return out


def sentence_units(
    states: Sequence[Mapping[str, Any]], retries: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Every non-empty retry and follow-on sentence, as a unit for the verifier."""
    by_hash = {s["hash"]: s for s in states}
    out = []
    for r in retries:
        s = by_hash[r["hash"]]
        for name, arm in r["arms"].items():
            if arm["retry"]:
                out.append(
                    {
                        "key": f"{r['hash']}:{name}:retry",
                        "state": r["hash"],
                        "query": s["query"],
                        "prefix": s["prefix"],
                        "sentence": arm["retry"],
                    }
                )
            if arm["retry"] and arm["follow"]:
                prefix = f"{s['prefix']} {arm['retry']}".strip()
                out.append(
                    {
                        "key": f"{r['hash']}:{name}:follow",
                        "state": r["hash"],
                        "query": s["query"],
                        "prefix": prefix,
                        "sentence": arm["follow"],
                    }
                )
    return out


def judge_requests(
    units: Sequence[Mapping[str, Any]], built: Mapping[str, Premise]
) -> dict[str, str]:
    """The judge's short-reply prompts for every clause the verifier sends it."""
    keyed = {u["key"]: built[u["state"]] for u in units}
    out: dict[str, str] = {}
    for u, r in zip(units, aj.record(units, keyed, config=aj.STRICT_FIGURES), strict=True):
        for clause, candidates in r["calls"]:
            user = aj.short_prompt(clause, candidates, u["prefix"])
            out[aj.prompt_key(user)] = user
    return out


class ShortScorer:
    """The judge's recorded short-reply labels in the entailment check's place."""

    def __init__(self, labels: Mapping[str, Mapping[str, Any]]) -> None:
        self.model_id = f"{JUDGE}/short"
        self.labels = labels
        self.prefix = ""
        self.missing = 0

    def score(self, premises: Sequence[str], hypothesis: str) -> list[Any]:
        label = self.labels.get(aj.prompt_key(aj.short_prompt(hypothesis, premises, self.prefix)))
        if label is None or label["label"] not in aj.LABELS:
            self.missing += 1
            return list(aj.one_hot("not_stated", 0, len(premises)))
        return list(aj.one_hot(label["label"], int(label.get("passage") or 0), len(premises)))


def verdicts(
    units: Sequence[Mapping[str, Any]],
    built: Mapping[str, Premise],
    labels: Mapping[str, Mapping[str, Any]],
) -> dict[str, str]:
    scorer = ShortScorer(labels)
    verifier = Verifier(scorer, aj.STRICT_FIGURES)
    out = {}
    for u in units:
        scorer.prefix = u["prefix"]
        v = verifier.check_sentence(built[u["state"]], u["sentence"], query=u["query"])
        out[u["key"]] = v.verdict.name
    return out


def labels_path(kind: str) -> Path:
    return OUT / f"labels.{kind}.jsonl"


def factor() -> dict[str, Any]:
    """KA's factor from the pilot retries and the judge's labels on them."""
    states = read_jsonl(OUT / "states.pilot.jsonl")
    runs = read_jsonl(OUT / "retries.pilot.jsonl")
    labels = {r["sha"]: r for r in read_jsonl(labels_path("pilot"))}
    by_hash = {s["hash"]: s for s in states}
    built = premises_for(states)
    passed: dict[float, int] = {}
    detail: dict[str, Any] = {}
    for f in FACTORS:
        rows = [{**r, "arms": {"KA": r["arms"][f"KA@{f}"]}} for r in runs]
        units = [u for u in sentence_units(states, rows) if u["key"].endswith(":retry")]
        v = verdicts(units, built, labels)
        ok = copied = 0
        for u in units:
            copy = copies(u["sentence"], by_hash[u["state"]]["passage_text"])
            copied += copy
            ok += v[u["key"]] == "EMIT" and not copy
        passed[f] = ok
        detail[str(f)] = {
            "states": len(runs),
            "retries": len(units),
            "passed_not_copied": ok,
            "copied": copied,
            "share_mean": _mean([r["arms"][f"KA@{f}"]["share"] for r in runs]),
        }
    chosen = choose_factor(passed)
    out = {"factor": chosen, "by_factor": detail}
    (OUT / "factor.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return out


def _mean(values: Sequence[float | None]) -> float | None:
    have = [v for v in values if v is not None]
    return round(sum(have) / len(have), 4) if have else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["build", "pilot", "factor"])
    command = parser.parse_args().command
    if command == "build":
        print(json.dumps({"set": os.environ.get("FRESH_SET", "fresh"), **build()}, indent=1))
    elif command == "pilot":
        print(json.dumps(pilot(), indent=1))
    else:
        print(json.dumps(factor(), indent=1))


if __name__ == "__main__":
    main()
