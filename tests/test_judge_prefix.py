"""Stop 77: the judge's answer so far, post-hoc and live, and the measured preset."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from legal_rag_verifier.engine import InFlightGenerator
from legal_rag_verifier.judge import (
    PRESETS,
    SHORT_SHA,
    STRICT_FIGURES,
    Judge,
    JudgedVerifier,
    OpenAIChat,
    prompt_key,
)
from legal_rag_verifier.premise import Premise
from legal_rag_verifier.verifier import Verdict, Verifier
from scripts import live_loop as ll
from tests.test_engine import PREMISE as SOURCE
from tests.test_engine import QUERY, ScriptedBackend

PREMISE = Premise.from_text(
    "The employer shall give written reasons for dismissal within fourteen days.\n\n"
    "The tribunal may order reinstatement."
)
FIRST = "The employer gives written reasons."
SECOND = "The reasons are given in writing."
THIRD = "The tribunal orders reinstatement."
TEXT = f"{FIRST} {SECOND} {THIRD}"
MODEL = "Vishva007/Qwen3.8-27B-W4A16-AutoRound-GPTQ"
REVISION = "1b9d56b428e9f841d7ad566f87660b5f47553c97"
RECORD_KEYS = {"sha", "label", "passage", "attempts", "ms", "tokens", "sentence", "preset", "error"}


def sentence_of(user: str) -> str:
    return user.split("Sentence to check:\n<<<\n", 1)[1].split("\n>>>", 1)[0]


def answer_so_far(user: str) -> str:
    return user.split("It is not evidence.\n<<<\n", 1)[1].split("\n>>>", 1)[0]


class Chat:
    """Labels each sentence as scripted (supported by default) and keeps every user prompt."""

    def __init__(self, labels: Mapping[str, str] | None = None) -> None:
        self.labels = dict(labels or {})
        self.users: list[str] = []

    def __call__(self, messages: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        user = str(messages[1]["content"])
        self.users.append(user)
        label = self.labels.get(sentence_of(user), "supported")
        content = json.dumps({"label": label, "passage": 1 if label != "not_stated" else 0})
        return {"content": content, "ms": 2.0, "tokens": 4, "finish": "stop"}

    @property
    def prefixes(self) -> list[str]:
        return [answer_so_far(u) for u in self.users]


# ---------------------------------------------------------------------- post-hoc (check_text)


def test_post_hoc_each_sentence_sees_every_earlier_sentence() -> None:
    chat = Chat()
    verifier = JudgedVerifier(Judge(chat))
    verdicts = verifier.check_text(PREMISE, TEXT, query="q")
    assert [v.verdict for v in verdicts] == [Verdict.EMIT] * 3
    assert [sentence_of(u) for u in chat.users] == [FIRST, SECOND, THIRD]
    assert chat.prefixes == ["(none)", FIRST, f"{FIRST} {SECOND}"]
    assert [c["sentence"] for c in verifier.calls] == [0, 1, 2]
    assert [c["sha"] for c in verifier.calls] == [prompt_key(u) for u in chat.users]


def test_post_hoc_prefix_keeps_a_rolled_back_sentence() -> None:
    chat = Chat({FIRST: "not_stated"})
    verifier = JudgedVerifier(Judge(chat))
    verdicts = verifier.check_text(PREMISE, TEXT, query="q")
    assert [v.verdict for v in verdicts] == [Verdict.ROLLBACK, Verdict.EMIT, Verdict.EMIT]
    assert chat.prefixes == ["(none)", FIRST, f"{FIRST} {SECOND}"]
    assert [c["sentence"] for c in verifier.calls] == [0, 1, 2]
    assert verifier.committed == []


def test_post_hoc_returns_the_base_verdicts_with_their_offsets() -> None:
    labels = {FIRST: "not_stated", THIRD: "contradicted"}
    judged = JudgedVerifier(Judge(Chat(labels))).check_text(PREMISE, TEXT, query="q")
    base = Verifier(Judge(Chat(labels)), STRICT_FIGURES)
    expected = base.check_text(PREMISE, TEXT, query="q")

    def view(vs: Sequence[Any]) -> list[tuple[Any, ...]]:
        return [(v.text, v.start, v.end, v.verdict, v.reasons) for v in vs]

    assert view(judged) == view(expected)
    assert [v.start for v in judged] == [0, len(FIRST) + 1, len(FIRST) + len(SECOND) + 2]


def test_check_text_starts_a_fresh_call_log() -> None:
    chat = Chat()
    verifier = JudgedVerifier(Judge(chat))
    verifier.check_text(PREMISE, TEXT, query="q")
    verifier.check_text(PREMISE, f"{THIRD} {FIRST}", query="q")
    assert len(verifier.calls) == 2
    assert [c["sha"] for c in verifier.calls] == [prompt_key(u) for u in chat.users[3:]]
    assert [c["sentence"] for c in verifier.calls] == [0, 1]
    assert chat.prefixes[3:] == ["(none)", THIRD]


def test_check_text_ignores_the_live_answer() -> None:
    chat = Chat()
    verifier = JudgedVerifier(Judge(chat))
    verifier.check_sentence(PREMISE, THIRD, query="q")
    assert verifier.committed == [THIRD]
    verifier.check_text(PREMISE, f"{FIRST} {SECOND}", query="q")
    assert chat.prefixes[1:] == ["(none)", FIRST]
    assert verifier.committed == []


# ---------------------------------------------------------------------- live (check_sentence)


def test_live_prefix_is_only_the_emitted_sentences() -> None:
    chat = Chat({FIRST: "not_stated"})
    verifier = JudgedVerifier(Judge(chat))
    verdicts = [verifier.check_sentence(PREMISE, s, query="q") for s in (FIRST, SECOND, THIRD)]
    assert [v.verdict for v in verdicts] == [Verdict.ROLLBACK, Verdict.EMIT, Verdict.EMIT]
    assert chat.prefixes == ["(none)", "(none)", SECOND]
    assert verifier.committed == [SECOND, THIRD]
    assert [c["sentence"] for c in verifier.calls] == [0, 0, 1]


def test_live_sentence_index_is_the_number_of_committed_sentences() -> None:
    chat = Chat({SECOND: "contradicted"})
    verifier = JudgedVerifier(Judge(chat))
    seen = []
    for s in (FIRST, SECOND, THIRD, FIRST):
        before = len(verifier.committed)
        verifier.check_sentence(PREMISE, s, query="q")
        seen.append((verifier.calls[-1]["sentence"], before))
    assert all(index == before for index, before in seen)
    assert [index for index, _ in seen] == [0, 1, 1, 2]


def test_reset_clears_the_answer_the_calls_and_the_prefix() -> None:
    chat = Chat()
    judge = Judge(chat)
    verifier = JudgedVerifier(judge)
    verifier.check_sentence(PREMISE, FIRST, query="q")
    verifier.check_sentence(PREMISE, SECOND, query="q")
    assert judge.prefix == FIRST
    verifier.reset()
    assert verifier.committed == []
    assert verifier.calls == []
    assert judge.calls == []
    assert judge.prefix == ""
    assert judge.sentence is None
    verifier.check_sentence(PREMISE, THIRD, query="q")
    assert chat.prefixes[-1] == "(none)"
    assert [c["sentence"] for c in verifier.calls] == [0]


def test_live_prompts_equal_the_loop_verifiers() -> None:
    labels = {FIRST: "not_stated", THIRD: "contradicted"}
    sentences = (FIRST, SECOND, THIRD, FIRST, SECOND)
    ours, theirs = Chat(labels), Chat(labels)
    judged = JudgedVerifier(Judge(ours))
    loop = ll.LoopVerifier(ll.LiveJudge(theirs, "judge@rev"))

    def run(verifier: Any) -> list[Verdict]:
        out = [verifier.check_sentence(PREMISE, s, query="q").verdict for s in sentences]
        verifier.reset()
        out.append(verifier.check_sentence(PREMISE, SECOND, query="q").verdict)
        return out

    assert run(judged) == run(loop)
    assert ours.users == theirs.users
    assert len(ours.users) == len(sentences) + 1
    assert judged.committed == loop.committed == [SECOND]


# ---------------------------------------------------------------------- measured and hand-built


def test_a_preset_judge_names_its_measured_configuration() -> None:
    judge = Judge.from_preset("qwen27-ar4", "http://127.0.0.1:1")
    assert judge.preset == "qwen27-ar4"
    assert judge.model_id == f"{MODEL}@{REVISION}"
    assert judge.calls == []


def test_a_hand_built_judge_is_unmeasured() -> None:
    judge = Judge(Chat())
    assert judge.preset is None
    verifier = JudgedVerifier(judge)
    verifier.check_text(PREMISE, FIRST, query="q")
    assert [c["preset"] for c in verifier.calls] == [None]
    assert set(verifier.calls[0]) == RECORD_KEYS


def test_the_preset_holds_the_measured_prompt() -> None:
    preset = PRESETS["qwen27-ar4"]
    assert SHORT_SHA == "7748f874db902456700c3ff64c1b4e37621e951ed0c3c65495b8b3c5911be149"
    assert preset.prompt_sha256 == SHORT_SHA
    assert preset.reply == "short"
    assert (preset.model, preset.revision) == (MODEL, REVISION)


def test_a_preset_is_frozen_and_an_unknown_name_is_refused() -> None:
    preset = PRESETS["qwen27-ar4"]
    assert dataclasses.is_dataclass(preset)
    field = "reply"
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(preset, field, "full")
    with pytest.raises(TypeError):
        preset.sampling["seed"] = 1  # type: ignore[index]
    with pytest.raises(TypeError):
        preset.template_kwargs["enable_thinking"] = True  # type: ignore[index]
    assert preset.sampling["seed"] == 0
    assert preset.template_kwargs["enable_thinking"] is False
    with pytest.raises(KeyError):
        Judge.from_preset("no-such-judge", "http://127.0.0.1:1")


def test_a_preset_judge_gets_plain_dict_copies() -> None:
    chat = Judge.from_preset("qwen27-ar4", "http://127.0.0.1:1").chat
    assert isinstance(chat, OpenAIChat)
    preset = PRESETS["qwen27-ar4"]
    assert type(chat.sampling) is dict
    assert type(chat.template_kwargs) is dict
    assert chat.sampling == dict(preset.sampling)
    assert chat.template_kwargs == dict(preset.template_kwargs)


def test_a_preset_with_an_unknown_reply_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    odd = dataclasses.replace(PRESETS["qwen27-ar4"], reply="long")
    monkeypatch.setitem(PRESETS, "odd", odd)
    with pytest.raises(ValueError, match="reply"):
        Judge.from_preset("odd", "http://127.0.0.1:1")


# ---------------------------------------------------------------------- the engine's path


def test_the_engine_checks_each_sentence_with_the_live_prefix() -> None:
    first, second = "The limit is £123,543.", "It applies to unfair dismissal."
    chat = Chat()
    verifier = JudgedVerifier(Judge(chat))
    backend = ScriptedBackend([f"{first} {second}"])
    answer = InFlightGenerator(backend, verifier).generate_verified(QUERY, SOURCE)
    assert answer.text == f"{first} {second}"
    assert [sentence_of(u) for u in chat.users] == [first, second]
    assert chat.prefixes == ["(none)", first]
    assert verifier.committed == [first, second]
    assert [c["sentence"] for c in verifier.calls] == [0, 1]
