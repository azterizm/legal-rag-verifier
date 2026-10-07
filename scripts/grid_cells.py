"""The remediation loops of the 2x2 grid (vault 07 §5), generator-agnostic; one shared detector.

* **full retry** (4A Gemini, 4D Qwen): the whole answer is generated, checked post-hoc with
  ``Verifier.check_text`` and, if any sentence is rolled back, regenerated after the vault's
  message *"Previous response hallucinated X or missed qualification Y. Regenerate."*, at most
  ``MAX_RETRIES`` times; an answer still failing after that is released as unresolved.
* **sentence continuation** (4C Gemini): the answer is checked sentence by sentence; the verified
  prefix is kept, and generation resumes after it with the rejected sentence named. The prefix is
  passed as the model's own previous (assistant) turn plus a user turn asking it to continue (any
  chat endpoint takes this shape; assistant prefill is not relied on). Each point gets at most
  ``MAX_RETRIES`` retries, then the engine's refusal sentence, as in 4B.
* **in-flight rollback** (4B Qwen) is ``InFlightGenerator``; :func:`from_trace` maps its trace onto
  the same record.

A generator is a ``Chat``: messages → :class:`Reply`. Greedy everywhere (temperature 0), so a
retry differs from its draft only through what the remediation changes.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial
from typing import Any, TypeVar

from legal_rag_verifier.engine import DEFAULT_REFUSAL, InFlightGenerator, render_premise
from legal_rag_verifier.premise import Premise
from legal_rag_verifier.segmenter import split_sentences
from legal_rag_verifier.verifier import Reason, SentenceVerdict, Verdict, Verifier

MAX_RETRIES = 3  # your rule (2026-10-06): every cell retries a failure at most three times
MAX_TOTAL_ROLLBACKS = 8  # as the engine default
MAX_CALLS = 24  # hard stop for a continuation that never converges
FEEDBACK = "Previous response hallucinated {hallucinated}{missed}. Regenerate."
CONTINUE = "Continue your answer from exactly where it stops, without repeating any of it."
REJECTED = (
    " The next sentence you wrote was rejected because it hallucinated {hallucinated}{missed}; "
    "write that point again correctly, or leave it out."
)
MOVE_ON = " Leave that point out and go on with the rest of the answer, if there is more to say."

Messages = list[dict[str, str]]
T = TypeVar("T")


@dataclass(frozen=True)
class Reply:
    text: str
    tokens_out: int
    tokens_in: int
    latency_ns: int
    cached_tokens: int = 0
    usage: dict[str, Any] | None = None  # the API's own usage object (Gemini: thinking tokens)


Chat = Callable[[Messages], Reply]


def base_messages(query: str, premise: Premise, system_prompt: str) -> Messages:
    """The prompt every cell gets: the engine's system prompt with the premise, then the query."""
    system = system_prompt.format(premise=render_premise(premise))
    return [{"role": "system", "content": system}, {"role": "user", "content": query}]


def describe(verdicts: Sequence[SentenceVerdict]) -> tuple[str, str]:
    """X and Y for the feedback message: hallucinated claims or sentences, missed qualifiers."""
    hallucinated: list[str] = []
    missed: list[str] = []
    for v in verdicts:
        if v.verdict is not Verdict.ROLLBACK:
            continue
        if Reason.QUALIFIER_DROPPED in v.reasons:
            missed += [d for d in v.details if d not in missed] or [repr(v.text)]
        bad = [r.claim.text for r in v.claims if r.reason is not None]
        if bad:
            hallucinated += [repr(b) for b in bad if repr(b) not in hallucinated]
        elif Reason.QUALIFIER_DROPPED not in v.reasons or len(v.reasons) > 1:
            hallucinated.append(repr(v.text))
    x = "; ".join(hallucinated) if hallucinated else "nothing"
    y = f" or missed qualification {'; '.join(missed)}" if missed else ""
    return x, y


