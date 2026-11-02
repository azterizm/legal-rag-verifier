"""Stop 77: the package judge's prompt, parsing, retries and scoring (``legal_rag_verifier.judge``),
checked against ``scripts/auditor_judge.py`` with fake chats only (no HTTP)."""

from __future__ import annotations

import copy
import email.message
import hashlib
import http.client
import re
import urllib.error
from collections.abc import Callable, Sequence
from typing import Any

import pytest

from legal_rag_verifier import judge
from legal_rag_verifier.verifier import NLIProbs, VerifierConfig
from scripts import auditor_judge as aj
from scripts import fresh_arms as fa

SHORT_SHA = "7748f874db902456700c3ff64c1b4e37621e951ed0c3c65495b8b3c5911be149"
PROMPT_SHA = "72ce7d0514311749ccdd1d9f4430f5beea7d8757eeb9bd73be16fe9eae0e437b"
# Literals computed from scripts/auditor_judge.py at commit 70e689b, before the scripts imported
# these names from the package: they guard against a drift the byte comparison above cannot see.
RETRY_SHA = "6eddaf3f8be80a18061e3c700fe3a13b5d0c62c6a27aefcbe420e844c980e602"
RENDERED_KEY = "69dfc7b7b8dc40b019445dace019820387983145a252227e4c4eb3f50044280e"
RECORD_KEYS = {"sha", "label", "passage", "attempts", "ms", "tokens", "sentence", "preset", "error"}
NEUTRAL = NLIProbs(0.0, 1.0, 0.0)
ENTAIL = NLIProbs(1.0, 0.0, 0.0)
CONTRADICT = NLIProbs(0.0, 0.0, 1.0)

PREMISES = ("The divisor used in calculations is N - ddof.", "By default ddof is zero.")
HYPOTHESIS = "It divides by N."
PREFIX = "numpy.std takes a parameter ddof."
GOOD = '{"label": "supported", "passage": 2}'
BAD = "no json"

REPLIES = [
    '{"label": "supported", "passage": 1, "reason": "r"}',
    '```json\n{"label": "contradicted", "passage": "2"}\n```',
    '<think>Passage 1 states it.</think>\n{"label": "supported", "passage": 1}',
    '{"label": "Not stated", "passage": 0, "reason": "neither"}',
    '{"label": "not_stated", "passage": "x"}',
]
BAD_REPLIES = ['{"label": "maybe", "passage": 1}', "no json", "{not json}", "[1, 2]", ""]


def short_sha(system: str, user: str, short_reply: str) -> str:
    """``scripts/fresh_arms.py:137``: the stop 42 template with its reply sentence replaced."""
    reply = user[user.index("Return JSON") :]
    return hashlib.sha256((system + user.replace(reply, short_reply)).encode()).hexdigest()


def script_error(text: str) -> ValueError:
    """What ``scripts/auditor_judge.py``'s ``parse_reply`` raises on ``text``."""
    try:
        aj.parse_reply(text)
    except ValueError as exc:
        return exc
    raise AssertionError(f"the script parsed {text!r}")


def prompt_sha(system: str, user: str) -> str:
    return hashlib.sha256((system + user).encode()).hexdigest()


def flip(text: str, i: int) -> str:
    """``text`` with one ASCII byte changed."""
    return text[:i] + chr(ord(text[i]) ^ 1) + text[i + 1 :]


def reply(content: str, *, ms: float = 10.0, tokens: int | None = 5) -> dict[str, Any]:
    return {"content": content, "ms": ms, "tokens": tokens, "finish": "stop"}


