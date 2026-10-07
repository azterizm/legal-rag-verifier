"""In-flight generation: request-per-sentence, verified sentence by sentence, with rollback.

The controller owns every decision (segmentation, verification, steering, rollback caps, trace); a
backend implements only :meth:`Backend.extend` plus its tokenizer (plan decision 8). Each call
decodes from the committed prefix up to a candidate boundary and returns; the segmenter confirms
the boundary (a false stop just extends the same sentence, a prefix-cache hit), the verifier
checks the sentence, and it is either committed or rolled back. A rolled-back sentence is never
appended: the next call resubmits the committed prefix, which the backend still holds (HF: a
``DynamicCache`` truncated to it; SGLang: RadixAttention).

Steering after a rollback is at decode level (``allow``, ``ban``) or, with ``steering="inject"``,
in the context:

* **allow**: when the claim check rejects a figure, citation, instrument or modal and the premise
  has same-type values (:class:`~legal_rag_verifier.verifier.Repair`), decoding resumes at the
  token where the claim starts and the claim span is constrained to those values (token sequences
  from the backend's tokenizer). The rejected value is excluded by construction.
* **ban**: otherwise, the sentence restarts with its rejected first token banned at that position.
  Bans accumulate per position.
* **inject** (added 2026-10-07 on your go; it reverses plan decision 6 for this mode only): the
  premise windows the verifier aligned the rejected sentence to are written into the context at the
  rollback point (``inject_template``), and the sentence is regenerated from its start with no
  constraint. The source stays in the context, where the backend caches it like any other prefix,
  but never in the answer text; the trace records which windows went in and how many tokens. A
  window is injected at most once per answer; a retry with no new window to inject falls back to a
  ban.

Each point is retried at most ``max_rollbacks`` times (default 3). A retry uses the allow-list when
the rejected draft has a same-type repair, otherwise a ban; so a failed allow retry is followed by a
ban retry when the frame itself is wrong (a figure forced in where its qualifier is missing). When
the last retry also fails, the engine commits a fixed refusal sentence and moves on; past
``max_total_rollbacks`` discarded drafts in one answer it ends the answer with the refusal.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from legal_rag_verifier.premise import PassageKind, Premise
from legal_rag_verifier.segmenter import BOUNDARY_STOPS, find_boundary
from legal_rag_verifier.verifier import SentenceVerdict, Verifier

__all__ = [
    "DEFAULT_REFUSAL",
    "INJECT_TEMPLATE",
    "SYSTEM_PROMPT",
    "Allow",
    "Answer",
    "Backend",
    "Ban",
    "Constraint",
    "InFlightGenerator",
    "Segment",
    "Tokens",
    "render_premise",
]

Tokens = tuple[int, ...]
FinishReason = Literal["stop", "length", "eos"]

DEFAULT_REFUSAL = "I cannot state this point reliably from the provisions provided."
#: How ``steering="inject"`` writes the aligned windows into the context, as plain text in the
#: answer stream. A backend-specific template (a chat turn, with its special tokens) also works.
INJECT_TEMPLATE = "\n\n(Source: {source})\n\n"
SYSTEM_PROMPT = (
    "You answer questions about legislation using only the provisions below. State figures, "
    "dates, section numbers and the names of Acts exactly as the provisions give them. If the "
    "provisions do not answer the question, say so. Answer in a few plain sentences, without "
    "headings or lists.\n\nProvisions:\n{premise}"
)


@dataclass(frozen=True, slots=True)
class Ban:
    """Token ids banned at the first decoded step only."""

    token_ids: frozenset[int]

    def banned(self, step: int) -> frozenset[int]:
        return self.token_ids if step == 0 else frozenset()

    def to_dict(self) -> dict[str, Any]:
        return {"ban": sorted(self.token_ids)}


@dataclass(frozen=True, slots=True)
class Allow:
    """Decoding must follow one of ``sequences``; the constraint lifts once one is complete.

    Stop strings are not honoured while the span is open (a candidate such as "£1.5 million"
    contains one).
    """

    sequences: tuple[Tokens, ...]

    def next_tokens(self, generated: Sequence[int]) -> frozenset[int] | None:
        """Tokens allowed after ``generated``; ``None`` once the span has closed."""
        step = len(generated)
        prefix = tuple(generated)
        live = [s for s in self.sequences if s[:step] == prefix]
        if not live or any(len(s) == step for s in live):
            return None
        return frozenset(s[step] for s in live)

    def to_dict(self) -> dict[str, Any]:
        return {"allow": [list(s) for s in self.sequences]}


Constraint = Ban | Allow


@dataclass(frozen=True, slots=True)
class Segment:
    """One decode call: the new tokens (no EOS), their text and why decoding stopped."""

    tokens: Tokens
    text: str
    finish_reason: FinishReason
    prefix_cache_hit_tokens: int
    latency_ns: int


class Backend(Protocol):
    """A generator the engine can drive. Greedy decoding; all policy lives in the engine."""

    name: str
    model_id: str

    def chat(self, messages: Sequence[Mapping[str, str]]) -> Tokens:
        """The prompt tokens for ``messages``, ready for the assistant turn."""
        ...

    def encode(self, text: str) -> Tokens:
        """Tokens of ``text`` without special tokens."""
        ...

    def decode(self, tokens: Sequence[int]) -> str: ...

    def extend(
        self,
        committed: Sequence[int],
        *,
        stop: Sequence[str],
        max_new: int,
        constraint: Constraint | None,
    ) -> Segment:
        """Decode after ``committed`` until a stop string, EOS or ``max_new`` tokens.

        ``prefix_cache_hit_tokens`` is how much of ``committed`` was reused, not recomputed.
        """
        ...


@dataclass(frozen=True)
class Answer:
    """The committed answer text and its per-sentence verification trace."""

    text: str
    trace: dict[str, Any]

    def trace_json(self) -> str:
        """Canonical JSON (sorted keys, no whitespace)."""
        return json.dumps(self.trace, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def render_premise(premise: Premise) -> str:
    """The premise as prompt text: each window under its heading, facts last."""
    ordered = sorted(premise.passages, key=lambda p: p.kind is PassageKind.FACT)
    return "\n\n".join(f"[{p.heading}]\n{p.text}" if p.heading else p.text for p in ordered)


@dataclass
class _Draft:
    """A sentence decoded from one point: its tokens, any lookahead past it, and call stats."""

    tokens: list[int]
    lookahead: list[int]
    end: FinishReason | None  # set once the stream has ended (EOS or token budget)
    calls: int = 0
    hit_tokens: int = 0
    latency_ns: int = 0


@dataclass
class _Stream:
    """The answer, and what the model sees after the prompt: the answer plus injected sources."""

    answer: list[int] = field(default_factory=list)
    context: list[int] = field(default_factory=list)
    injected: set[int] = field(default_factory=set)  # windows already written into the context

    def commit(self, tokens: Sequence[int]) -> None:
        self.answer += tokens
        self.context += tokens


@dataclass
class _Retry:
    """Where a rolled-back point resumes: a kept seed, a constraint, or a source written first."""

    seed: list[int]
    constraint: Constraint | None
    steering: str | None
    note: list[int] = field(default_factory=list)
    injection: dict[str, Any] | None = None


@dataclass
class _Point:
    """Every attempt at one sentence position, for the trace."""

    start: int
    attempts: list[dict[str, Any]] = field(default_factory=list)
    bans: dict[int, set[int]] = field(default_factory=dict)
    rollbacks: int = 0  # discarded drafts; all but a refused point's last one were retried
    injected: bool = False  # a source was written into the context for this point


class InFlightGenerator:
    """Generate an answer whose every sentence passed the verifier, or was refused."""

    def __init__(
        self,
        backend: Backend,
        verifier: Verifier,
        *,
        max_rollbacks: int = 3,
        max_total_rollbacks: int = 8,
        steering: Literal["allow", "ban", "inject"] = "allow",
        refusal: str = DEFAULT_REFUSAL,
        max_new_tokens: int = 512,
        max_sentence_tokens: int = 160,
        system_prompt: str = SYSTEM_PROMPT,
        inject_template: str = INJECT_TEMPLATE,
        inject_windows: int = 2,
        inject_max_tokens: int = 800,
    ) -> None:
        self.backend = backend
        self.verifier = verifier
        self.max_rollbacks = max_rollbacks
        self.max_total_rollbacks = max_total_rollbacks
        self.steering = steering
        self.refusal = refusal
        self.max_new_tokens = max_new_tokens
        self.max_sentence_tokens = max_sentence_tokens
        self.system_prompt = system_prompt
        self.inject_template = inject_template
        self.inject_windows = inject_windows
        self.inject_max_tokens = inject_max_tokens

    # ------------------------------------------------------------------ public API
    def messages(self, query: str, premise: Premise) -> list[dict[str, str]]:
        """The chat the generator sees: the premise in the system turn, then the query."""
        system = self.system_prompt.format(premise=render_premise(premise))
        return [{"role": "system", "content": system}, {"role": "user", "content": query}]

    def generate_verified(self, query: str, premise: Premise) -> Answer:
        t0 = time.perf_counter_ns()
        prompt = self.backend.chat(self.messages(query, premise))
        stream = _Stream()
        carry: _Draft | None = None  # lookahead decoded past the last committed sentence
        points: list[dict[str, Any]] = []
        total_rollbacks = 0
        stop_reason: str | None = None
        while stop_reason is None:
            point = _Point(len(stream.answer))
            retry = _Retry(carry.lookahead if carry else [], None, None)
            end = carry.end if carry else None
            carry = None
            while True:
                draft = self._draft(prompt, stream, retry.seed, end, retry.constraint)
                sentence = self.backend.decode(draft.tokens).strip()
                if not sentence and point.rollbacks:  # the retry gave nothing: say so
                    stream.commit(self._refusal(stream.answer))
                    points.append(self._close(point, "refused", self.refusal))
                    break
                if not sentence:  # whitespace between sentences, or nothing at all
                    stream.commit(draft.tokens)
                    carry = draft
                    break
                verdict = self.verifier.check_sentence(premise, sentence, query=query)
                attempt = self._attempt(draft, verdict, retry)
                point.attempts.append(attempt)
                if verdict.emitted:
                    if point.injected:  # decoded after the source, not after the answer's text
                        stream.answer += self._separator(stream.answer, draft.tokens)
                    stream.commit(draft.tokens)
                    carry = draft
                    points.append(self._close(point, "emitted", sentence))
                    break
                point.rollbacks += 1
                total_rollbacks += 1
                if self._refuses(point, total_rollbacks):
                    attempt["tokens_discarded"] = len(draft.tokens) + len(draft.lookahead)
                    stream.commit(self._refusal(stream.answer))
                    points.append(self._close(point, "refused", self.refusal))
                    if total_rollbacks > self.max_total_rollbacks:
                        stop_reason = "rollback_budget"
                    break
                retry = self._steer(point, draft.tokens, verdict, premise, stream)
                end = None
                kept = len(retry.seed)
                attempt["tokens_discarded"] = len(draft.tokens) + len(draft.lookahead) - kept
            if stop_reason is None and carry is not None and carry.end and not carry.lookahead:
                stop_reason = carry.end
            if stop_reason is None and len(stream.answer) >= self.max_new_tokens:
                stop_reason = "length"
        return Answer(
            self.backend.decode(stream.answer).strip(),
            self._trace(prompt, stream.answer, points, stop_reason, time.perf_counter_ns() - t0),
        )

    # ------------------------------------------------------------------ decoding
    def _draft(
        self,
        prompt: Tokens,
        stream: _Stream,
        seed: Sequence[int],
        end: FinishReason | None,
        constraint: Constraint | None,
    ) -> _Draft:
        """Decode from the context + ``seed`` until the segmenter confirms a sentence boundary.

        The token budget counts the answer only, not injected sources."""
        draft = _Draft(list(seed), [], end)
        while True:
            text = self.backend.decode(draft.tokens)
            lead = len(text) - len(text.lstrip())
            final = draft.end is not None
            cut = find_boundary(text, lead, final=final) if text.strip() else None
            if cut is not None:
                k = _token_cut(self.backend, draft.tokens, cut)
                draft.tokens, draft.lookahead = draft.tokens[:k], draft.tokens[k:]
                return draft
            if final:
                return draft
            budget = min(
                self.max_sentence_tokens - len(draft.tokens),
                self.max_new_tokens - len(stream.answer) - len(draft.tokens),
            )
            if budget <= 0:
                draft.end = "length"
                continue
            # A trailing "." is undecided until the next token: peek one, not a whole sentence.
            peek = text.rstrip(" \t").endswith(".")
            segment = self.backend.extend(
                (*prompt, *stream.context, *draft.tokens),
                stop=BOUNDARY_STOPS,
                max_new=1 if peek else budget,
                constraint=constraint,
            )
            constraint = None  # a constraint applies from the resume position only
            draft.calls += 1
            draft.hit_tokens += segment.prefix_cache_hit_tokens
            draft.latency_ns += segment.latency_ns
            draft.tokens += segment.tokens
            if segment.finish_reason == "eos":
                draft.end = "eos"
            elif not segment.tokens:
                draft.end = "length"  # a backend that cannot decode further

    # ------------------------------------------------------------------ steering
    def _refuses(self, point: _Point, total_rollbacks: int) -> bool:
        """Refuse once the point's retries, or the answer's rollback budget, are spent."""
        return point.rollbacks > self.max_rollbacks or total_rollbacks > self.max_total_rollbacks

    def _steer(
        self,
        point: _Point,
        tokens: Sequence[int],
        verdict: SentenceVerdict,
        premise: Premise,
        stream: _Stream,
    ) -> _Retry:
        """Where to resume after a rollback, and under which constraint (or after which source).

        An injected source is written into ``stream.context`` here."""
        repair = verdict.repair
        if self.steering == "inject":
            note, windows = self._source(premise, verdict.aligned, stream.injected)
            if note:
                stream.injected.update(windows)
                stream.context += note
                point.injected = True
                return _Retry([], None, "inject", note, {"windows": windows, "tokens": len(note)})
        if self.steering == "allow" and repair is not None and repair.mode == "allow":
            allowed = self._allow(tokens, repair.offset, repair.candidates, repair.rejected)
            if allowed is not None:
                keep, sequences = allowed
                return _Retry(list(tokens[:keep]), Allow(sequences), "allow")
        # Ban: restart at the sentence's first non-space token with that token banned there.
        first = next((i for i, t in enumerate(tokens) if self.backend.decode([t]).strip()), 0)
        banned = point.bans.setdefault(first, set())
        banned.add(tokens[first])
        return _Retry(list(tokens[:first]), Ban(frozenset(banned)), "ban")

    def _allow(
        self,
        tokens: Sequence[int],
        offset: int,
        candidates: Sequence[str],
        rejected: str,
    ) -> tuple[int, tuple[Tokens, ...]] | None:
        """Kept token prefix and candidate token sequences for a claim starting at ``offset``."""
        text = self.backend.decode(tokens)
        start = len(text) - len(text.lstrip()) + offset  # verdict offsets are on the stripped text
        keep = _token_floor(self.backend, tokens, start)
        kept = self.backend.decode(tokens[:keep])
        gap = text[len(kept) : start]
        base = self.backend.encode(kept)
        sequences: list[Tokens] = []
        for candidate in candidates:
            if candidate == rejected:
                continue
            joint = self.backend.encode(kept + gap + candidate)
            suffix = joint[len(base) :] if joint[: len(base)] == base else None
            seq = suffix or self.backend.encode(gap + candidate)
            if seq and seq not in sequences:
                sequences.append(seq)
        return (keep, tuple(sequences)) if sequences else None

    def _source(
        self, premise: Premise, aligned: Sequence[int], injected: set[int]
    ) -> tuple[list[int], list[int]]:
        """Context tokens that write the aligned windows not yet injected, and their positions."""
        source, windows = self._source_text(premise, aligned, injected)
        if not windows:
            return [], []
        return list(self.backend.encode(self.inject_template.format(source=source))), windows

    def _source_text(
        self, premise: Premise, aligned: Sequence[int], injected: set[int]
    ) -> tuple[str, list[int]]:
        """The aligned windows not yet injected, each rendered as in the prompt, cut at
        ``inject_max_tokens``; and their positions."""
        windows = [i for i in aligned if i not in injected][: self.inject_windows]
        if not windows:
            return "", []
        passages = [premise.passages[i] for i in windows]
        source = "\n\n".join(f"[{p.heading}]\n{p.text}" if p.heading else p.text for p in passages)
        tokens = self.backend.encode(source)
        if len(tokens) > self.inject_max_tokens:
            source = self.backend.decode(tokens[: self.inject_max_tokens]).rstrip() + " …"
        return source, windows

    def _separator(self, answer: Sequence[int], tokens: Sequence[int]) -> list[int]:
        """A space between the answer and a sentence decoded after an injected source, if needed."""
        text, sentence = self.backend.decode(answer), self.backend.decode(tokens)
        if text.strip() and not text[-1:].isspace() and not sentence[:1].isspace():
            return list(self.backend.encode(" "))
        return []

    def _refusal(self, answer: Sequence[int]) -> list[int]:
        text = self.backend.decode(answer)
        sep = " " if text.strip() and not text[-1:].isspace() else ""
        return list(self.backend.encode(sep + self.refusal))

    # ------------------------------------------------------------------ trace
    @staticmethod
    def _attempt(
        draft: _Draft,
        verdict: SentenceVerdict,
        retry: _Retry,
    ) -> dict[str, Any]:
        return {
            "verdict": verdict.to_dict(),
            "steering": retry.steering,
            "constraint": retry.constraint.to_dict() if retry.constraint else None,
            "injected": retry.injection,
            "tokens": len(draft.tokens),
            "tokens_reused": len(retry.seed),
            "tokens_discarded": 0,
            "decode_calls": draft.calls,
            "prefix_cache_hit_tokens": draft.hit_tokens,
            "decode_latency_ns": draft.latency_ns,
        }

    @staticmethod
    def _close(point: _Point, outcome: str, text: str) -> dict[str, Any]:
        emitted = point.attempts[-1]["steering"] if outcome == "emitted" else None
        return {
            "text": text,
            "outcome": outcome,
            "rollbacks": point.rollbacks,
            "recovered_by": emitted if point.rollbacks else None,
            "attempts": point.attempts,
        }

    def _trace(
        self,
        prompt: Tokens,
        answer: Sequence[int],
        points: list[dict[str, Any]],
        stop_reason: str | None,
        elapsed_ns: int,
    ) -> dict[str, Any]:
        attempts = [a for p in points for a in p["attempts"]]
        nli = self.verifier.nli
        return {
            "backend": self.backend.name,
            "model": self.backend.model_id,
            "verifier": {
                "config": self.verifier.config.to_dict(),
                "nli": nli.model_id if nli is not None else None,
            },
            "engine": {
                "max_rollbacks": self.max_rollbacks,
                "max_total_rollbacks": self.max_total_rollbacks,
                "steering": self.steering,
                "refusal": self.refusal,
                "max_new_tokens": self.max_new_tokens,
                "inject_template": self.inject_template if self.steering == "inject" else None,
                "inject_windows": self.inject_windows,
                "inject_max_tokens": self.inject_max_tokens,
            },
            "prompt_tokens": len(prompt),
            "answer_tokens": len(answer),
            "sentences": points,
            "totals": {
                "sentences": len(points),
                "refused": sum(p["outcome"] == "refused" for p in points),
                "rollbacks": sum(p["rollbacks"] for p in points),
                "recovered_by_allow": sum(p["recovered_by"] == "allow" for p in points),
                "recovered_by_ban": sum(p["recovered_by"] == "ban" for p in points),
                "recovered_by_inject": sum(p["recovered_by"] == "inject" for p in points),
                "injections": sum(a["injected"] is not None for a in attempts),
                "tokens_injected": sum(a["injected"]["tokens"] for a in attempts if a["injected"]),
                "tokens_discarded": sum(a["tokens_discarded"] for a in attempts),
                "decode_calls": sum(a["decode_calls"] for a in attempts),
                "prefix_cache_hit_tokens": sum(a["prefix_cache_hit_tokens"] for a in attempts),
                "claim_latency_ns": sum(a["verdict"]["claim_latency_ns"] for a in attempts),
                "nli_latency_ns": sum(a["verdict"]["nli_latency_ns"] for a in attempts),
                "decode_latency_ns": sum(a["decode_latency_ns"] for a in attempts),
                "elapsed_ns": elapsed_ns,
            },
            "stop_reason": stop_reason,
        }


def _token_cut(backend: Backend, tokens: Sequence[int], end: int) -> int:
    """Fewest leading tokens whose text reaches character ``end``."""
    for k in range(1, len(tokens) + 1):
        if len(backend.decode(tokens[:k])) >= end:
            return k
    return len(tokens)


def _token_floor(backend: Backend, tokens: Sequence[int], start: int) -> int:
    """Most leading tokens whose text ends at or before character ``start``."""
    keep = 0
    for k in range(1, len(tokens) + 1):
        if len(backend.decode(tokens[:k])) > start:
            break
        keep = k
    return keep