class _Clock:
    def __init__(self) -> None:
        self.t0 = time.perf_counter_ns()
        self.generation_ns = 0
        self.verify_ns = 0
        self.calls = 0
        self.tokens_out = 0
        self.tokens_in = 0
        self.cached_tokens = 0

    def chat(self, chat: Chat, messages: Messages) -> Reply:
        reply = chat(messages)
        self.calls += 1
        self.generation_ns += reply.latency_ns
        self.tokens_out += reply.tokens_out
        self.tokens_in += reply.tokens_in
        self.cached_tokens += reply.cached_tokens
        return reply

    def check(self, fn: Callable[[], T]) -> T:
        t0 = time.perf_counter_ns()
        out = fn()
        self.verify_ns += time.perf_counter_ns() - t0
        return out

    def stats(self) -> dict[str, Any]:
        wall = time.perf_counter_ns() - self.t0
        return {
            "calls": self.calls,
            "tokens_out": self.tokens_out,
            "tokens_in": self.tokens_in,
            "cached_tokens": self.cached_tokens,
            "generation_ns": self.generation_ns,
            "verify_ns": self.verify_ns,
            "wall_ns": wall,
            "decode_tok_s": round(self.tokens_out / (self.generation_ns / 1e9), 2)
            if self.generation_ns
            else None,
        }


def full_retry(
    chat: Chat, verifier: Verifier, query: str, premise: Premise, system_prompt: str
) -> dict[str, Any]:
    """Cells 4A / 4D."""
    clock = _Clock()
    messages = base_messages(query, premise, system_prompt)
    attempts: list[dict[str, Any]] = []
    discarded = 0
    while True:
        reply = clock.chat(chat, messages)
        text = reply.text.strip()
        verdicts = clock.check(partial(verifier.check_text, premise, text, query=query))
        rejected = [v for v in verdicts if v.verdict is Verdict.ROLLBACK]
        attempts.append(_attempt(text, reply, rejected))
        if not rejected or len(attempts) > MAX_RETRIES:
            break
        discarded += reply.tokens_out
        x, y = describe(rejected)
        messages = [
            *messages,
            {"role": "assistant", "content": text},
            {"role": "user", "content": FEEDBACK.format(hallucinated=x, missed=y)},
        ]
    stats = clock.stats()
    return {
        "answer": text,
        "resolved": not rejected,
        "retries": len(attempts) - 1,
        "refusals": 0,
        "tokens_discarded": discarded,
        "time_to_first_output_ns": stats["wall_ns"],  # nothing is released before the check
        "attempts": attempts,
        **stats,
    }


def continuation(
    chat: Chat, verifier: Verifier, query: str, premise: Premise, system_prompt: str
) -> dict[str, Any]:
    """Cell 4C."""
    clock = _Clock()
    base = base_messages(query, premise, system_prompt)
    committed = ""
    first_output_ns: int | None = None
    attempts: list[dict[str, Any]] = []
    retries = refusals = total = discarded = 0
    point_retries = 0
    note = ""
    while clock.calls < MAX_CALLS:
        reply = clock.chat(chat, _continue(base, committed, note))
        text = _strip_repeat(reply.text, committed)
        sentences = split_sentences(text)
        if not sentences:
            break
        kept_end, bad = 0, None
        for s in sentences:
            verdict = clock.check(partial(verifier.check_sentence, premise, s.text, query=query))
            if verdict.verdict is Verdict.ROLLBACK:
                bad = verdict
                break
            kept_end = s.end
        if kept_end:
            committed = _join(committed, text[:kept_end])
            point_retries = 0
            if first_output_ns is None:
                first_output_ns = time.perf_counter_ns() - clock.t0
        attempts.append(_attempt(text, reply, [bad] if bad else []))
        if bad is None:
            break
        discarded += _token_share(reply.tokens_out, text, kept_end)
        total += 1
        point_retries += 1
        x, y = describe([bad])
        if point_retries > MAX_RETRIES or total > MAX_TOTAL_ROLLBACKS:
            committed = _join(committed, DEFAULT_REFUSAL)
            refusals += 1
            point_retries = 0
            if first_output_ns is None:
                first_output_ns = time.perf_counter_ns() - clock.t0
            if total > MAX_TOTAL_ROLLBACKS:
                break
            note = MOVE_ON
        else:
            retries += 1
            note = REJECTED.format(hallucinated=x, missed=y)
    stats = clock.stats()
    return {
        "answer": committed,
        "resolved": refusals == 0,
        "retries": retries,
        "refusals": refusals,
        "tokens_discarded": discarded,
        "time_to_first_output_ns": first_output_ns,
        "attempts": attempts,
        **stats,
    }


