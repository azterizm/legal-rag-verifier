"""SGLang client against a fake ``/generate`` (no server, no GPU): same engine outcomes as HF."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from legal_rag_verifier.backends.sglang import SGLangBackend
from legal_rag_verifier.engine import Allow, Ban, InFlightGenerator
from legal_rag_verifier.premise import Premise
from legal_rag_verifier.verifier import Verifier

EOS = 3
PROMPT = "Q>"
PREMISE = Premise.from_text(
    "The limit of a compensatory award is £123,543.",
    titles=("Employment Rights Act 1996",),
)


class CharTokenizer:
    chat_template = None

    def __call__(self, text: str, *, add_special_tokens: bool = False) -> dict[str, list[int]]:
        return {"input_ids": [ord(c) for c in text]}

    def decode(self, ids: list[int], *, skip_special_tokens: bool = True) -> str:
        return "".join(chr(i) for i in ids if i != EOS)


class FakeServer:
    """Greedy "model": continue the first script that extends the text; radix-style cache."""

    def __init__(self, scripts: Sequence[str]) -> None:
        self.scripts = list(scripts)
        self.seen: list[list[int]] = []
        self.requests: list[dict[str, Any]] = []

    def __call__(self, body: dict[str, Any]) -> dict[str, Any]:
        self.requests.append(body)
        ids: list[int] = body["input_ids"]
        params = body["sampling_params"]
        cached = max((_shared(ids, s) for s in self.seen), default=0)
        cached = min(cached, len(ids) - 1)
        mask = params.get("custom_params") or {}
        assert ("custom_logit_processor" in body) == bool(mask)
        out: list[int] = []
        finish: dict[str, Any] = {"type": "length"}
        while len(out) < params["max_new_tokens"]:
            text = "".join(chr(i) for i in [*ids, *out])[len(PROMPT) :]
            token = self._choose(text, mask if not out else {})
            out.append(token)
            if token == EOS:
                finish = {"type": "stop", "matched": EOS}
                break
            if chr(token) in params["stop"]:
                finish = {"type": "stop", "matched": chr(token)}
                break
        self.seen.append([*ids, *out])
        return {"output_ids": out, "meta_info": {"cached_tokens": cached, "finish_reason": finish}}

    def _choose(self, text: str, mask: dict[str, list[int]]) -> int:
        allowed, banned = mask.get("allowed"), set(mask.get("banned", []))
        for script in self.scripts:
            if not script.startswith(text):
                continue
            token = ord(script[len(text)]) if len(script) > len(text) else EOS
            if token in banned or (allowed is not None and token not in allowed):
                continue
            return token
        return min(allowed) if allowed else EOS


def _shared(a: Sequence[int], b: Sequence[int]) -> int:
    n = 0
    for x, y in zip(a, b, strict=False):
        if x != y:
            break
        n += 1
    return n


def backend(scripts: Sequence[str]) -> tuple[SGLangBackend, FakeServer]:
    server = FakeServer(scripts)
    client = SGLangBackend(
        "http://fake",
        CharTokenizer(),
        model_id="fake@0",
        eos=[EOS],
        post=server,
        processor="<processor>",
    )
    client.chat = lambda messages: client.encode(PROMPT)  # type: ignore[method-assign]
    return client, server


def test_allow_list_is_one_masked_request_per_token_then_a_plain_continuation() -> None:
    client, server = backend(["The limit is £85,000.", "The limit is £123,543."])
    answer = InFlightGenerator(client, Verifier()).generate_verified("cap?", PREMISE)
    assert answer.text == "The limit is £123,543."
    masked = [r for r in server.requests if r["sampling_params"].get("custom_params")]
    assert [r["sampling_params"]["custom_params"] for r in masked] == [
        {"allowed": [ord(c)]} for c in "£123,543"
    ]
    assert all(r["sampling_params"]["max_new_tokens"] == 1 for r in masked)
    resumed = answer.trace["sentences"][0]["attempts"][1]
    assert resumed["prefix_cache_hit_tokens"] >= len(PROMPT + "The limit is ") - 1


def test_ban_masks_only_the_first_step() -> None:
    client, server = backend(
        ["The limit is £85,000.", "A compensatory award is capped at £123,543."]
    )
    engine = InFlightGenerator(client, Verifier(), steering="ban")
    answer = engine.generate_verified("cap?", PREMISE)
    assert answer.text == "A compensatory award is capped at £123,543."
    masked = [r for r in server.requests if r["sampling_params"].get("custom_params")]
    assert [r["sampling_params"]["custom_params"] for r in masked] == [{"banned": [ord("T")]}]


def test_rollback_resubmits_the_committed_prefix_and_reports_the_cache_hit() -> None:
    client, _ = backend(["One. Two."])
    first = client.extend(client.encode(PROMPT), stop=(".",), max_new=20, constraint=None)
    assert first.text == "One."
    assert first.finish_reason == "stop"
    committed = (*client.encode(PROMPT), *first.tokens)
    again = client.extend(committed, stop=(".",), max_new=20, constraint=None)
    assert again.text == " Two."
    assert again.prefix_cache_hit_tokens == len(committed) - 1
    end = client.extend((*committed, *again.tokens), stop=(".",), max_new=20, constraint=None)
    assert end.finish_reason == "eos"
    assert end.tokens == ()


def test_constraint_span_ignores_stop_strings_and_lifts_when_complete() -> None:
    client, _ = backend(["Pay £1.5m now."])
    allow = Allow((client.encode("£1.5m"),))
    segment = client.extend(
        client.encode(PROMPT + "Pay "), stop=(".",), max_new=20, constraint=allow
    )
    assert segment.text == "£1.5m now."
    banned = client.extend(
        client.encode(PROMPT), stop=(".",), max_new=1, constraint=Ban(frozenset({ord("P")}))
    )
    assert banned.finish_reason == "eos"  # no other script: the fake model ends
