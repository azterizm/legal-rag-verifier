"""Grid remediation loops (4A/4D full retry, 4C continuation, 4B record) with scripted chats."""

from __future__ import annotations

from collections.abc import Sequence

from legal_rag_verifier.engine import DEFAULT_REFUSAL, SYSTEM_PROMPT, InFlightGenerator
from legal_rag_verifier.premise import Premise
from legal_rag_verifier.verifier import Verifier
from scripts.grid_cells import (
    CONTINUE,
    MAX_RETRIES,
    Messages,
    Reply,
    continuation,
    full_retry,
    in_flight,
)
from tests.test_engine import ScriptedBackend

PREMISE = Premise.from_text(
    "The limit of a compensatory award is £123,543.", titles=("Employment Rights Act 1996",)
)
QUERY = "What is the cap?"


class Scripted:
    """Returns the scripted replies in order (the last one repeats) and records each request."""

    def __init__(self, replies: Sequence[str]) -> None:
        self.replies = list(replies)
        self.requests: list[Messages] = []

    def __call__(self, messages: Messages) -> Reply:
        self.requests.append(messages)
        text = self.replies[min(len(self.requests), len(self.replies)) - 1]
        return Reply(text, len(text.split()), 100, 1_000_000)


def test_full_retry_regenerates_with_the_vault_message() -> None:
    chat = Scripted(["The limit is £85,000.", "The limit is £123,543."])
    record = full_retry(chat, Verifier(), QUERY, PREMISE, SYSTEM_PROMPT)
    assert record["answer"] == "The limit is £123,543."
    assert record["resolved"]
    assert record["retries"] == 1
    assert record["tokens_discarded"] == 4
    feedback = chat.requests[1][-1]
    assert feedback == {
        "role": "user",
        "content": "Previous response hallucinated '£85,000'. Regenerate.",
    }
    assert chat.requests[1][-2] == {"role": "assistant", "content": "The limit is £85,000."}


def test_full_retry_gives_up_after_three_retries() -> None:
    chat = Scripted(["The limit is £85,000."])
    record = full_retry(chat, Verifier(), QUERY, PREMISE, SYSTEM_PROMPT)
    assert not record["resolved"]
    assert record["retries"] == MAX_RETRIES
    assert len(chat.requests) == MAX_RETRIES + 1
    assert record["answer"] == "The limit is £85,000."


def test_continuation_keeps_the_verified_prefix_and_resumes_after_it() -> None:
    chat = Scripted(
        [
            "It applies to compensatory awards. The limit is £85,000. More text.",
            "The limit is £123,543.",
        ]
    )
    record = continuation(chat, Verifier(), QUERY, PREMISE, SYSTEM_PROMPT)
    assert record["answer"] == "It applies to compensatory awards. The limit is £123,543."
    assert record["resolved"]
    assert record["retries"] == 1
    resumed = chat.requests[1]
    assert resumed[-2] == {"role": "assistant", "content": "It applies to compensatory awards."}
    assert resumed[-1]["content"].startswith(CONTINUE)
    assert "'£85,000'" in resumed[-1]["content"]
    assert record["time_to_first_output_ns"] is not None


def test_continuation_refuses_a_point_after_three_retries_and_moves_on() -> None:
    chat = Scripted(["The limit is £85,000."] * (MAX_RETRIES + 1) + [""])
    record = continuation(chat, Verifier(), QUERY, PREMISE, SYSTEM_PROMPT)
    assert record["answer"] == DEFAULT_REFUSAL
    assert record["refusals"] == 1
    assert record["retries"] == MAX_RETRIES
    assert not record["resolved"]


def test_continuation_drops_a_restated_prefix() -> None:
    chat = Scripted(
        [
            "It applies to compensatory awards. The limit is £85,000.",
            "It applies to compensatory awards. The limit is £123,543.",
        ]
    )
    record = continuation(chat, Verifier(), QUERY, PREMISE, SYSTEM_PROMPT)
    assert record["answer"] == "It applies to compensatory awards. The limit is £123,543."


def test_in_flight_record_has_the_grid_fields() -> None:
    backend = ScriptedBackend(["The limit is £85,000.", "The limit is £123,543."])
    record = in_flight(InFlightGenerator(backend, Verifier()), QUERY, PREMISE)
    assert record["answer"] == "The limit is £123,543."
    assert record["resolved"]
    assert record["retries"] == 1
    assert record["refusals"] == 0
    assert record["tokens_discarded"] == len("£85,000.")
    assert record["time_to_first_output_ns"] > 0
