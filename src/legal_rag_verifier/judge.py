"""An LLM judge as the verifier's entailment check (stop 77, ``docs/GRID.md``).

The judge replaces the NLI head: each sentence the claim check sends on goes to a chat model with
the candidate passages, numbered, and the answer so far (to resolve references only), and the
reply ``supported``, ``contradicted`` or ``not_stated`` becomes one-hot entailment output.

The measured configuration is ``PRESETS["qwen27-ar4"]``: Qwen3.8 27B at 4 bits on SGLang, thinking
off, the short reply of stop 61, ``STRICT_FIGURES``, post-hoc prefix = every earlier sentence. It
scored 93.8 % (332/354) and 90.1 % (136/151) on the two fresh tests (stop 61) and ran in the live
loop at stop 65. Limits:

- any other model, sampling, prompt or config is unmeasured;
- with the source in the generator's prompt, the judge scored below no auditor (88.9 % vs 94.4 %,
  72 sentences, stop 73);
- a judge that cannot be reached scores every sentence not stated, so ``STRICT_FIGURES`` rolls
  back every sentence.

``OpenAIChat`` is a stdlib client for any OpenAI-compatible ``/v1/chat/completions`` endpoint. The
API key is read from the environment at call time; it is never stored, logged or recorded.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from legal_rag_verifier.premise import Premise
from legal_rag_verifier.segmenter import split_sentences
from legal_rag_verifier.verifier import (
    NLIProbs,
    SentenceVerdict,
    Verifier,
    VerifierConfig,
    _shift,
)

__all__ = [
    "CLOSE_THINK",
    "LABELS",
    "PRESETS",
    "PROMPT_SHA",
    "RETRY",
    "SHORT_REPLY",
    "SHORT_SHA",
    "STRICT_FIGURES",
    "SYSTEM",
    "USER",
    "Chat",
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
]

# ---------------------------------------------------------------------- the prompt (stops 42, 61)

LABELS = ("supported", "contradicted", "not_stated")

SYSTEM = (
    "You check whether a sentence is supported by source passages. Use only the passages, not "
    "your own knowledge. Reply with a single JSON object."
)
USER = """Passages:
{passages}

Answer so far. Use it only to work out what words such as "it" or "this" refer to. It is not \
evidence.
<<<
{prefix}
>>>

Sentence to check:
<<<
{sentence}
>>>

Labels:
- "supported": a passage states the sentence, or the sentence follows from the passages by \
reasoning, such as applying a default, substituting a definition, following a reference to another \
passage, converting units or doing arithmetic.
- "contradicted": the passages state or imply something incompatible with the sentence, such as a \
different figure, condition, scope or outcome.
- "not_stated": neither. Use this when the sentence may be true but the passages do not establish \
it.

