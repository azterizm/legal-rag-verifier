"""Stop 77: ``OpenAIChat`` and ``Judge`` over HTTP, against a fake server on 127.0.0.1.

The request must be the one ``scripts/auditor_judge.py`` ``server_chat`` sends (docs/GRID.md,
stop 77, "The measured configuration"); failures share ``Judge``'s one counter of 3 attempts; the
API key is sent as a header and appears nowhere else.
"""

from __future__ import annotations

import dataclasses
import http.server
import json
import logging
import threading
import traceback
import urllib.error
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, cast

import pytest

from legal_rag_verifier.judge import (
    PRESETS,
    RETRY,
    SYSTEM,
    Judge,
    JudgedVerifier,
    OpenAIChat,
    prompt_key,
    short_prompt,
)
from legal_rag_verifier.premise import Passage, Premise
from legal_rag_verifier.verifier import NLIProbs
from scripts.auditor_judge import server_chat

KEY_ENV = "X_TEST_KEY"
MODEL = "test/judge-model"
SAMPLING: dict[str, Any] = {
    "temperature": 0.7,
    "top_p": 0.8,
    "top_k": 20,
    "min_p": 0.0,
    "max_tokens": 64,
    "seed": 0,
}
TEMPLATE: dict[str, Any] = {"enable_thinking": False}
CONVERSATION = [
    {"role": "system", "content": "sys"},
    {"role": "user", "content": "first"},
    {"role": "assistant", "content": "not json"},
    {"role": "user", "content": "again"},
]
GOOD = '{"label": "supported", "passage": 1}'
TIMEOUT = 0.2  # the client's timeout in the failure tests
SLOW = 0.6  # the server's delay that outlasts it (cut short at teardown)
NEUTRAL = NLIProbs(0.0, 1.0, 0.0)
CANDIDATES = ["The divisor is N - ddof.", "By default ddof is zero."]
HYPOTHESIS = "numpy.std divides by N."
RECORD_KEYS = {"sha", "label", "passage", "attempts", "ms", "tokens", "sentence", "preset", "error"}
# As tests/test_auditor_judge.py: a sentence the claim check passes reaches the judge.
PREMISE = Premise(
    (
        Passage(
            "The divisor used in calculations is N - ddof. By default ddof is zero.",
            heading="numpy.std, parameter ddof",
        ),
    )
)


# ---------------------------------------------------------------------- the fake server


@dataclass(frozen=True)
class Reply:
    """One scripted response: a status with a JSON body, or a raw body, after an optional delay,
    with an optional ``Location`` header."""

    status: int = 200
    body: Any = None
    raw: bytes | None = None
    delay: float = 0.0
    location: str | None = None


@dataclass(frozen=True)
class Seen:
    path: str
    method: str
    headers: dict[str, str]  # names lower-cased
    body: dict[str, Any]


def completion(
    content: str | None = GOOD,
    *,
    reasoning: str | None = None,
    tokens: int | None = 5,
    finish: str | None = "stop",
) -> Reply:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if reasoning is not None:
        message["reasoning_content"] = reasoning
    body: dict[str, Any] = {"choices": [{"index": 0, "message": message, "finish_reason": finish}]}
    if tokens is not None:
        body["usage"] = {"prompt_tokens": 100, "completion_tokens": tokens}
    return Reply(body=body)


ERROR_500 = Reply(status=500, body={"error": {"message": "internal error"}})
TOO_SLOW = dataclasses.replace(completion(), delay=SLOW)
NOT_JSON = Reply(raw=b"<html>502 Bad Gateway</html>")
NO_CHOICES = Reply(body={"choices": [], "usage": {"completion_tokens": 0}})


class FakeHTTP:
    """An OpenAI-compatible endpoint on 127.0.0.1: records each request, replies from a queue
    (then ``default``)."""

    def __init__(self) -> None:
        self.queue: list[Reply] = []
        self.default = completion()
        self.requests: list[Seen] = []
        self.stop = threading.Event()
        self._lock = threading.Lock()
        self._server = _Server(("127.0.0.1", 0), _Handler)
        self._server.fake = self
        self.url = f"http://127.0.0.1:{self._server.server_port}"
        self._thread = threading.Thread(
            target=self._server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
        )
        self._thread.start()

    def script(self, *replies: Reply) -> None:
        with self._lock:
            self.queue.extend(replies)

    def take(self, seen: Seen) -> Reply:
        with self._lock:
            self.requests.append(seen)
            return self.queue.pop(0) if self.queue else self.default

    def close(self) -> None:
        self.stop.set()  # wakes a handler still delaying a reply
        self._server.shutdown()
        self._server.server_close()  # joins the handler threads
        self._thread.join()


