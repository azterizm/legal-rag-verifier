"""Controller logic on a scripted, character-level fake backend (no model, no torch)."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from legal_rag_verifier.engine import (
    DEFAULT_REFUSAL,
    INJECT_TEMPLATE,
    Allow,
    Ban,
    Constraint,
    InFlightGenerator,
    Segment,
    Tokens,
)
from legal_rag_verifier.premise import Premise
from legal_rag_verifier.verifier import Verifier

PREMISE = Premise.from_text(
    "The limit of a compensatory award is £123,543.",
    titles=("Employment Rights Act 1996",),
    citations=("s124",),
)
QUERY = "What is the cap on the compensatory award?"
EOS = -1


class ScriptedBackend:
    """One token per character. The "model" prefers the first script that continues the text."""

    name = "fake"
    model_id = "fake@0"
    prompt = "Q>"

    def __init__(self, scripts: Sequence[str]) -> None:
        self.scripts = list(scripts)
        self.cached: Tokens = ()
        self.calls: list[tuple[int, int]] = []  # (len(committed), prefix-cache hit)

    def chat(self, messages: Sequence[Mapping[str, str]]) -> Tokens:
        return self.encode(self.prompt)

    def encode(self, text: str) -> Tokens:
        return tuple(ord(c) for c in text)

    def decode(self, tokens: Sequence[int]) -> str:
        return "".join(chr(t) for t in tokens)

    def extend(
        self,
        committed: Sequence[int],
        *,
        stop: Sequence[str],
        max_new: int,
        constraint: Constraint | None,
    ) -> Segment:
        hit = 0
        for a, b in zip(self.cached, committed, strict=False):
            if a != b:
                break
            hit += 1
        hit = min(hit, len(committed) - 1)
        self.calls.append((len(committed), hit))
        text = self.decode(committed)[len(self.prompt) :]
        out: list[int] = []
        finish = "length"
        span = isinstance(constraint, Allow)
        while len(out) < max_new:
            token = self._choose(text + self.decode(out), constraint, out, span)
            if isinstance(constraint, Allow) and span:
                span = constraint.next_tokens([*out, token]) is not None
            if token == EOS:
                finish = "eos"
                break
            out.append(token)
            if not span and chr(token) in stop:
                finish = "stop"
                break
        self.cached = (*committed, *out)
        return Segment(tuple(out), self.decode(out), finish, hit, 1000)  # type: ignore[arg-type]

    def _choose(self, text: str, constraint: Constraint | None, out: list[int], span: bool) -> int:
        options = [s[len(text) :] for s in self.scripts if s.startswith(text)]
        banned = constraint.banned(len(out)) if isinstance(constraint, Ban) else frozenset()
        allowed = constraint.next_tokens(out) if isinstance(constraint, Allow) and span else None
        for option in options:
            token = ord(option[0]) if option else EOS
            if token in banned or (allowed is not None and token not in allowed):
                continue
            return token
        return min(allowed) if allowed else EOS


def generate(scripts: Sequence[str], **kwargs: Any) -> tuple[str, dict[str, Any]]:
    backend = ScriptedBackend(scripts)
    answer = InFlightGenerator(backend, Verifier(), **kwargs).generate_verified(QUERY, PREMISE)
    return answer.text, answer.trace


def test_grounded_answer_is_emitted_unchanged() -> None:
    text, trace = generate(["The limit is £123,543. It applies to unfair dismissal."])
    assert text == "The limit is £123,543. It applies to unfair dismissal."
    assert [s["outcome"] for s in trace["sentences"]] == ["emitted", "emitted"]
    assert trace["totals"]["rollbacks"] == 0
    assert trace["stop_reason"] == "eos"


def test_allow_list_resumes_at_the_figure_and_excludes_the_rejected_value() -> None:
    text, trace = generate(["The limit is £85,000.", "The limit is £123,543."])
    assert text == "The limit is £123,543."
    sentence = trace["sentences"][0]
    assert sentence["rollbacks"] == 1
    assert sentence["recovered_by"] == "allow"
    first, second = sentence["attempts"]
    assert first["verdict"]["reasons"] == ["UNGROUNDED_FIGURE"]
    assert second["steering"] == "allow"
    assert second["tokens_reused"] == len("The limit is ")  # kept up to the divergence point
    assert first["tokens_discarded"] == len("£85,000.")
    allowed = ["".join(chr(t) for t in seq) for seq in second["constraint"]["allow"]]
    assert allowed == ["£123,543"]


def test_allow_overrides_the_model_preference() -> None:
    # The model only ever wants £85,000; the constraint forces the premise figure anyway.
    text, trace = generate(["The limit is £85,000. It applies to unfair dismissal."])
    assert text.startswith("The limit is £123,543")
    assert trace["sentences"][0]["recovered_by"] == "allow"


def test_ban_path_restarts_the_sentence_without_its_first_token() -> None:
    text, trace = generate(
        ["The limit is £85,000.", "A compensatory award is capped at £123,543."],
        steering="ban",
    )
    assert text == "A compensatory award is capped at £123,543."
    attempt = trace["sentences"][0]["attempts"][1]
    assert attempt["steering"] == "ban"
    assert attempt["constraint"] == {"ban": [ord("T")]}
    assert trace["sentences"][0]["recovered_by"] == "ban"


def test_a_point_is_refused_when_its_third_retry_also_fails() -> None:
    scripts = [
        "The limit is £85,000.",
        "A cap of £90,000 applies.",
        "Compensation is £70,000.",
        "Damages stop at £60,000.",
        "Each award is £123,543.",
    ]
    text, trace = generate(scripts, steering="ban")
    assert text == DEFAULT_REFUSAL
    sentence = trace["sentences"][0]
    assert sentence["outcome"] == "refused"
    assert len(sentence["attempts"]) == 4  # the draft and three retries; the fifth is never tried
    assert sentence["rollbacks"] == 4
    assert trace["totals"]["refused"] == 1


def test_a_third_retry_can_still_recover() -> None:
    scripts = [
        "The limit is £85,000.",
        "A cap of £90,000 applies.",
        "Compensation is £70,000.",
        "Each award is capped at £123,543.",
    ]
    text, trace = generate(scripts, steering="ban")
    assert text == scripts[3]
    assert trace["sentences"][0]["rollbacks"] == 3
    assert trace["sentences"][0]["recovered_by"] == "ban"


def test_a_retry_that_gives_nothing_is_refused_not_dropped() -> None:
    text, trace = generate(["The limit is £85,000."], steering="ban")
    assert text == DEFAULT_REFUSAL
    assert trace["sentences"][0]["outcome"] == "refused"
    assert trace["sentences"][0]["rollbacks"] == 1


def test_rollback_budget_ends_the_answer() -> None:
    text, trace = generate(["The limit is £85,000."], steering="ban", max_total_rollbacks=0)
    assert text == DEFAULT_REFUSAL
    assert trace["stop_reason"] == "rollback_budget"


def test_false_stop_extends_the_same_sentence_with_a_cache_hit() -> None:
    scripts = ["Under s. 124 the limit is £123,543. That is all."]
    backend = ScriptedBackend(scripts)
    answer = InFlightGenerator(backend, Verifier()).generate_verified(QUERY, PREMISE)
    first = answer.trace["sentences"][0]
    assert first["text"] == "Under s. 124 the limit is £123,543."
    assert first["outcome"] == "emitted"
    assert first["attempts"][0]["decode_calls"] > 1  # stopped at "s.", then extended
    # Every call after the first reuses everything committed but the last token.
    assert all(hit == n - 1 for n, hit in backend.calls[1:])
    assert answer.text == scripts[0]


def test_rollback_resubmits_the_committed_prefix() -> None:
    scripts = [
        "It applies to unfair dismissal. The limit is £85,000.",
        "It applies to unfair dismissal. The limit is £123,543.",
    ]
    backend = ScriptedBackend(scripts)
    answer = InFlightGenerator(backend, Verifier()).generate_verified(QUERY, PREMISE)
    assert answer.text == scripts[1]
    assert answer.trace["sentences"][1]["recovered_by"] == "allow"
    # The resumed call reuses the prompt, the first sentence and the kept words of the second.
    committed = len("Q>") + len("It applies to unfair dismissal. The limit is ")
    assert (committed, committed - 1) in backend.calls


def test_newlines_between_sentences_are_kept_and_not_verified() -> None:
    text, trace = generate(["The limit is £123,543.\n\nIt applies to unfair dismissal."])
    assert text == "The limit is £123,543.\n\nIt applies to unfair dismissal."
    assert len(trace["sentences"]) == 2


def test_trace_is_canonical_json_with_backend_and_verifier_settings() -> None:
    backend = ScriptedBackend(["The limit is £85,000.", "The limit is £123,543."])
    answer = InFlightGenerator(backend, Verifier()).generate_verified(QUERY, PREMISE)
    dumped = answer.trace_json()
    assert json.loads(dumped) == answer.trace
    assert dumped == json.dumps(
        json.loads(dumped), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    assert answer.trace["backend"] == "fake"
    assert answer.trace["model"] == "fake@0"
    assert answer.trace["verifier"]["config"]["entail_threshold"] == 0.70
    assert answer.trace["engine"]["max_rollbacks"] == 3
    assert answer.trace["totals"]["tokens_discarded"] == len("£85,000.")


def test_allow_constraint_lifts_when_a_sequence_completes() -> None:
    allow = Allow(((1, 2, 3), (1, 4)))
    assert allow.next_tokens([]) == frozenset({1})
    assert allow.next_tokens([1]) == frozenset({2, 4})
    assert allow.next_tokens([1, 4]) is None
    assert allow.next_tokens([9]) is None
    assert Ban(frozenset({5})).banned(0) == frozenset({5})
    assert Ban(frozenset({5})).banned(1) == frozenset()


def test_failed_allow_retry_falls_back_to_ban_before_refusing() -> None:
    # Live case (stop 18): the allow-list fixes the figure, but the frame still drops a qualifier.
    premise = Premise.from_text(
        "The amount is the lower of £123,543 and 52 multiplied by a week's pay.",
        titles=("Employment Rights Act 1996",),
    )
    scripts = [
        "The cap is £85,000.",
        "Compensation is the lower of £123,543 and 52 multiplied by a week's pay.",
    ]
    backend = ScriptedBackend(scripts)
    answer = InFlightGenerator(backend, Verifier()).generate_verified(QUERY, premise)
    assert answer.text == scripts[1]
    sentence = answer.trace["sentences"][0]
    assert [a["steering"] for a in sentence["attempts"]] == [None, "allow", "ban"]
    assert sentence["attempts"][1]["verdict"]["reasons"] == ["QUALIFIER_DROPPED"]
    assert sentence["rollbacks"] == 2
    assert sentence["recovered_by"] == "ban"


# ---------------------------------------------------------------------- inject (stop 27)
NOTE_SOURCE = "The limit of a compensatory award is £123,543."
NOTE = INJECT_TEMPLATE.format(source=NOTE_SOURCE)


def test_inject_writes_the_aligned_window_into_the_context_and_regenerates() -> None:
    backend = ScriptedBackend(["The limit is £85,000.", NOTE + "The limit is £123,543."])
    engine = InFlightGenerator(backend, Verifier(), steering="inject")
    answer = engine.generate_verified(QUERY, PREMISE)
    assert answer.text == "The limit is £123,543."  # the source is context, never answer text
    sentence = answer.trace["sentences"][0]
    assert [a["steering"] for a in sentence["attempts"]] == [None, "inject"]
    assert sentence["attempts"][1]["injected"] == {"windows": [0], "tokens": len(NOTE)}
    assert sentence["attempts"][1]["constraint"] is None
    assert sentence["recovered_by"] == "inject"
    totals = answer.trace["totals"]
    assert (totals["injections"], totals["tokens_injected"]) == (1, len(NOTE))
    assert totals["recovered_by_inject"] == 1
    assert answer.trace["engine"]["inject_template"] == INJECT_TEMPLATE
    # The retry resubmits the committed prefix plus the source: only the source is new.
    retry = next(c for c in backend.calls if c[0] == len(backend.prompt) + len(NOTE))
    assert retry[1] == len(backend.prompt)


def test_inject_template_may_restate_the_query() -> None:
    template = "\n[{query}] {source}\n"
    note = template.format(query=QUERY, source=NOTE_SOURCE)
    backend = ScriptedBackend(["The limit is £85,000.", note + "The limit is £123,543."])
    engine = InFlightGenerator(backend, Verifier(), steering="inject", inject_template=template)
    answer = engine.generate_verified(QUERY, PREMISE)
    assert answer.text == "The limit is £123,543."
    assert answer.trace["sentences"][0]["attempts"][1]["injected"]["tokens"] == len(note)


def test_inject_mid_answer_keeps_the_source_in_context_and_spaces_the_answer() -> None:
    first = "The limit is £123,543."
    scripts = [f"{first} The limit is £85,000.", f"{first}{NOTE}It applies to unfair dismissal."]
    backend = ScriptedBackend(scripts)
    answer = InFlightGenerator(backend, Verifier(), steering="inject").generate_verified(
        QUERY, PREMISE
    )
    assert answer.text == f"{first} It applies to unfair dismissal."
    assert [s["outcome"] for s in answer.trace["sentences"]] == ["emitted", "emitted"]
    assert answer.trace["sentences"][1]["recovered_by"] == "inject"


def test_a_window_is_injected_once_then_the_retry_falls_back_to_ban() -> None:
    scripts = ["The limit is £85,000.", NOTE + "The limit is £85,000.", NOTE + "A limit applies."]
    answer = InFlightGenerator(ScriptedBackend(scripts), Verifier(), steering="inject")
    out = answer.generate_verified(QUERY, PREMISE)
    sentence = out.trace["sentences"][0]
    assert [a["steering"] for a in sentence["attempts"]] == [None, "inject", "ban"]
    assert [a["injected"] for a in sentence["attempts"]][2] is None
    assert out.text == "A limit applies."
    assert sentence["recovered_by"] == "ban"


def test_inject_with_no_window_to_inject_bans_instead() -> None:
    backend = ScriptedBackend(["The limit is £85,000.", "A limit applies."])
    engine = InFlightGenerator(backend, Verifier(), steering="inject")
    answer = engine.generate_verified(QUERY, Premise.from_text(""))
    assert answer.text == "A limit applies."
    assert [a["steering"] for a in answer.trace["sentences"][0]["attempts"]] == [None, "ban"]
    assert answer.trace["totals"]["injections"] == 0


def test_other_modes_record_no_injection() -> None:
    _, trace = generate(["The limit is £85,000.", "The limit is £123,543."], steering="ban")
    assert all(a["injected"] is None for s in trace["sentences"] for a in s["attempts"])
    assert trace["totals"]["injections"] == 0
    assert trace["engine"]["inject_template"] is None