Return JSON with keys "label" (one of the three), "passage" (the number of the passage that \
decides it, or 0) and "reason" (one sentence)."""

# Stop 61: the same prompt asking for no reason. Only its last sentence differs.
SHORT_REPLY = (
    'Return JSON with keys "label" (one of the three) and "passage" (the number of the passage '
    "that decides it, or 0). Give no reason."
)

#: Sent after a reply that does not parse. It names "reason" in short mode too, as measured.
RETRY = "Reply with ONLY the JSON object, with keys label, passage and reason."

#: sha256 of the stop 42 template (``SYSTEM + USER``).
PROMPT_SHA = hashlib.sha256((SYSTEM + USER).encode()).hexdigest()
_REPLY = USER[USER.index("Return JSON") :]
#: sha256 of the stop 61 template: ``USER`` with its reply sentence replaced by ``SHORT_REPLY``.
SHORT_SHA = hashlib.sha256((SYSTEM + USER.replace(_REPLY, SHORT_REPLY)).encode()).hexdigest()

_MEASURED_PROMPT_SHA = "72ce7d0514311749ccdd1d9f4430f5beea7d8757eeb9bd73be16fe9eae0e437b"
_MEASURED_SHORT_SHA = "7748f874db902456700c3ff64c1b4e37621e951ed0c3c65495b8b3c5911be149"
if (PROMPT_SHA, SHORT_SHA) != (_MEASURED_PROMPT_SHA, _MEASURED_SHORT_SHA):  # pragma: no cover
    raise RuntimeError("the judge prompt differs from the measured one")

#: A closing think tag, including K2's ``</ifm|think>``.
CLOSE_THINK = re.compile(r"</(?:ifm\|)?think[a-z_]*>")

#: The measured verifier config: strict, and a figure the claim check cannot find goes to the judge.
STRICT_FIGURES = VerifierConfig(
    neutral_policy="strict", neutral_with_grounded_claim="rollback", ungrounded_figure="judge"
)


def user_prompt(sentence: str, candidates: Sequence[str], prefix: str) -> str:
    """The stop 42 prompt: passages as ``[n] text``, ``(none)`` for an empty answer so far."""
    passages = "\n\n".join(f"[{n}] {text}" for n, text in enumerate(candidates, 1))
    return USER.format(passages=passages, prefix=prefix or "(none)", sentence=sentence)


def short_prompt(sentence: str, candidates: Sequence[str], prefix: str) -> str:
    """The stop 61 prompt: :func:`user_prompt` with its reply sentence replaced."""
    head, _ = user_prompt(sentence, candidates, prefix).rsplit("Return JSON", 1)
    return head + SHORT_REPLY


def prompt_key(user: str) -> str:
    """The key a recorded label is stored under: sha256 of ``SYSTEM + "\\n" + user``."""
    return hashlib.sha256(f"{SYSTEM}\n{user}".encode()).hexdigest()


def extract_json(text: str) -> dict[str, Any]:
    """The first ``{`` to the last ``}`` of ``text``, code fences removed, as a dict."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in output")
    parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("not a JSON object")  # noqa: TRY004
    return parsed


def parse_reply(text: str) -> dict[str, Any]:
    """A judge reply as ``{label, passage, reason}``; ValueError when it is not one."""
    reply = extract_json(text)
    label = str(reply.get("label", "")).strip().lower().replace(" ", "_")
    if label not in LABELS:
        raise ValueError(f"label {label!r}")
    try:
        passage = int(reply.get("passage") or 0)
    except (TypeError, ValueError):
        passage = 0
    return {"label": label, "passage": passage, "reason": str(reply.get("reason", ""))}


def one_hot(label: str, passage: int, n: int) -> list[NLIProbs]:
    """A judge label as entailment-model output over ``n`` candidates. Supported: entailment 1
    on its passage; contradicted: contradiction 1 there; otherwise neutral 1 everywhere. A
    passage number out of range applies the label to every candidate."""
    neutral = NLIProbs(0.0, 1.0, 0.0)
    if label == "supported":
        hit = NLIProbs(1.0, 0.0, 0.0)
    elif label == "contradicted":
        hit = NLIProbs(0.0, 0.0, 1.0)
    else:
        return [neutral] * n
    if not 1 <= passage <= n:
        return [hit] * n
    return [hit if i == passage - 1 else neutral for i in range(n)]


# ---------------------------------------------------------------------- the client

#: A chat call: messages in, ``{"content", "ms", "tokens", "finish"}`` out.
Chat = Callable[[list[dict[str, str]]], Mapping[str, Any]]

#: What a chat call may raise that counts as a failed attempt (transport or body).
_TRANSPORT: tuple[type[BaseException], ...] = (
    urllib.error.URLError,
    TimeoutError,
    OSError,
    http.client.HTTPException,
    ValueError,
    KeyError,
    IndexError,
)


