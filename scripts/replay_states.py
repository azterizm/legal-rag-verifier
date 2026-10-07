"""Stop 29: the rollback states arms A (4B) and B (4B-inject) share, rebuilt for replay.

A and B run the same engine until the first rollback: greedy decoding, the same prompt and the same
auditor. So in every answer with a rollback, both arms reach the first rollback point with the same
committed text and the same rejected draft, and their first retries start from one state. This
module extracts those states from the traces and rebuilds their tokens with the generator's
tokenizer, checked against what the traces recorded:

- the prompt length (``prompt_tokens``);
- the injected source's length (B's ``injected.tokens``), rebuilt by the engine's own code;
- the committed answer's length: B's injected retry reuses the prompt and the committed answer
  from the prefix cache and nothing else, so its first decode call's cache hit is
  ``len(prompt) + len(committed)`` (checked on retries of one or two decode calls).

  uv run python scripts/replay_states.py      # → results/grid/replay_states.json
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from math import comb
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "batteries/verifier"))

from legal_rag_verifier.backends._tokenizer import TokenizerMixin  # noqa: E402
from legal_rag_verifier.engine import InFlightGenerator, Segment  # noqa: E402
from legal_rag_verifier.verifier import Verifier  # noqa: E402

GRID = ROOT / "results/grid"
OUT = GRID / "replay_states.json"
MODEL = "Qwen/Qwen2.5-7B-Instruct"
REVISION = "a09a35458c702b33eeacc393d103063234e8bc28"


@dataclass(frozen=True)
class State:
    """One first-rollback state both arms reached, and each arm's first retry from it."""

    id: str
    point: int  # index of the rolled-back sentence in the trace
    committed: str  # answer text before the rolled-back sentence
    rejected: str  # the first draft both arms rejected
    a_retry: dict[str, Any] | None  # None when A refused without a retry
    b_retry: dict[str, Any] | None

    @staticmethod
    def passed(retry: dict[str, Any] | None) -> bool:
        return retry is not None and retry["verdict"]["verdict"] == "EMIT"


def load(path: Path) -> dict[str, dict[str, Any]]:
    records = (json.loads(x) for x in path.read_text(encoding="utf-8").splitlines())
    return {r["id"]: r for r in records}


def first_point(record: dict[str, Any]) -> int | None:
    sentences = record["trace"]["sentences"]
    return next((i for i, s in enumerate(sentences) if s["rollbacks"]), None)


def committed_text(answer: str, sentences: Sequence[str]) -> str:
    """The answer up to the end of the last of ``sentences`` (each found in order)."""
    pos = 0
    for sentence in sentences:
        found = answer.find(sentence, pos)
        if found < 0:
            raise ValueError(f"sentence not in answer: {sentence[:60]!r}")
        pos = found + len(sentence)
    return answer[:pos]


def _retry(point: dict[str, Any]) -> dict[str, Any] | None:
    attempts: list[dict[str, Any]] = point["attempts"]
    return attempts[1] if len(attempts) > 1 else None


def shared_states(
    a: dict[str, dict[str, Any]], b: dict[str, dict[str, Any]]
) -> tuple[list[State], list[str]]:
    """States both arms reached (same committed sentences, same rejected draft), and the ids of
    answers where the arms diverged before their first rollback."""
    states: list[State] = []
    diverged: list[str] = []
    for key in sorted(a.keys() & b.keys()):
        ia, ib = first_point(a[key]), first_point(b[key])
        if ia is None and ib is None:
            continue
        sa, sb = a[key]["trace"]["sentences"], b[key]["trace"]["sentences"]
        before = [s["text"] for s in sa[: ia or 0]]
        same = (
            ia is not None
            and ia == ib
            and before == [s["text"] for s in sb[:ib]]
            and sa[ia]["attempts"][0]["verdict"]["text"] == sb[ia]["attempts"][0]["verdict"]["text"]
        )
        if not same or ia is None:
            diverged.append(key)
            continue
        states.append(
            State(
                key,
                ia,
                committed_text(a[key]["answer"], before),
                sa[ia]["attempts"][0]["verdict"]["text"],
                _retry(sa[ia]),
                _retry(sb[ia]),
            )
        )
    return states, diverged


def mcnemar(only_a: int, only_b: int) -> float:
    """Exact two-sided McNemar p-value from the discordant pairs."""
    n = only_a + only_b
    if n == 0:
        return 1.0
    tail = sum(comb(n, k) for k in range(min(only_a, only_b) + 1)) / float(2**n)
    return min(1.0, 2 * tail)