class FakeChat:
    """A chat that plays ``steps`` in order (a reply dict, or an exception to raise), repeating
    the last one, and records a copy of every message list it receives."""

    def __init__(self, steps: Sequence[dict[str, Any] | BaseException]) -> None:
        self.steps = list(steps)
        self.sent: list[list[dict[str, str]]] = []

    def __call__(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        self.sent.append(copy.deepcopy(messages))
        step = self.steps[min(len(self.sent), len(self.steps)) - 1]
        if isinstance(step, BaseException):
            raise step
        return step


class NamedChat(FakeChat):
    model = "fake/judge-model"


def first(user: str) -> list[dict[str, str]]:
    return [{"role": "system", "content": judge.SYSTEM}, {"role": "user", "content": user}]


def retry(user: str, bad: str) -> list[dict[str, str]]:
    return [
        *first(user),
        {"role": "assistant", "content": bad},
        {"role": "user", "content": judge.RETRY},
    ]


def run(
    steps: Sequence[dict[str, Any] | BaseException],
) -> tuple[FakeChat, judge.Judge, list[NLIProbs], dict[str, Any]]:
    chat = FakeChat(steps)
    j = judge.Judge(chat)
    j.prefix = PREFIX
    out = j.score(list(PREMISES), HYPOTHESIS)
    assert len(j.calls) == 1
    return chat, j, out, j.calls[0]


USER = aj.short_prompt(HYPOTHESIS, list(PREMISES), PREFIX)


# ---------------------------------------------------------------------- bytes and hashes


def test_the_prompt_constants_are_the_scripts_bytes() -> None:
    for name in ("SYSTEM", "USER", "SHORT_REPLY", "RETRY"):
        ours, theirs = getattr(judge, name), getattr(aj, name)
        assert isinstance(ours, str), name
        assert ours.encode() == theirs.encode(), name
    assert judge.LABELS == aj.LABELS == ("supported", "contradicted", "not_stated")
    assert [x.encode() for x in judge.LABELS] == [x.encode() for x in aj.LABELS]


def test_the_hashes_are_the_measured_ones() -> None:
    assert judge.SHORT_SHA == SHORT_SHA == fa.SHORT_SHA
    assert short_sha(judge.SYSTEM, judge.USER, judge.SHORT_REPLY) == SHORT_SHA
    assert judge.PROMPT_SHA == PROMPT_SHA == aj.PROMPT_SHA
    assert prompt_sha(judge.SYSTEM, judge.USER) == PROMPT_SHA


@pytest.mark.parametrize("name", ["SYSTEM", "USER", "SHORT_REPLY"])
def test_a_one_byte_change_breaks_the_hash(name: str) -> None:
    parts = {"SYSTEM": judge.SYSTEM, "USER": judge.USER, "SHORT_REPLY": judge.SHORT_REPLY}
    assert short_sha(parts["SYSTEM"], parts["USER"], parts["SHORT_REPLY"]) == SHORT_SHA
    parts[name] = flip(parts[name], 0)
    assert len(parts[name].encode()) == len(getattr(judge, name).encode())
    assert short_sha(parts["SYSTEM"], parts["USER"], parts["SHORT_REPLY"]) != SHORT_SHA
    if name != "SHORT_REPLY":
        assert prompt_sha(parts["SYSTEM"], parts["USER"]) != PROMPT_SHA


def test_retry_and_the_rendering_are_the_measured_bytes() -> None:
    assert hashlib.sha256(judge.RETRY.encode()).hexdigest() == RETRY_SHA
    assert judge.prompt_key(judge.short_prompt("It divides by N.", ["A.", "B."], "x")) == (
        RENDERED_KEY
    )


@pytest.mark.parametrize("i", [0, len(judge.RETRY) // 2, len(judge.RETRY) - 1])
def test_a_one_byte_change_to_retry_breaks_its_hash(i: int) -> None:
    changed = flip(judge.RETRY, i)
    assert len(changed.encode()) == len(judge.RETRY.encode())
    assert hashlib.sha256(changed.encode()).hexdigest() != RETRY_SHA


def test_the_public_names() -> None:
    assert set(judge.__all__) == {
        "LABELS",
        "PRESETS",
        "PROMPT_SHA",
        "RETRY",
        "SHORT_REPLY",
        "SHORT_SHA",
        "STRICT_FIGURES",
        "SYSTEM",
        "USER",
        "Judge",
        "JudgedVerifier",
        "OpenAIChat",
        "Preset",
        "extract_json",
        "one_hot",
        "parse_reply",
        "prompt_key",
        "short_prompt",
        "user_prompt",
    }
    assert all(hasattr(judge, name) for name in judge.__all__)
    assert judge.CLOSE_THINK is aj.CLOSE_THINK  # still defined, for the scripts


# ---------------------------------------------------------------------- pure functions


@pytest.mark.parametrize(
    ("sentence", "candidates", "prefix"),
    [
        (HYPOTHESIS, list(PREMISES), PREFIX),
        ("x", ["only one"], ""),
        ("Nothing to check against.", [], ""),
    ],
)
def test_the_prompts_and_keys_are_the_scripts(
    sentence: str, candidates: list[str], prefix: str
) -> None:
    full = judge.user_prompt(sentence, candidates, prefix)
    short = judge.short_prompt(sentence, candidates, prefix)
    assert full == aj.user_prompt(sentence, candidates, prefix)
    assert short == aj.short_prompt(sentence, candidates, prefix)
    assert short.endswith(judge.SHORT_REPLY)
    assert ("<<<\n(none)\n>>>" in short) is (prefix == "")
    assert judge.prompt_key(short) == aj.prompt_key(short)
    assert (
        judge.prompt_key(short) == hashlib.sha256(f"{judge.SYSTEM}\n{short}".encode()).hexdigest()
    )


@pytest.mark.parametrize("text", REPLIES)
def test_replies_parse_as_the_script_parses_them(text: str) -> None:
    assert judge.extract_json(text) == aj.extract_json(text)
    assert judge.parse_reply(text) == aj.parse_reply(text)


def test_the_parsed_replies() -> None:
    assert [judge.parse_reply(t)["label"] for t in REPLIES] == [
        "supported",
        "contradicted",
        "supported",
        "not_stated",
        "not_stated",
    ]
    assert judge.parse_reply(REPLIES[1])["passage"] == 2
    assert judge.parse_reply(REPLIES[4])["passage"] == 0


@pytest.mark.parametrize("text", BAD_REPLIES)
def test_bad_replies_raise_as_the_script_raises(text: str) -> None:
    theirs = script_error(text)
    with pytest.raises(type(theirs), match=re.escape(str(theirs))) as ours:
        judge.parse_reply(text)
    assert type(ours.value) is type(theirs)


def test_a_bad_label_names_the_label() -> None:
    with pytest.raises(ValueError, match="label"):
        judge.parse_reply('{"label": "maybe"}')


# ---------------------------------------------------------------------- scoring


def test_labels_land_on_the_named_passage() -> None:
    assert judge.one_hot("supported", 2, 3) == [NEUTRAL, ENTAIL, NEUTRAL]
    assert judge.one_hot("contradicted", 1, 2) == [CONTRADICT, NEUTRAL]
    for passage in (0, -1, 4, 9):
        assert judge.one_hot("supported", passage, 3) == [ENTAIL] * 3
        assert judge.one_hot("contradicted", passage, 3) == [CONTRADICT] * 3
    for label in ("not_stated", "error"):
        for passage in (-1, 0, 1, 3, 4):
            assert judge.one_hot(label, passage, 3) == [NEUTRAL] * 3


def test_one_hot_is_the_scripts() -> None:
    for label in (*aj.LABELS, "error"):
        for n in (0, 1, 3):
            for passage in range(-1, n + 2):
                assert judge.one_hot(label, passage, n) == aj.one_hot(label, passage, n)


def test_the_config_is_strict_figures() -> None:
    assert judge.STRICT_FIGURES == aj.STRICT_FIGURES
    assert (
        VerifierConfig(
            neutral_policy="strict",
            neutral_with_grounded_claim="rollback",
            ungrounded_figure="judge",
        )
        == judge.STRICT_FIGURES
    )


# ---------------------------------------------------------------------- the judge, fake chat


def test_a_good_reply_gives_one_record() -> None:
    chat, j, out, rec = run([reply(GOOD, ms=12.5, tokens=7)])
    assert set(rec) == RECORD_KEYS
    assert rec == {
        "sha": judge.prompt_key(judge.short_prompt(HYPOTHESIS, list(PREMISES), PREFIX)),
        "label": "supported",
        "passage": 2,
        "attempts": 1,
        "ms": 12.5,
        "tokens": 7,
        "sentence": None,
        "preset": None,
        "error": None,
    }
    assert rec["sha"] == aj.prompt_key(USER)
    assert chat.sent == [first(USER)]
    assert chat.sent[0][0]["content"] == judge.SYSTEM
    assert out == judge.one_hot("supported", 2, len(PREMISES)) == [NEUTRAL, ENTAIL]
    assert j.score(PREMISES, HYPOTHESIS) == out  # premises as any sequence
    assert len(j.calls) == 2


def test_a_plain_function_works_and_the_record_carries_sentence_and_preset() -> None:
    sent: list[list[dict[str, str]]] = []

    def chat(messages: list[dict[str, str]]) -> dict[str, Any]:
        sent.append(copy.deepcopy(messages))
        return {"content": '{"label": "Not stated", "passage": 1}', "ms": 3.0, "tokens": None}

    j = judge.Judge(chat)
    assert (j.prefix, j.sentence, j.preset, j.calls) == ("", None, None, [])
    assert j.model_id == "unknown"
    j.sentence = 4
    assert j.score(["a passage"], "It is zero.") == [NEUTRAL]
    user = aj.short_prompt("It is zero.", ["a passage"], "")
    assert "(none)" in user
    assert sent == [first(user)]
    (rec,) = j.calls
    assert (rec["label"], rec["passage"], rec["sentence"], rec["tokens"]) == (
        "not_stated",
        1,
        4,
        None,
    )
    assert rec["sha"] == aj.prompt_key(user)


def test_the_model_id_comes_from_the_chat() -> None:
    assert judge.Judge(NamedChat([reply(GOOD)])).model_id == "fake/judge-model"
    assert judge.Judge(FakeChat([reply(GOOD)])).model_id == "unknown"


def test_the_full_reply_uses_the_stop_42_prompt() -> None:
    chat = FakeChat([reply('{"label": "contradicted", "passage": 1, "reason": "r"}')])
    j = judge.Judge(chat, reply="full")
    assert j.score(PREMISES, HYPOTHESIS) == [CONTRADICT, NEUTRAL]
    user = aj.user_prompt(HYPOTHESIS, list(PREMISES), "")
    assert chat.sent == [first(user)]
    assert j.calls[0]["sha"] == aj.prompt_key(user)


@pytest.mark.parametrize("value", ["long", "Short", ""])
def test_another_reply_mode_is_refused(value: Any) -> None:  # Any: past a Literal type
    with pytest.raises(ValueError):  # noqa: PT011 - the contract fixes the type, not the message
        judge.Judge(FakeChat([reply(GOOD)]), reply=value)


# ---------------------------------------------------------------------- retries


def test_a_bad_reply_is_asked_again_with_retry() -> None:
    chat, _, out, rec = run([reply(BAD, ms=10.0, tokens=5), reply(GOOD, ms=2.5, tokens=7)])
    assert chat.sent == [first(USER), retry(USER, BAD)]
    assert (rec["label"], rec["passage"], rec["attempts"], rec["error"]) == (
        "supported",
        2,
        2,
        None,
    )
    assert (rec["ms"], rec["tokens"]) == (12.5, 12)
    assert out == [NEUTRAL, ENTAIL]


def test_only_the_last_bad_reply_is_kept() -> None:
    chat, _, _, rec = run([reply("first bad"), reply("second bad"), reply(GOOD)])
    assert chat.sent == [first(USER), retry(USER, "first bad"), retry(USER, "second bad")]
    assert (rec["label"], rec["attempts"], rec["error"]) == ("supported", 3, None)


def test_three_bad_replies_give_error_scored_not_stated() -> None:
    last = "{not json}"
    raised = script_error(last)
    chat, _, out, rec = run([reply(BAD), reply(BAD), reply(last, tokens=None)])
    assert len(chat.sent) == 3
    assert chat.sent[2] == retry(USER, BAD)
    assert set(rec) == RECORD_KEYS
    assert (rec["label"], rec["passage"], rec["attempts"]) == ("error", 0, 3)
    assert rec["error"] == type(raised).__name__
    assert rec["error"] in {"ValueError", "JSONDecodeError"}
    assert (rec["ms"], rec["tokens"]) == (30.0, 10)
    assert out == [NEUTRAL, NEUTRAL]


def test_the_chat_is_never_called_more_than_three_times() -> None:
    chat, j, _, _ = run([reply(BAD)])
    assert len(chat.sent) == 3
    assert j.calls[0]["error"] == "ValueError"
    j.score(PREMISES, HYPOTHESIS)
    assert len(chat.sent) == 6
    assert [c["attempts"] for c in j.calls] == [3, 3]


# ---------------------------------------------------------------------- transport failures

TRANSPORT: list[Callable[[], BaseException]] = [
    lambda: urllib.error.URLError("connection refused"),
    lambda: urllib.error.HTTPError(
        "http://127.0.0.1:1/v1/chat/completions", 503, "busy", email.message.Message(), None
    ),
    lambda: TimeoutError("timed out"),
    lambda: ConnectionResetError("reset"),
    lambda: OSError("down"),
    lambda: http.client.RemoteDisconnected("gone"),
    lambda: http.client.HTTPException("bad response"),
    lambda: ValueError("non-JSON body"),
    lambda: KeyError("choices"),
    lambda: IndexError("list index out of range"),
]


@pytest.mark.parametrize("make", TRANSPORT, ids=[type(m()).__name__ for m in TRANSPORT])
def test_a_transport_failure_resends_the_same_messages(make: Callable[[], BaseException]) -> None:
    chat, _, out, rec = run([make(), reply(GOOD, ms=7.5, tokens=None)])
    assert chat.sent == [first(USER), first(USER)]
    assert (rec["label"], rec["attempts"], rec["error"]) == ("supported", 2, None)
    assert (rec["ms"], rec["tokens"]) == (7.5, None)
    assert out == [NEUTRAL, ENTAIL]


def test_a_mix_of_failures_gives_error_named_by_the_last() -> None:
    steps: list[dict[str, Any] | BaseException] = [
        TimeoutError("slow"),
        reply(BAD, ms=4.0, tokens=3),
        urllib.error.URLError("down"),
    ]
    chat, _, out, rec = run(steps)
    assert chat.sent == [first(USER), first(USER), retry(USER, BAD)]
    assert set(rec) == RECORD_KEYS
    assert (rec["label"], rec["passage"], rec["attempts"], rec["error"]) == (
        "error",
        0,
        3,
        "URLError",
    )
    assert (rec["ms"], rec["tokens"]) == (4.0, 3)
    assert out == [NEUTRAL, NEUTRAL]


def test_three_transport_failures_give_error() -> None:
    chat, _, out, rec = run([urllib.error.URLError("a"), TimeoutError("b"), OSError("c")])
    assert chat.sent == [first(USER)] * 3
    assert (rec["label"], rec["passage"], rec["attempts"], rec["error"]) == (
        "error",
        0,
        3,
        "OSError",
    )
    assert rec["ms"] == 0.0
    assert rec["tokens"] is None
    assert out == [NEUTRAL, NEUTRAL]


# Reply dicts a hand-written chat may return that are not ``{"content", "ms", "tokens", ...}``.
MALFORMED_REPLIES: dict[str, Any] = {
    "None": None,
    "a list": [GOOD],
    "no content": {"ms": 1.0, "tokens": 1},
    "content a number": {"content": 5, "ms": 1.0, "tokens": 1},
    "content zero": {"content": 0, "ms": 1.0, "tokens": 1},
    "content a dict": {"content": {"label": "supported"}, "ms": 1.0, "tokens": 1},
    "ms not a number": {"content": GOOD, "ms": "slow", "tokens": 1},
    "ms a list": {"content": GOOD, "ms": [1.0], "tokens": 1},
    "tokens not a number": {"content": GOOD, "ms": 1.0, "tokens": "many"},
}


@pytest.mark.parametrize("bad", MALFORMED_REPLIES.values(), ids=MALFORMED_REPLIES.keys())
def test_a_malformed_reply_dict_counts_as_a_failed_attempt(bad: Any) -> None:
    chat, _, out, rec = run([bad, reply(GOOD, ms=7.5, tokens=2)])
    assert chat.sent == [first(USER), first(USER)]
    assert (rec["label"], rec["attempts"], rec["error"]) == ("supported", 2, None)
    assert (rec["ms"], rec["tokens"]) == (7.5, 2)
    assert out == [NEUTRAL, ENTAIL]


def test_three_malformed_reply_dicts_give_error() -> None:
    steps: list[Any] = [{"ms": 1.0}, None, {"content": 5}]
    _, _, out, rec = run(steps)
    assert (rec["label"], rec["attempts"], rec["error"]) == ("error", 3, "TypeError")
    assert (rec["ms"], rec["tokens"]) == (0.0, None)
    assert out == [NEUTRAL, NEUTRAL]


@pytest.mark.parametrize("ms", ["missing", None])
def test_a_reply_without_ms_counts_zero_ms(ms: Any) -> None:
    out: dict[str, Any] = {"content": GOOD, "tokens": 3}
    if ms != "missing":
        out["ms"] = ms
    _, _, _, rec = run([out])
    assert (rec["label"], rec["attempts"], rec["ms"], rec["tokens"]) == ("supported", 1, 0.0, 3)


def test_the_error_is_the_class_name_not_the_message() -> None:
    _, _, _, rec = run([urllib.error.URLError("secret-ish detail")])
    assert rec["error"] == "URLError"