class _Server(http.server.ThreadingHTTPServer):
    fake: FakeHTTP

    def handle_error(self, request: Any, client_address: Any) -> None:
        """A client that timed out has gone; there is nothing to report."""


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        """Recorded too: urllib's default redirect turns the POST into a GET."""
        self.do_POST()

    def do_POST(self) -> None:
        fake = cast(_Server, self.server).fake
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length)) if length else {}
        headers = {name.lower(): value for name, value in self.headers.items()}
        reply = fake.take(Seen(self.path, self.command, headers, body))
        if reply.delay and fake.stop.wait(reply.delay):
            return
        data = reply.raw if reply.raw is not None else json.dumps(reply.body).encode()
        try:
            self.send_response(reply.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            if reply.location is not None:
                self.send_header("Location", reply.location)
            self.end_headers()
            self.wfile.write(data)
        except OSError:
            return  # the client timed out and closed the connection

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Quiet: the tests read what was sent from ``FakeHTTP.requests``."""


@pytest.fixture
def server() -> Iterator[FakeHTTP]:
    fake = FakeHTTP()
    try:
        yield fake
    finally:
        fake.close()


@pytest.fixture
def secret(monkeypatch: pytest.MonkeyPatch) -> str:
    value = f"sk-test-{uuid.uuid4().hex}"
    monkeypatch.setenv(KEY_ENV, value)
    return value


def score_once(judge: Judge) -> list[NLIProbs]:
    return judge.score(CANDIDATES, HYPOTHESIS)


# ---------------------------------------------------------------------- the request


def test_one_post_to_chat_completions_as_json(server: FakeHTTP) -> None:
    chat = OpenAIChat(server.url + "/", MODEL, sampling=SAMPLING, template_kwargs=TEMPLATE)
    assert chat.base_url == server.url
    chat(CONVERSATION)
    (seen,) = server.requests
    assert seen.path == "/v1/chat/completions"
    assert seen.method == "POST"
    assert seen.headers["content-type"] == "application/json"


def test_body_spreads_sampling_and_template_and_marks_assistant_turns(server: FakeHTTP) -> None:
    chat = OpenAIChat(server.url, MODEL, sampling=SAMPLING, template_kwargs=TEMPLATE)
    chat(CONVERSATION)
    (seen,) = server.requests
    assert seen.body == {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "not json", "reasoning_content": ""},
            {"role": "user", "content": "again"},
        ],
        **SAMPLING,
        "chat_template_kwargs": TEMPLATE,
    }


def test_defaults_send_no_sampling_and_an_empty_template(server: FakeHTTP) -> None:
    chat = OpenAIChat(server.url, MODEL)
    assert (chat.model, chat.api_key_env, chat.sampling, chat.template_kwargs) == (
        MODEL,
        None,
        {},
        {},
    )
    assert chat.timeout == 1800.0
    chat(CONVERSATION[:2])
    assert server.requests[0].body == {
        "model": MODEL,
        "messages": CONVERSATION[:2],
        "chat_template_kwargs": {},
    }


def test_the_request_is_the_scripts_server_chat_request(server: FakeHTTP) -> None:
    ours = OpenAIChat(server.url, MODEL, sampling=SAMPLING, template_kwargs=TEMPLATE)(CONVERSATION)
    theirs = server_chat(server.url, MODEL, SAMPLING, TEMPLATE)(CONVERSATION)
    first, second = server.requests
    assert first.body == second.body
    assert first.path == second.path
    assert first.method == second.method
    assert first.headers["content-type"] == second.headers["content-type"]
    assert {k: v for k, v in ours.items() if k != "ms"} == {
        k: v for k, v in theirs.items() if k != "ms"
    }


@pytest.mark.parametrize("url", ["localhost:30000", "file:///x", "ftp://h"])
def test_a_url_that_is_not_http_is_refused(url: str) -> None:
    with pytest.raises(ValueError, match="not an http"):
        OpenAIChat(url, MODEL)


@pytest.mark.parametrize("url", ["http://127.0.0.1:30000", "https://judge.example/"])
def test_http_and_https_urls_are_accepted(url: str) -> None:
    assert OpenAIChat(url, MODEL).base_url == url.rstrip("/")


# ---------------------------------------------------------------------- the reply


def test_reply_gives_content_time_tokens_and_finish(server: FakeHTTP) -> None:
    server.script(completion("hello", tokens=7, finish="length"))
    out = OpenAIChat(server.url, MODEL)(CONVERSATION[:2])
    assert set(out) == {"content", "ms", "tokens", "finish"}
    assert (out["content"], out["tokens"], out["finish"]) == ("hello", 7, "length")
    assert isinstance(out["ms"], float)
    assert out["ms"] >= 0.0


def test_reply_without_usage_has_no_tokens(server: FakeHTTP) -> None:
    server.script(completion("hello", tokens=None))
    assert OpenAIChat(server.url, MODEL)(CONVERSATION[:2])["tokens"] is None


@pytest.mark.parametrize("content", ["", None])
@pytest.mark.parametrize("close", ["</think>", "</ifm|think>"])
def test_answer_left_in_reasoning_is_recovered(
    server: FakeHTTP, content: str | None, close: str
) -> None:
    reply = completion(content, reasoning=f"<think>passage 1 says so{close}{GOOD}")
    server.script(reply, reply)
    ours = OpenAIChat(server.url, MODEL)(CONVERSATION[:2])
    theirs = server_chat(server.url, MODEL, {}, {})(CONVERSATION[:2])
    assert ours["content"] == GOOD
    assert theirs["content"] == GOOD


# ---------------------------------------------------------------------- the key


def test_key_is_sent_as_a_bearer_header(server: FakeHTTP, secret: str) -> None:
    OpenAIChat(server.url, MODEL, api_key_env=KEY_ENV)(CONVERSATION[:2])
    assert server.requests[0].headers["authorization"] == f"Bearer {secret}"


def test_no_key_env_sends_no_header(server: FakeHTTP, secret: str) -> None:
    OpenAIChat(server.url, MODEL)(CONVERSATION[:2])
    assert "authorization" not in server.requests[0].headers


@pytest.mark.parametrize("value", [None, ""])
def test_unset_or_empty_key_sends_no_header_and_raises_nothing(
    server: FakeHTTP, monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv(KEY_ENV, raising=False)
    else:
        monkeypatch.setenv(KEY_ENV, value)
    out = OpenAIChat(server.url, MODEL, api_key_env=KEY_ENV)(CONVERSATION[:2])
    assert out["content"] == GOOD
    assert "authorization" not in server.requests[0].headers


def test_key_is_read_at_call_time(server: FakeHTTP, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(KEY_ENV, raising=False)
    chat = OpenAIChat(server.url, MODEL, api_key_env=KEY_ENV)
    chat(CONVERSATION[:2])
    value = f"sk-late-{uuid.uuid4().hex}"
    monkeypatch.setenv(KEY_ENV, value)
    chat(CONVERSATION[:2])
    before, after = server.requests
    assert "authorization" not in before.headers
    assert after.headers["authorization"] == f"Bearer {value}"


# ---------------------------------------------------------------------- secrets never leak


def exception_text(error: BaseException) -> str:
    return str(error) + repr(error) + "".join(traceback.format_exception(error))


def test_secret_absent_from_repr_and_str(server: FakeHTTP, secret: str) -> None:
    chat = OpenAIChat(server.url, MODEL, api_key_env=KEY_ENV)
    chat(CONVERSATION[:2])
    assert server.requests[0].headers["authorization"] == f"Bearer {secret}"
    assert secret not in repr(chat)
    assert secret not in str(chat)


def test_secret_absent_from_exception_on_http_500(server: FakeHTTP, secret: str) -> None:
    server.script(ERROR_500)
    chat = OpenAIChat(server.url, MODEL, api_key_env=KEY_ENV)
    with pytest.raises(urllib.error.HTTPError) as info:
        chat(CONVERSATION[:2])
    try:
        assert info.value.code == 500
        assert secret not in exception_text(info.value)
    finally:
        info.value.close()
    assert len(server.requests) == 1  # no retry inside OpenAIChat


def test_secret_absent_from_exception_on_timeout(server: FakeHTTP, secret: str) -> None:
    server.script(TOO_SLOW)
    chat = OpenAIChat(server.url, MODEL, api_key_env=KEY_ENV, timeout=TIMEOUT)
    with pytest.raises((TimeoutError, urllib.error.URLError)) as info:
        chat(CONVERSATION[:2])
    assert secret not in exception_text(info.value)
    assert len(server.requests) == 1


def test_secret_absent_from_judge_records_logs_and_output(
    server: FakeHTTP,
    secret: str,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    caplog.set_level(logging.DEBUG)
    server.script(ERROR_500, completion(), ERROR_500, NOT_JSON, TOO_SLOW)
    judge = Judge(OpenAIChat(server.url, MODEL, api_key_env=KEY_ENV, timeout=TIMEOUT))
    score_once(judge)  # a success after a failure
    score_once(judge)  # a give-up
    assert [c["label"] for c in judge.calls] == ["supported", "error"]
    assert all(s.headers["authorization"] == f"Bearer {secret}" for s in server.requests)
    assert secret not in repr(judge)
    assert secret not in json.dumps(judge.calls)
    assert secret not in caplog.text
    captured = capsys.readouterr()
    assert secret not in captured.out + captured.err


def test_secret_absent_from_judged_verdicts(server: FakeHTTP, secret: str) -> None:
    judge = Judge(OpenAIChat(server.url, MODEL, api_key_env=KEY_ENV))
    verdicts = JudgedVerifier(judge).check_text(PREMISE, HYPOTHESIS)
    assert server.requests, "the sentence reaches the judge"
    assert all(s.headers["authorization"] == f"Bearer {secret}" for s in server.requests)
    assert secret not in json.dumps([v.to_dict() for v in verdicts])
    assert secret not in json.dumps(judge.calls)


@pytest.mark.parametrize("tail", ["\n", "\r\n", " \t\n"])
def test_a_key_with_trailing_whitespace_is_stripped(
    server: FakeHTTP, monkeypatch: pytest.MonkeyPatch, tail: str
) -> None:
    value = f"sk-test-{uuid.uuid4().hex}"
    monkeypatch.setenv(KEY_ENV, value + tail)
    OpenAIChat(server.url, MODEL, api_key_env=KEY_ENV)(CONVERSATION[:2])
    assert server.requests[0].headers["authorization"] == f"Bearer {value}"


# A line break inside the value, control characters, a character beyond latin-1.
INVALID_TAILS = ["\r\nX: y", "\nX: y", "\rX", "\x1b", "\x7f", "\u20ac"]


@pytest.mark.parametrize("tail", INVALID_TAILS)
def test_an_invalid_key_is_refused_without_leaking_it(
    server: FakeHTTP, monkeypatch: pytest.MonkeyPatch, tail: str
) -> None:
    value = f"sk-test-{uuid.uuid4().hex}"
    monkeypatch.setenv(KEY_ENV, value + tail)
    chat = OpenAIChat(server.url, MODEL, api_key_env=KEY_ENV)
    with pytest.raises(ValueError, match=f"^{KEY_ENV} holds an invalid header value$") as info:
        chat(CONVERSATION[:2])
    assert value not in exception_text(info.value)
    assert info.value.__cause__ is None
    assert info.value.__context__ is None or info.value.__suppress_context__
    assert server.requests == []

    judge = Judge(chat)
    assert score_once(judge) == [NEUTRAL, NEUTRAL]
    (call,) = judge.calls
    assert (call["label"], call["attempts"], call["error"]) == ("error", 3, "ValueError")
    assert value not in json.dumps(judge.calls)
    assert value not in repr(judge)
    assert server.requests == []


@pytest.fixture
def elsewhere() -> Iterator[FakeHTTP]:
    """A second server, the target of a redirect."""
    fake = FakeHTTP()
    try:
        yield fake
    finally:
        fake.close()


def redirect(to: FakeHTTP, status: int = 302) -> Reply:
    return Reply(status=status, body={}, location=f"{to.url}/v1/chat/completions")


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_a_redirect_is_not_followed(
    server: FakeHTTP, elsewhere: FakeHTTP, secret: str, status: int
) -> None:
    server.script(redirect(elsewhere, status))
    chat = OpenAIChat(server.url, MODEL, api_key_env=KEY_ENV)
    with pytest.raises(urllib.error.HTTPError) as info:
        chat(CONVERSATION[:2])
    try:
        assert info.value.code == status
        assert secret not in exception_text(info.value)
    finally:
        info.value.close()
    assert len(server.requests) == 1
    assert elsewhere.requests == []  # the key never reaches the second server


def test_a_redirect_counts_as_a_failed_attempt(
    server: FakeHTTP, elsewhere: FakeHTTP, secret: str
) -> None:
    server.script(redirect(elsewhere), completion())
    judge = Judge(OpenAIChat(server.url, MODEL, api_key_env=KEY_ENV))
    score_once(judge)
    server.script(redirect(elsewhere), redirect(elsewhere), redirect(elsewhere))
    score_once(judge)
    assert [(c["label"], c["attempts"], c["error"]) for c in judge.calls] == [
        ("supported", 2, None),
        ("error", 3, "HTTPError"),
    ]
    assert len(server.requests) == 5
    assert elsewhere.requests == []


# ---------------------------------------------------------------------- failures as attempts


def test_http_500_then_good_takes_two_attempts(server: FakeHTTP) -> None:
    server.script(ERROR_500, completion(tokens=9))
    judge = Judge(OpenAIChat(server.url, MODEL))
    assert score_once(judge) == [NLIProbs(1.0, 0.0, 0.0), NEUTRAL]
    (call,) = judge.calls
    assert set(call) == RECORD_KEYS
    assert (call["label"], call["passage"], call["attempts"], call["error"]) == (
        "supported",
        1,
        2,
        None,
    )
    assert call["tokens"] == 9
    assert isinstance(call["ms"], float)
    first, second = server.requests
    assert first.body == second.body  # a transport failure re-sends the same messages
    assert call["sha"] == prompt_key(first.body["messages"][1]["content"])


def test_timeout_then_good_takes_two_attempts(server: FakeHTTP) -> None:
    server.script(TOO_SLOW, completion())
    judge = Judge(OpenAIChat(server.url, MODEL, timeout=TIMEOUT))
    score_once(judge)
    (call,) = judge.calls
    assert (call["label"], call["attempts"], call["error"]) == ("supported", 2, None)
    first, second = server.requests
    assert first.body == second.body


def test_three_500s_give_up_as_error(server: FakeHTTP) -> None:
    server.script(ERROR_500, ERROR_500, ERROR_500, completion())
    judge = Judge(OpenAIChat(server.url, MODEL))
    assert score_once(judge) == [NEUTRAL, NEUTRAL]
    (call,) = judge.calls
    assert set(call) == RECORD_KEYS
    assert (call["label"], call["passage"], call["attempts"], call["error"]) == (
        "error",
        0,
        3,
        "HTTPError",
    )
    assert call["tokens"] is None
    assert len(server.requests) == 3  # the fourth (good) reply is never asked for


def test_mixed_failures_give_up_after_three(server: FakeHTTP) -> None:
    server.script(NOT_JSON, TOO_SLOW, ERROR_500, completion())
    judge = Judge(OpenAIChat(server.url, MODEL, timeout=TIMEOUT))
    assert score_once(judge) == [NEUTRAL, NEUTRAL]
    (call,) = judge.calls
    assert (call["label"], call["attempts"], call["error"]) == ("error", 3, "HTTPError")
    assert len(server.requests) == 3
    assert all(s.body == server.requests[0].body for s in server.requests)


def test_empty_choices_then_good_takes_two_attempts(server: FakeHTTP) -> None:
    server.script(NO_CHOICES, completion())
    judge = Judge(OpenAIChat(server.url, MODEL))
    score_once(judge)
    (call,) = judge.calls
    assert (call["label"], call["attempts"], call["error"]) == ("supported", 2, None)
    assert len(server.requests) == 2


def choices(*items: Any, **extra: Any) -> Reply:
    return Reply(body={"choices": list(items), **extra})


GOOD_CHOICE = {
    "index": 0,
    "message": {"role": "assistant", "content": GOOD},
    "finish_reason": "stop",
}
MALFORMED = {
    "a JSON list": Reply(body=[1, 2]),
    "a JSON string": Reply(body="text"),
    "a JSON null": Reply(body=None),
    "choices null": Reply(body={"choices": None}),
    "choices an object": Reply(body={"choices": {"0": GOOD_CHOICE}}),
    "a choice not an object": choices("x"),
    "message null": choices({"index": 0, "message": None}),
    "message a string": choices({"index": 0, "message": GOOD}),
    "content a number": choices({"index": 0, "message": {"content": 5}}),
    "content a list": choices({"index": 0, "message": {"content": [GOOD]}}),
    "content false": choices({"index": 0, "message": {"content": False}}),
    "reasoning a number": choices(
        {"index": 0, "message": {"content": None, "reasoning_content": 5}}
    ),
    "usage a string": choices(GOOD_CHOICE, usage="x"),
    "tokens a string": choices(GOOD_CHOICE, usage={"completion_tokens": "many"}),
}


@pytest.mark.parametrize("body", MALFORMED.values(), ids=MALFORMED.keys())
def test_a_malformed_body_raises_value_error(server: FakeHTTP, body: Reply) -> None:
    server.script(body)
    with pytest.raises(ValueError):  # noqa: PT011 - the type is what Judge counts
        OpenAIChat(server.url, MODEL)(CONVERSATION[:2])


@pytest.mark.parametrize("body", MALFORMED.values(), ids=MALFORMED.keys())
def test_a_malformed_body_then_good_takes_two_attempts(server: FakeHTTP, body: Reply) -> None:
    server.script(body, completion())
    judge = Judge(OpenAIChat(server.url, MODEL))
    score_once(judge)
    (call,) = judge.calls
    assert (call["label"], call["attempts"], call["error"]) == ("supported", 2, None)
    assert len(server.requests) == 2


def test_null_usage_is_no_tokens(server: FakeHTTP) -> None:
    server.script(choices(GOOD_CHOICE, usage=None), choices(GOOD_CHOICE, usage=None))
    out = OpenAIChat(server.url, MODEL)(CONVERSATION[:2])
    assert (out["content"], out["tokens"], out["finish"]) == (GOOD, None, "stop")
    judge = Judge(OpenAIChat(server.url, MODEL))
    score_once(judge)
    (call,) = judge.calls
    assert (call["label"], call["attempts"], call["tokens"]) == ("supported", 1, None)


def test_transport_failure_and_bad_reply_share_one_counter(server: FakeHTTP) -> None:
    server.script(ERROR_500, completion("no json here"), completion())
    judge = Judge(OpenAIChat(server.url, MODEL))
    score_once(judge)
    (call,) = judge.calls
    assert (call["label"], call["attempts"]) == ("supported", 3)
    first, second, third = (s.body["messages"] for s in server.requests)
    assert first == second
    assert third == [
        *first,
        {"role": "assistant", "content": "no json here", "reasoning_content": ""},
        {"role": "user", "content": RETRY},
    ]


# ---------------------------------------------------------------------- the preset


def test_preset_sends_the_measured_configuration(server: FakeHTTP) -> None:
    # The values of scripts/modal_distill.py JUDGES["qwen27-ar4"], as literals: that module
    # imports modal at the top, which the dev environment does not install.
    model = "Vishva007/Qwen3.8-27B-W4A16-AutoRound-GPTQ"
    revision = "1b9d56b428e9f841d7ad566f87660b5f47553c97"
    sampling = {
        "temperature": 0.7,
        "top_p": 0.8,
        "top_k": 20,
        "min_p": 0.0,
        "presence_penalty": 1.5,
        "max_tokens": 1024,
        "seed": 0,
    }
    preset = PRESETS["qwen27-ar4"]
    assert (preset.model, preset.revision, preset.reply) == (model, revision, "short")
    assert dict(preset.sampling) == sampling
    assert dict(preset.template_kwargs) == {"enable_thinking": False}

    judge = Judge.from_preset("qwen27-ar4", server.url)
    assert judge.preset == "qwen27-ar4"
    assert judge.model_id == f"{model}@{revision}"
    score_once(judge)
    (seen,) = server.requests
    assert seen.path == "/v1/chat/completions"
    assert seen.body == {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": short_prompt(HYPOTHESIS, CANDIDATES, "")},
        ],
        **sampling,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    assert "authorization" not in seen.headers
    (call,) = judge.calls
    assert call["preset"] == "qwen27-ar4"
    assert call["sentence"] is None


def test_preset_with_a_key_env_sends_the_key(server: FakeHTTP, secret: str) -> None:
    judge = Judge.from_preset("qwen27-ar4", server.url, api_key_env=KEY_ENV)
    score_once(judge)
    assert server.requests[0].headers["authorization"] == f"Bearer {secret}"
    assert secret not in repr(judge)
    assert secret not in json.dumps(judge.calls)
