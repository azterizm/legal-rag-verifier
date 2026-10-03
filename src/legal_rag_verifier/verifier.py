"""The shared detector: a deterministic claim check, then (when configured) the NLI head.

``Verifier.check_text(premise, text)`` is the post-hoc API used by grid cells 4A/4D; the in-flight
engine calls :meth:`Verifier.check_sentence` on each sentence as it closes (plan R5). Both return
the same :class:`SentenceVerdict`.

Order of checks for one sentence:

1. **Grounding** (whole premise, declared metadata and the query): every figure, citation and
   instrument title must be found. A miss is a rollback without running NLI.
2. **Alignment**: the sentence is aligned to its top-k premise windows (lexical, or the NLI head's
   best-entailed windows), plus windows those windows cite ("subsection (1ZA)").
3. **Window checks** (plan R2, R3): a figure taken from outside the aligned windows while they state
   a different value of the same kind is a value swap; a figure stated without the qualifier its
   source binds it with is a dropped qualifier; a modal whose class the aligned windows do not
   use is a deontic shift.
4. **NLI** over premise windows (SummaC-ZS style), when an NLI scorer is configured.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal, Protocol

from legal_rag_verifier.align import rank_windows
from legal_rag_verifier.citations import is_relative, render_citation
from legal_rag_verifier.claims import FIGURE_KINDS, Claim, ClaimKind, extract_claims
from legal_rag_verifier.deontic import MODAL_SURFACES, Deontic, DeonticMatch, find_deontics
from legal_rag_verifier.index import PremiseIndex, WindowIndex, build_index, numeric_part
from legal_rag_verifier.premise import PassageKind, Premise
from legal_rag_verifier.qualifiers import find_bound_qualifier, sentence_qualifiers
from legal_rag_verifier.segmenter import split_sentences

__all__ = [
    "ClaimResult",
    "GroundedBy",
    "NLIProbs",
    "NLIResult",
    "NLIScorer",
    "Reason",
    "Repair",
    "SentenceVerdict",
    "Verdict",
    "Verifier",
    "VerifierConfig",
]


class Verdict(StrEnum):
    EMIT = "EMIT"
    ROLLBACK = "ROLLBACK"


class Reason(StrEnum):
    GROUNDED = "GROUNDED"
    CONNECTIVE = "CONNECTIVE"
    UNGROUNDED_FIGURE = "UNGROUNDED_FIGURE"
    UNGROUNDED_CITATION = "UNGROUNDED_CITATION"
    UNGROUNDED_INSTRUMENT = "UNGROUNDED_INSTRUMENT"
    FIGURE_MISALIGNED = "FIGURE_MISALIGNED"
    QUALIFIER_DROPPED = "QUALIFIER_DROPPED"
    DEONTIC_SHIFT = "DEONTIC_SHIFT"
    NLI_CONTRADICTION = "NLI_CONTRADICTION"
    NLI_NOT_ENTAILED = "NLI_NOT_ENTAILED"
    NEUTRAL_STRICT = "NEUTRAL_STRICT"


_PASS = frozenset({Reason.GROUNDED, Reason.CONNECTIVE})
_QUALIFIED_KINDS = FIGURE_KINDS - {ClaimKind.DATE}


class GroundedBy(StrEnum):
    WINDOW = "window"  # in an aligned window
    PREMISE = "premise"  # elsewhere in the premise text
    FACT = "fact"  # in a linearised temporal fact
    METADATA = "metadata"  # a declared citation or instrument title
    QUERY = "query"  # stated by the user (plan R4)


@dataclass(frozen=True, slots=True)
class ClaimResult:
    claim: Claim
    grounded_by: GroundedBy | None
    reason: Reason | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.claim.kind.value,
            "value": self.claim.value,
            "text": self.claim.text,
            "span": [self.claim.start, self.claim.end],
            "grounded_by": self.grounded_by.value if self.grounded_by else None,
            "reason": self.reason.value if self.reason else None,
        }


@dataclass(frozen=True, slots=True)
class Repair:
    """How to regenerate a rejected sentence.

    ``allow``: keep the sentence up to ``offset`` (characters), then constrain the next span to one
    of ``candidates`` (grounded values of the same type), excluding the rejected value by
    construction. ``ban``: restart the sentence and ban its first token for that step.
    """

    mode: Literal["allow", "ban"]
    offset: int
    candidates: tuple[str, ...] = ()
    rejected: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "offset": self.offset,
            "candidates": list(self.candidates),
            "rejected": self.rejected,
        }


@dataclass(frozen=True, slots=True)
class NLIProbs:
    entailment: float
    neutral: float
    contradiction: float


class NLIScorer(Protocol):
    """A batched NLI head: one ``[premise, hypothesis]`` pair per premise, one forward pass."""

    model_id: str

    def score(self, premises: Sequence[str], hypothesis: str) -> list[NLIProbs]: ...


@dataclass(frozen=True, slots=True)
class NLIResult:
    entailment: float
    contradiction: float
    neutral: float
    window: int
    latency_ns: int
    model_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "entailment": round(self.entailment, 6),
            "contradiction": round(self.contradiction, 6),
            "neutral": round(self.neutral, 6),
            "window": self.window,
            "latency_ns": self.latency_ns,
            "model_id": self.model_id,
        }


@dataclass(frozen=True)
class VerifierConfig:
    """Thresholds and policies, recorded in every trace (plan §5, R7)."""

    entail_threshold: float = 0.70
    contradict_threshold: float = 0.40
    neutral_policy: Literal["connective", "strict"] = "connective"
    top_k: int = 2
    #: A window below the top one is aligned only if it scores at least this share of the best.
    align_ratio: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return {
            "entail_threshold": self.entail_threshold,
            "contradict_threshold": self.contradict_threshold,
            "neutral_policy": self.neutral_policy,
            "top_k": self.top_k,
            "align_ratio": self.align_ratio,
        }


@dataclass(frozen=True)
class SentenceVerdict:
    text: str
    start: int
    end: int
    verdict: Verdict
    reasons: tuple[Reason, ...]
    claims: tuple[ClaimResult, ...] = ()
    deontics: tuple[str, ...] = ()
    aligned: tuple[int, ...] = ()
    nli: NLIResult | None = None
    repair: Repair | None = None
    claim_latency_ns: int = 0
    nli_latency_ns: int = 0
    details: tuple[str, ...] = field(default=())

    @property
    def emitted(self) -> bool:
        return self.verdict is Verdict.EMIT

    @property
    def ungrounded(self) -> list[str]:
        return [r.claim.text for r in self.claims if r.reason is not None]

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "span": [self.start, self.end],
            "verdict": self.verdict.value,
            "reasons": [r.value for r in self.reasons],
            "claims": [c.to_dict() for c in self.claims],
            "deontics": list(self.deontics),
            "aligned_windows": list(self.aligned),
            "nli": self.nli.to_dict() if self.nli else None,
            "repair": self.repair.to_dict() if self.repair else None,
            "claim_latency_ns": self.claim_latency_ns,
            "nli_latency_ns": self.nli_latency_ns,
            "details": list(self.details),
        }


class Verifier:
    """Sentence verifier. Without an NLI scorer it runs the deterministic claim check only."""

    def __init__(self, nli: NLIScorer | None = None, config: VerifierConfig | None = None) -> None:
        self.nli = nli
        self.config = config or VerifierConfig()

    # ------------------------------------------------------------------ public API
    def check_text(
        self, premise: Premise, text: str, *, query: str | None = None
    ) -> list[SentenceVerdict]:
        """Split ``text`` into sentences and verify each one (the post-hoc path)."""
        out = []
        for sentence in split_sentences(text):
            verdict = self.check_sentence(premise, sentence.text, query=query)
            out.append(_shift(verdict, sentence.start))
        return out

    def check_sentence(
        self, premise: Premise, sentence: str, *, query: str | None = None
    ) -> SentenceVerdict:
        t0 = time.perf_counter_ns()
        index = build_index(premise)
        claims = extract_claims(sentence)
        deontics = find_deontics(sentence)
        query_claims = extract_claims(query) if query else []

        results = [self._ground(c, index, query_claims) for c in claims]
        failed = [r for r in results if r.reason is not None]
        if failed:
            first = min(failed, key=lambda r: r.claim.start)
            aligned = self._aligned_lexical(index, sentence)
            return SentenceVerdict(
                sentence,
                0,
                len(sentence),
                Verdict.ROLLBACK,
                _unique(r.reason for r in failed if r.reason),
                tuple(results),
                tuple(d.deontic.value for d in deontics),
                aligned,
                repair=self._repair_claim(first, index, aligned, sentence),
                claim_latency_ns=time.perf_counter_ns() - t0,
            )

        nli_result: NLIResult | None = None
        if self.nli is not None:
            nli_result, ranked = _run_nli(self.nli, index, sentence)
            aligned = self._expand(index, self._top(ranked))
        else:
            aligned = self._aligned_lexical(index, sentence)
        claim_ns = time.perf_counter_ns() - t0 - (nli_result.latency_ns if nli_result else 0)

        aligned_windows = [index.windows[i] for i in aligned]
        results = [_refine(r, aligned_windows) for r in results]
        found = self._window_checks(results, index, aligned, deontics, sentence)
        has_claims = bool(claims) or bool(deontics)
        if not found.reasons and nli_result is not None:
            nli_reason = self._nli_reason(nli_result, has_claims=has_claims)
            if nli_reason is not None:
                found.reasons.append(nli_reason)
                found.repair = Repair("ban", 0)

        reasons = found.reasons or [Reason.GROUNDED if has_claims else Reason.CONNECTIVE]
        verdict = Verdict.EMIT if set(reasons) <= _PASS else Verdict.ROLLBACK
        return SentenceVerdict(
            sentence,
            0,
            len(sentence),
            verdict,
            tuple(reasons),
            tuple(found.results),
            tuple(d.deontic.value for d in deontics),
            aligned,
            nli_result,
            found.repair if verdict is Verdict.ROLLBACK else None,
            claim_ns,
            nli_result.latency_ns if nli_result else 0,
            tuple(found.details),
        )

    def _window_checks(
        self,
        results: list[ClaimResult],
        index: PremiseIndex,
        aligned: tuple[int, ...],
        deontics: list[DeonticMatch],
        sentence: str,
    ) -> _Findings:
        """Value swap, dropped qualifier and deontic shift against the aligned windows."""
        windows = [index.windows[i] for i in aligned]
        found = _Findings(results)
        swapped = [r for r in results if _misaligned(r, windows)]
        if swapped:
            found.reasons.append(Reason.FIGURE_MISALIGNED)
            found.results = [
                ClaimResult(r.claim, r.grounded_by, Reason.FIGURE_MISALIGNED) if r in swapped else r
                for r in results
            ]
            found.repair = self._repair_claim(_first(found.results), index, aligned, sentence)

        dropped = _dropped_qualifiers(results, index, sentence)
        if dropped:
            found.reasons.append(Reason.QUALIFIER_DROPPED)
            found.details += dropped
            found.repair = found.repair or Repair("ban", 0)

        window_deontics = frozenset[Deontic]().union(*(w.deontics for w in windows))
        shifted = [d for d in deontics if window_deontics and d.deontic not in window_deontics]
        if shifted:
            found.reasons.append(Reason.DEONTIC_SHIFT)
            found.details.append(
                f"sentence {shifted[0].deontic.value} ({shifted[0].text!r}) vs window "
                + "/".join(sorted(d.value for d in window_deontics))
            )
            found.repair = found.repair or Repair(
                "allow",
                shifted[0].start,
                tuple(s for d in sorted(window_deontics) for s in MODAL_SURFACES[d]),
                shifted[0].text,
            )
        return found

    def _nli_reason(self, nli: NLIResult, *, has_claims: bool) -> Reason | None:
        if nli.contradiction > self.config.contradict_threshold:
            return Reason.NLI_CONTRADICTION
        if nli.entailment > self.config.entail_threshold:
            return None
        if has_claims:
            return Reason.NLI_NOT_ENTAILED
        return Reason.NEUTRAL_STRICT if self.config.neutral_policy == "strict" else None

    # ------------------------------------------------------------------ grounding
    def _ground(self, claim: Claim, index: PremiseIndex, query_claims: list[Claim]) -> ClaimResult:
        by = _grounded_in_premise(claim, index)
        if by is None and _in_query(claim, query_claims):
            by = GroundedBy.QUERY
        if by is not None:
            return ClaimResult(claim, by)
        reason = {
            ClaimKind.CITATION: Reason.UNGROUNDED_CITATION,
            ClaimKind.INSTRUMENT: Reason.UNGROUNDED_INSTRUMENT,
        }.get(claim.kind, Reason.UNGROUNDED_FIGURE)
        return ClaimResult(claim, None, reason)

    # ------------------------------------------------------------------ alignment
    def _aligned_lexical(self, index: PremiseIndex, sentence: str) -> tuple[int, ...]:
        if not index.windows:
            return ()
        ranked = rank_windows(sentence, [w.text for w in index.windows])
        return self._expand(index, self._top(ranked))

    def _top(self, ranked: Sequence[tuple[int, float]]) -> list[int]:
        """The top-k windows, dropping any that score below ``align_ratio`` of the best."""
        best = ranked[0][1]
        return [
            i
            for rank, (i, score) in enumerate(ranked[: self.config.top_k])
            if rank == 0 or score >= self.config.align_ratio * best
        ]

    def _expand(self, index: PremiseIndex, top: Sequence[int]) -> tuple[int, ...]:
        """Add windows that the aligned windows cite (one hop): "subsection (1ZA)" → (1ZA)."""
        out = list(top)
        for i in top:
            for cite in index.windows[i].citations:
                for w in index.windows:
                    if (
                        w.position not in out
                        and w.tail
                        and (w.tail == cite or w.tail.startswith(cite + "/"))
                    ):
                        out.append(w.position)
        return tuple(out)

    # ------------------------------------------------------------------ repair
    def _repair_claim(
        self, result: ClaimResult, index: PremiseIndex, aligned: Sequence[int], sentence: str
    ) -> Repair:
        claim = result.claim
        windows = [index.windows[i] for i in aligned]
        candidates: list[str] = []
        if claim.kind in FIGURE_KINDS:
            seen: set[str] = set()
            for w in windows:
                for c in w.values(claim.kind):
                    if c.value != claim.value and c.value not in seen:
                        seen.add(c.value)
                        candidates.append(c.text)
        elif claim.kind is ClaimKind.CITATION:
            style = "s." if claim.text.lower().startswith("s.") else "section"
            for w in windows:
                if w.tail:
                    rendered = render_citation(w.tail, style=style)
                    if rendered not in candidates and w.tail != claim.value:
                        candidates.append(rendered)
            if not claim.text.lower().startswith(("s", "section")):
                candidates = []
        elif claim.kind is ClaimKind.INSTRUMENT:
            candidates = [t for t in index.declared_titles if t.lower() not in claim.text.lower()]
        if candidates:
            return Repair(
                "allow", claim.start, tuple(candidates), sentence[claim.start : claim.end]
            )
        return Repair("ban", 0, (), sentence[claim.start : claim.end])


# ---------------------------------------------------------------------- helpers


@dataclass
class _Findings:
    results: list[ClaimResult]
    reasons: list[Reason] = field(default_factory=list)
    details: list[str] = field(default_factory=list)
    repair: Repair | None = None


def _run_nli(
    scorer: NLIScorer, index: PremiseIndex, sentence: str
) -> tuple[NLIResult, list[tuple[int, float]]]:
    """Score every window in one batch; rank windows by entailment (SummaC-ZS style)."""
    t0 = time.perf_counter_ns()
    probs = scorer.score([w.text for w in index.windows], sentence)
    elapsed = time.perf_counter_ns() - t0
    ranked = sorted(range(len(probs)), key=lambda i: (-probs[i].entailment, i))
    best = ranked[0]
    contradiction = max(p.contradiction for p in probs)
    result = NLIResult(
        probs[best].entailment, contradiction, probs[best].neutral, best, elapsed, scorer.model_id
    )
    return result, [(i, probs[i].entailment) for i in ranked]


def _misaligned(result: ClaimResult, aligned: list[WindowIndex]) -> bool:
    """A figure from outside the aligned windows while they state a rival value (plan R3)."""
    claim = result.claim
    if claim.kind not in FIGURE_KINDS or result.grounded_by in {
        GroundedBy.WINDOW,
        GroundedBy.QUERY,
    }:
        return False
    rivals = {c.value for w in aligned for c in w.values(claim.kind)}
    return bool(rivals) and claim.value not in rivals


def _dropped_qualifiers(
    results: list[ClaimResult], index: PremiseIndex, sentence: str
) -> list[str]:
    """Figures whose every source occurrence is bound by a qualifier the sentence drops (R2)."""
    expressed = sentence_qualifiers(sentence)
    out: list[str] = []
    for result in results:
        claim = result.claim
        if claim.kind not in _QUALIFIED_KINDS or result.grounded_by is GroundedBy.QUERY:
            continue
        bindings = [
            find_bound_qualifier(window.text, source.start, source.end)
            for window in index.windows
            if window.kind is not PassageKind.FACT
            for source in window.values(claim.kind)
            if source.value == claim.value
        ]
        bound = bindings[0] if bindings and all(bindings) else None
        if bound is not None and bound.qualifier not in expressed:
            out.append(f"{claim.text!r} is bound by {bound.text!r} ({bound.qualifier.value})")
    return out


def _grounded_in_premise(claim: Claim, index: PremiseIndex) -> GroundedBy | None:
    kind, value = claim.kind, claim.value
    if kind is ClaimKind.CITATION:
        return _ground_citation(value, index)
    if kind is ClaimKind.INSTRUMENT:
        return _ground_instrument(value, index)
    windows = [w for w in index.windows if _window_has(w, claim)]
    if windows:
        return (
            GroundedBy.PREMISE
            if any(w.kind is not PassageKind.FACT for w in windows)
            else GroundedBy.FACT
        )
    number = numeric_part(claim)
    if kind is ClaimKind.NUMBER and number in index.numbers:
        return GroundedBy.METADATA
    return None


def _window_has(window: WindowIndex, claim: Claim) -> bool:
    if claim.kind is ClaimKind.DATE:
        return any(
            c.kind is ClaimKind.DATE and c.value.startswith(claim.value) for c in window.claims
        )
    if claim.kind is ClaimKind.NUMBER:
        return any(numeric_part(c) == claim.value for c in window.claims if c.kind in FIGURE_KINDS)
    if claim.kind is ClaimKind.DURATION:
        if any(c.kind is ClaimKind.DURATION and c.value == claim.value for c in window.claims):
            return True
        number, unit = claim.value.split(":")
        return unit in window.text.lower() and any(
            numeric_part(c) == number for c in window.claims if c.kind in FIGURE_KINDS
        )
    return any(c.kind is claim.kind and c.value == claim.value for c in window.claims)


def _ground_citation(value: str, index: PremiseIndex) -> GroundedBy | None:
    def matches(pool: frozenset[str]) -> bool:
        if is_relative(value):
            labels = value[2:].split("/")
            for cite in pool:
                parts = cite.split("/")[1:]
                for i in range(len(parts) - len(labels) + 1):
                    if parts[i : i + len(labels)] == labels:
                        return True
            return False
        return value in pool or any(c.startswith(value + "/") for c in pool)

    if matches(index.text_citations):
        return GroundedBy.PREMISE
    if matches(index.declared_citations):
        return GroundedBy.METADATA
    return None


def _ground_instrument(value: str, index: PremiseIndex) -> GroundedBy | None:
    if value.startswith("si:"):
        return GroundedBy.METADATA if value in index.sis else None
    if value.startswith("acr:"):
        return GroundedBy.METADATA if value[4:] in index.acronyms else None
    words = value.split()
    for title in index.titles:
        known = title.split()
        shorter = min(len(words), len(known))
        if shorter >= 3 and words[-shorter:] == known[-shorter:]:  # noqa: PLR2004
            return GroundedBy.METADATA
    return None


def _in_query(claim: Claim, query_claims: list[Claim]) -> bool:
    for q in query_claims:
        if q.kind is claim.kind and q.value == claim.value:
            return True
        if (
            claim.kind is ClaimKind.NUMBER
            and q.kind in FIGURE_KINDS
            and numeric_part(q) == claim.value
        ):
            return True
    return False


def _refine(result: ClaimResult, aligned: list[WindowIndex]) -> ClaimResult:
    if result.grounded_by in {GroundedBy.PREMISE, GroundedBy.FACT} and any(
        _window_has(w, result.claim) for w in aligned
    ):
        return ClaimResult(result.claim, GroundedBy.WINDOW, result.reason)
    return result


def _first(results: Sequence[ClaimResult]) -> ClaimResult:
    return min((r for r in results if r.reason is not None), key=lambda r: r.claim.start)


def _unique(reasons: Any) -> tuple[Reason, ...]:
    return tuple(dict.fromkeys(reasons))


def _shift(verdict: SentenceVerdict, offset: int) -> SentenceVerdict:
    return SentenceVerdict(
        verdict.text,
        verdict.start + offset,
        verdict.end + offset,
        verdict.verdict,
        verdict.reasons,
        verdict.claims,
        verdict.deontics,
        verdict.aligned,
        verdict.nli,
        verdict.repair,
        verdict.claim_latency_ns,
        verdict.nli_latency_ns,
        verdict.details,
    )