def from_trace(answer: Any, wall_ns: int) -> dict[str, Any]:
    """Cell 4B: the engine's trace in the grid's record shape."""
    trace = answer.trace
    totals = trace["totals"]
    attempts = [a for s in trace["sentences"] for a in s["attempts"]]
    first = trace["sentences"][0]["attempts"] if trace["sentences"] else []
    first_ns = sum(
        a["decode_latency_ns"] + a["verdict"]["claim_latency_ns"] + a["verdict"]["nli_latency_ns"]
        for a in first
    )
    generated = sum(a["tokens"] for a in attempts)
    return {
        "answer": answer.text,
        "resolved": totals["refused"] == 0,
        "retries": totals["rollbacks"] - totals["refused"],
        "refusals": totals["refused"],
        "tokens_discarded": totals["tokens_discarded"],
        "time_to_first_output_ns": first_ns or None,  # first sentence decoded and verified
        "calls": totals["decode_calls"],
        "tokens_out": generated,
        "tokens_in": trace["prompt_tokens"],
        "cached_tokens": totals["prefix_cache_hit_tokens"],
        "generation_ns": totals["decode_latency_ns"],
        "verify_ns": totals["claim_latency_ns"] + totals["nli_latency_ns"],
        "wall_ns": wall_ns,
        "decode_tok_s": round(generated / (totals["decode_latency_ns"] / 1e9), 2)
        if totals["decode_latency_ns"]
        else None,
        "trace": trace,
    }


def in_flight(engine: InFlightGenerator, query: str, premise: Premise) -> dict[str, Any]:
    t0 = time.perf_counter_ns()
    answer = engine.generate_verified(query, premise)
    return from_trace(answer, time.perf_counter_ns() - t0)


# ---------------------------------------------------------------------- helpers


def _attempt(text: str, reply: Reply, rejected: Sequence[SentenceVerdict]) -> dict[str, Any]:
    return {
        "text": text,
        "tokens_out": reply.tokens_out,
        "latency_ns": reply.latency_ns,
        "usage": reply.usage,
        "rejected": [
            {"sentence": v.text, "reasons": [r.value for r in v.reasons]} for v in rejected
        ],
    }


def _continue(base: Messages, committed: str, note: str) -> Messages:
    if not committed:
        if not note:
            return list(base)
        return [base[0], {"role": "user", "content": f"{base[1]['content']}\n\n{note.strip()}"}]
    return [
        *base,
        {"role": "assistant", "content": committed},
        {"role": "user", "content": CONTINUE + note},
    ]


def _strip_repeat(text: str, committed: str) -> str:
    """Drop the prefix if the model restated it instead of continuing."""
    head = committed.strip()
    body = text.strip()
    if head and body.startswith(head):
        return body[len(head) :]
    return text


def _join(committed: str, text: str) -> str:
    text = text.strip()
    if not committed:
        return text
    return f"{committed} {text}" if text else committed


def _token_share(tokens: int, text: str, kept: int) -> int:
    """Tokens of the discarded part, pro rata by characters (a closed API returns no offsets)."""
    return round(tokens * (len(text) - kept) / len(text)) if text else 0
