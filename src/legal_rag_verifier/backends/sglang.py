"""SGLang backend (M4): the KV cache lives in the server's radix tree, not in this process.

Request-per-sentence maps directly onto SGLang's native ``/generate``: every call resubmits
``committed`` as ``input_ids`` and RadixAttention serves the shared prefix from cache, so a rollback
is simply not resubmitting the rejected tokens. ``meta_info.cached_tokens`` of the first request
is recorded as ``prefix_cache_hit_tokens``, the evidence that the committed prefix was not
re-prefilled.

Constraints are applied one token per request through a server-side logit mask
(:mod:`legal_rag_verifier.backends._sglang_mask`; the server needs
``--enable-custom-logit-processor``), with the same semantics as the HF backend; the free
continuation after the span is one plain request with the stop strings. Greedy (temperature 0).
The client is stdlib HTTP; the tokenizer is the model's Hugging Face tokenizer.
"""

from __future__ import annotations

import json
import time
import urllib.request
from collections.abc import Callable, Sequence
from typing import Any, Literal

from legal_rag_verifier.backends._tokenizer import TokenizerMixin
from legal_rag_verifier.engine import Allow, Ban, Constraint, Segment

__all__ = ["SGLangBackend"]

Post = Callable[[dict[str, Any]], dict[str, Any]]


class SGLangBackend(TokenizerMixin):
    """Drives a running SGLang server (``python -m sglang.launch_server …``)."""

    name = "sglang"

    def __init__(
        self,
        url: str,
        tokenizer: Any,
        *,
        model_id: str,
        eos: Sequence[int],
        post: Post | None = None,
        processor: str | None = None,
        timeout: float = 300.0,
    ) -> None:
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"not an http(s) URL: {url!r}")
        self.url = url.rstrip("/")
        self.tokenizer = tokenizer
        self.model_id = model_id
        self.eos: frozenset[int] = frozenset(eos)
        self.timeout = timeout
        self._post = post or self._http
        self._processor = processor

    @classmethod
    def connect(cls, url: str, model_path: str, *, revision: str | None = None) -> SGLangBackend:
        """Attach to a server serving ``model_path``; the tokenizer is loaded locally."""
        from transformers import AutoTokenizer, GenerationConfig  # noqa: PLC0415

        tokenizer = AutoTokenizer.from_pretrained(model_path, revision=revision)
        eos: Any = GenerationConfig.from_pretrained(
            model_path, revision=revision or "main"
        ).eos_token_id
        eos = eos if isinstance(eos, list) else [eos if eos is not None else tokenizer.eos_token_id]
        info = json.loads(_get(f"{url.rstrip('/')}/get_model_info"))
        served = str(info.get("model_path", model_path))
        return cls(url, tokenizer, model_id=f"{served}@{revision or 'main'}", eos=eos)

    # ------------------------------------------------------------------ HTTP
    def _http(self, body: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(  # noqa: S310 - http(s) checked in __init__
            f"{self.url}/generate",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
            out: dict[str, Any] = json.loads(response.read())
        return out

    def processor(self) -> str:
        if self._processor is None:
            from legal_rag_verifier.backends._sglang_mask import MaskProcessor  # noqa: PLC0415

            self._processor = str(MaskProcessor().to_str())
        return self._processor

    def generate(
        self,
        input_ids: Sequence[int],
        max_new: int,
        *,
        stop: Sequence[str] = (),
        mask: dict[str, list[int]] | None = None,
    ) -> dict[str, Any]:
        """One greedy ``/generate`` request."""
        params: dict[str, Any] = {
            "temperature": 0.0,
            "max_new_tokens": max_new,
            "stop": list(stop),
            "no_stop_trim": True,
            "skip_special_tokens": False,
        }
        body: dict[str, Any] = {"input_ids": list(input_ids), "sampling_params": params}
        if mask:
            params["custom_params"] = mask
            body["custom_logit_processor"] = self.processor()
        return self._post(body)

    def flush_cache(self) -> None:
        """Empty the server's radix cache (for cold-prefill measurements)."""
        url = f"{self.url}/flush_cache"
        request = urllib.request.Request(url, data=b"", method="POST")  # noqa: S310
        with urllib.request.urlopen(request, timeout=self.timeout):  # noqa: S310
            pass

    # ------------------------------------------------------------------ decoding
    def extend(
        self,
        committed: Sequence[int],
        *,
        stop: Sequence[str],
        max_new: int,
        constraint: Constraint | None,
    ) -> Segment:
        t0 = time.perf_counter_ns()
        generated: list[int] = []
        hit: int | None = None
        span_open = isinstance(constraint, Allow)
        while constraint is not None and len(generated) < max_new:
            mask = _mask(constraint, generated, span_open=span_open)
            if mask is None:
                break
            reply = self.generate([*committed, *generated], 1, mask=mask)
            hit = _cached(reply) if hit is None else hit
            token = int(reply["output_ids"][0])
            if isinstance(constraint, Allow):
                span_open = constraint.next_tokens([*generated, token]) is not None
            if token in self.eos:
                return self._segment(generated, "eos", hit, t0)
            generated.append(token)
            if not span_open and any(s in self.decode([token]) for s in stop):
                return self._segment(generated, "stop", hit, t0)
        if len(generated) >= max_new:
            return self._segment(generated, "length", hit or 0, t0)
        reply = self.generate([*committed, *generated], max_new - len(generated), stop=stop)
        hit = _cached(reply) if hit is None else hit
        tokens = [int(t) for t in reply["output_ids"]]
        finish: Literal["stop", "length", "eos"] = "length"
        if tokens and tokens[-1] in self.eos:
            tokens, finish = tokens[:-1], "eos"
        elif reply["meta_info"].get("finish_reason", {}).get("type") == "stop":
            matched = reply["meta_info"]["finish_reason"].get("matched")
            finish = "eos" if isinstance(matched, int) and matched in self.eos else "stop"
        return self._segment([*generated, *tokens], finish, hit, t0)

    def _segment(
        self, tokens: list[int], finish: Literal["stop", "length", "eos"], hit: int, t0: int
    ) -> Segment:
        return Segment(tuple(tokens), self.decode(tokens), finish, hit, time.perf_counter_ns() - t0)


def _mask(
    constraint: Constraint, generated: Sequence[int], *, span_open: bool
) -> dict[str, list[int]] | None:
    """The single-step mask for the next token, or ``None`` once the constraint no longer binds."""
    if isinstance(constraint, Ban):
        banned = constraint.banned(len(generated))
        return {"banned": sorted(banned)} if banned else None
    if not span_open:
        return None
    allowed = constraint.next_tokens(generated)
    return {"allowed": sorted(allowed)} if allowed is not None else None


def _cached(reply: dict[str, Any]) -> int:
    return int(reply.get("meta_info", {}).get("cached_tokens", 0))


def _get(url: str) -> str:
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310
        return str(response.read().decode())