def paired(states: Sequence[State]) -> dict[str, Any]:
    """First-retry pass at the shared states, A against B, with McNemar's exact test."""
    a = [State.passed(s.a_retry) for s in states]
    b = [State.passed(s.b_retry) for s in states]
    only_a = sum(x and not y for x, y in zip(a, b, strict=True))
    only_b = sum(y and not x for x, y in zip(a, b, strict=True))
    return {
        "states": len(states),
        "a_first_retry_passed": sum(a),
        "b_first_retry_passed": sum(b),
        "both": sum(x and y for x, y in zip(a, b, strict=True)),
        "only_a": only_a,
        "only_b": only_b,
        "neither": sum(not x and not y for x, y in zip(a, b, strict=True)),
        "b_retries_injected": sum(bool(s.b_retry and s.b_retry.get("injected")) for s in states),
        "mcnemar_p": round(mcnemar(only_a, only_b), 6),
    }


def downstream(records: dict[str, dict[str, Any]], ids: Sequence[str]) -> dict[str, Any]:
    """Sentences after the first rollback point of each answer: how many first drafts passed."""
    after = clean = 0
    for key in ids:
        point = first_point(records[key])
        if point is None:
            continue
        later = records[key]["trace"]["sentences"][point + 1 :]
        after += len(later)
        clean += sum(s["rollbacks"] == 0 for s in later)
    return {"sentences": after, "first_draft_passed": clean}


# ---------------------------------------------------------------------- token rebuild


class LocalTokenizer(TokenizerMixin):
    """The generator's tokenizer as an engine backend that can only tokenize."""

    name = "local-tokenizer"

    def __init__(self, tokenizer: Any) -> None:
        self.tokenizer = tokenizer
        self.model_id = f"{MODEL}@{REVISION[:8]}"

    def extend(self, *args: Any, **kwargs: Any) -> Segment:
        raise NotImplementedError("tokenizer only")


def rebuild(
    state: State, row: dict[str, Any], record: dict[str, Any], engine: InFlightGenerator
) -> dict[str, Any]:
    """Tokens of the state and the checks against the trace."""
    from grid_prompts import premise  # type: ignore[import-not-found]  # noqa: PLC0415

    built = premise(row)
    backend = engine.backend
    prompt = backend.chat(engine.messages(row["query"], built))
    committed = backend.encode(state.committed)
    check: dict[str, Any] = {
        "id": state.id,
        "prompt_tokens": len(prompt),
        "prompt_ok": len(prompt) == record["trace"]["prompt_tokens"],
        "committed_tokens": len(committed),
        "round_trip_ok": backend.decode(committed) == state.committed,
    }
    injected = state.b_retry["injected"] if state.b_retry else None
    if injected:
        note, windows = engine._source(built, injected["windows"], set())
        check["note_ok"] = windows == injected["windows"] and len(note) == injected["tokens"]
        retry = state.b_retry or {}  # an injection is only recorded on a retry
        reused = len(prompt) + len(committed)
        calls, hit = retry["decode_calls"], retry["prefix_cache_hit_tokens"]
        expected = {
            1: reused,
            # the second call is the engine's one-token peek after a trailing ".": all of its
            # input is cached (prompt, committed answer, source, and the draft but its last token)
            2: reused + (reused + len(note) + retry["tokens"] - 1),
        }.get(calls)
        if expected is not None:
            check["cache_hit_ok"] = hit == expected
    return check


def main() -> None:
    from grid_prompts import rows  # noqa: PLC0415
    from grid_qwen import INJECT, INJECT_STYLE  # type: ignore[import-not-found]  # noqa: PLC0415
    from transformers import AutoTokenizer  # noqa: PLC0415

    a, b = load(GRID / "4B.jsonl"), load(GRID / "4B-inject.jsonl")
    states, diverged = shared_states(a, b)
    ids = [s.id for s in states]
    tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=REVISION)
    engine = InFlightGenerator(
        LocalTokenizer(tokenizer),
        Verifier(),
        steering="inject",
        inject_template=INJECT[INJECT_STYLE],
    )
    by_id = {r["id"]: r for r in rows("test")}
    checks = [rebuild(s, by_id[s.id], b[s.id], engine) for s in states]

    def count(key: str) -> str:
        have = [c[key] for c in checks if key in c]
        return f"{sum(have)}/{len(have)}"

    out = {
        "paired": paired(states),
        "diverged_before_first_rollback": diverged,
        "downstream": {"A": downstream(a, ids), "B": downstream(b, ids)},
        "rebuild": {
            "prompt_length_matches": count("prompt_ok"),
            "committed_round_trip": count("round_trip_ok"),
            "injected_source_length_matches": count("note_ok"),
            "cache_hit_matches_prompt_plus_committed": count("cache_hit_ok"),
        },
        "states": checks,
    }
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "states"}, indent=1))


if __name__ == "__main__":
    main()