class OpenAIChat:
    """One POST per call to ``{base_url}/v1/chat/completions`` (OpenAI-compatible, e.g. SGLang).

    The body is ``model``, the messages, ``sampling`` spread at the top level and
    ``chat_template_kwargs``; assistant turns carry ``"reasoning_content": ""``. When
    ``api_key_env`` names a variable that is set and non-empty at call time, its value is sent as
    ``Authorization: Bearer``; the value is never stored. No retry: :class:`Judge` retries.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        api_key_env: str | None = None,
        sampling: Mapping[str, Any] | None = None,
        template_kwargs: Mapping[str, Any] | None = None,
        timeout: float = 1800.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key_env = api_key_env
        self.sampling: dict[str, Any] = dict(sampling or {})
        self.template_kwargs: dict[str, Any] = dict(template_kwargs or {})
        self.timeout = timeout

    def __repr__(self) -> str:
        return (
            f"OpenAIChat(base_url={self.base_url!r}, model={self.model!r}, "
            f"api_key_env={self.api_key_env!r})"
        )

    def __call__(self, messages: Sequence[Mapping[str, str]]) -> dict[str, Any]:
        sent = [
            {**m, "reasoning_content": ""} if m["role"] == "assistant" else dict(m)
            for m in messages
        ]
        body = {
            "model": self.model,
            "messages": sent,
            **self.sampling,
            "chat_template_kwargs": dict(self.template_kwargs),
        }
        headers = {"Content-Type": "application/json"}
        key = os.environ.get(self.api_key_env) if self.api_key_env else None
        if key:
            headers["Authorization"] = f"Bearer {key}"
        request = urllib.request.Request(  # noqa: S310 - the caller's endpoint
            f"{self.base_url}/v1/chat/completions",
            data=json.dumps(body).encode(),
            method="POST",
            headers=headers,
        )
        t0 = time.perf_counter()
        with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
            out = json.loads(response.read())
        ms = (time.perf_counter() - t0) * 1000
        choice = out["choices"][0]
        message = choice["message"]
        content = message.get("content") or ""
        reasoning = message.get("reasoning_content") or ""
        if not content.strip() and CLOSE_THINK.search(reasoning):
            # The reasoning parser left the answer inside the reasoning: take what follows the
            # last closing tag.
            content = CLOSE_THINK.split(reasoning)[-1]
        return {
            "content": content,
            "ms": ms,
            "tokens": out.get("usage", {}).get("completion_tokens"),
            "finish": choice.get("finish_reason"),
        }


# ---------------------------------------------------------------------- the judge


class Judge:
    """The judge as an :class:`~legal_rag_verifier.verifier.NLIScorer`: one call per sentence.

    ``prefix`` is the answer so far and ``sentence`` the sentence's index; :class:`JudgedVerifier`
    sets both. At most 3 attempts in all: a transport failure re-sends the same messages, a reply
    that does not parse is re-asked with ``RETRY``. After 3 failures the label is ``"error"``,
    scored not stated. ``calls`` holds one record per :meth:`score`.
    """

    def __init__(self, chat: Chat, *, reply: Literal["short", "full"] = "short") -> None:
        if reply not in {"short", "full"}:
            raise ValueError(f"reply must be 'short' or 'full', not {reply!r}")
        self.chat = chat
        self.reply = reply
        model = getattr(chat, "model", None)
        self.model_id: str = str(model) if model is not None else "unknown"
        self.prefix = ""
        self.sentence: int | None = None
        self.preset: str | None = None
        self.calls: list[dict[str, Any]] = []

    def __repr__(self) -> str:
        return f"Judge(chat={self.chat!r}, reply={self.reply!r}, preset={self.preset!r})"

    @classmethod
    def from_preset(cls, name: str, base_url: str, *, api_key_env: str | None = None) -> Judge:
        """The measured judge ``PRESETS[name]`` on the server at ``base_url``."""
        preset = PRESETS[name]
        chat = OpenAIChat(
            base_url,
            preset.model,
            api_key_env=api_key_env,
            sampling=dict(preset.sampling),
            template_kwargs=dict(preset.template_kwargs),
        )
        judge = cls(chat, reply="short" if preset.reply == "short" else "full")
        judge.preset = name
        judge.model_id = f"{preset.model}@{preset.revision}"
        return judge

    def score(self, premises: Sequence[str], hypothesis: str) -> list[NLIProbs]:
        build = short_prompt if self.reply == "short" else user_prompt
        user = build(hypothesis, list(premises), self.prefix)
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
        label, passage, error = "error", 0, None
        ms, tokens, counted = 0.0, 0, False
        attempt = 0
        for attempt in range(1, 4):  # noqa: B007 - the attempts used are recorded
            try:
                reply = self.chat(messages)
            except _TRANSPORT as exc:
                if isinstance(exc, urllib.error.HTTPError):
                    exc.close()
                error = type(exc).__name__
                continue
            ms += float(reply["ms"])
            if reply.get("tokens") is not None:
                tokens += int(reply["tokens"])
                counted = True
            content = reply["content"] or ""
            try:
                parsed = parse_reply(content)
            except ValueError as exc:  # json.JSONDecodeError included
                error = type(exc).__name__
                messages = [
                    *messages[:2],
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": RETRY},
                ]
                continue
            label, passage, error = parsed["label"], parsed["passage"], None
            break
        self.calls.append(
            {
                "sha": prompt_key(user),
                "label": label,
                "passage": passage,
                "attempts": attempt,
                "ms": ms,
                "tokens": tokens if counted else None,
                "sentence": self.sentence,
                "preset": self.preset,
                "error": error,
            }
        )
        return one_hot(label if label in LABELS else "not_stated", passage, len(premises))


class JudgedVerifier(Verifier):
    """The verifier with a :class:`Judge` as its entailment check, telling it the answer so far.

    :meth:`check_text` (post-hoc) gives each sentence every earlier sentence of the text, rolled
    back or not, as measured at stop 61. :meth:`check_sentence` (the engine's path, live) gives it
    the sentences emitted so far; call :meth:`reset` between answers.
    """

    def __init__(self, judge: Judge, config: VerifierConfig = STRICT_FIGURES) -> None:
        super().__init__(judge, config)
        self.judge = judge
        self.committed: list[str] = []

    @property
    def calls(self) -> list[dict[str, Any]]:
        """The judge's call records since the last :meth:`reset`."""
        return self.judge.calls

    def reset(self) -> None:
        """Start a new answer: no emitted sentences, no call records, no prefix."""
        self.committed = []
        self.judge.calls = []
        self.judge.prefix = ""
        self.judge.sentence = None

    def check_text(
        self, premise: Premise, text: str, *, query: str | None = None
    ) -> list[SentenceVerdict]:
        """Post-hoc: a fresh call log; each sentence's prefix is all the sentences before it."""
        self.reset()
        out = []
        earlier: list[str] = []
        for i, sentence in enumerate(split_sentences(text)):
            self.judge.prefix = " ".join(earlier)
            self.judge.sentence = i
            verdict = Verifier.check_sentence(self, premise, sentence.text, query=query)
            out.append(_shift(verdict, sentence.start))
            earlier.append(sentence.text)
        return out

    def check_sentence(
        self, premise: Premise, sentence: str, *, query: str | None = None
    ) -> SentenceVerdict:
        """Live: the prefix is the emitted sentences; an emitted sentence joins them."""
        self.judge.prefix = " ".join(self.committed)
        self.judge.sentence = len(self.committed)
        verdict = super().check_sentence(premise, sentence, query=query)
        if verdict.emitted:
            self.committed.append(sentence)
        return verdict


# ---------------------------------------------------------------------- the measured preset


@dataclass(frozen=True)
class Preset:
    """A measured judge configuration, with the figure it scored and where it is recorded."""

    model: str
    revision: str
    quantisation: str
    server: str
    sampling: Mapping[str, float | int]
    template_kwargs: Mapping[str, bool | str]
    reply: str
    prompt_sha256: str
    figure: str
    measurements: str


PRESETS: dict[str, Preset] = {
    "qwen27-ar4": Preset(
        model="Vishva007/Qwen3.8-27B-W4A16-AutoRound-GPTQ",
        revision="1b9d56b428e9f841d7ad566f87660b5f47553c97",
        quantisation="W4A16 AutoRound (GPTQ format), SGLang's gptq_marlin kernel",
        server=(
            "SGLang 0.5.21 (lmsysorg/sglang:v0.5.21), --reasoning-parser qwen3 "
            "--context-length 65536 --mem-fraction-static 0.85, one L40S"
        ),
        sampling={
            "temperature": 0.7,
            "top_p": 0.8,
            "top_k": 20,
            "min_p": 0.0,
            "presence_penalty": 1.5,
            "max_tokens": 1024,
            "seed": 0,
        },
        template_kwargs={"enable_thinking": False},
        reply="short",
        prompt_sha256=SHORT_SHA,
        figure=(
            "93.8 % (332/354) and 90.1 % (136/151) on the two fresh tests, stop 61, under "
            "STRICT_FIGURES; with the source in the prompt 88.9 % vs 94.4 % for no auditor"
        ),
        measurements=(
            "docs/measurements.md"
            "#a-judge-reply-without-the-reason-stop-61-2026-10-12-method-in-docsgridmd"
        ),
    ),
}
