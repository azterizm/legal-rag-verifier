"""Qwen 3.8 27B on two hosts, Groq and Cloudflare Workers AI, in rotation (GRID § Stop 74).

A call goes to the current host; on any error (HTTP, timeout, an empty reply) it rotates to the
other and tries again. When both fail in turn it backs off, and after ``ROUNDS`` rounds it raises
``HostedError`` so a run stops cleanly. Only the one model name on each host is called; no listing
or probing. Keys come from ``GROQ_API_KEY`` and ``CLOUDFLARE_AI_WORKER_TOKEN``, the Cloudflare
account from ``CLOUDFLARE_ACCOUNT_ID``; none is written to the repository.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

ROUNDS = 6
BACKOFF = (5.0, 15.0, 30.0, 60.0, 120.0, 240.0)  # seconds after a round where both hosts failed
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


class HostedError(RuntimeError):
    """Every host failed for ``ROUNDS`` rounds."""


@dataclass(frozen=True)
class Host:
    name: str
    model: str
    url: Callable[[], str]
    key_env: str
    extra: Mapping[str, Any] = field(default_factory=dict)  # how this host turns thinking off


def _cloudflare_url() -> str:
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    if not account:
        raise HostedError("CLOUDFLARE_ACCOUNT_ID is not set")
    return f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1/chat/completions"


HOSTS = (
    Host(
        "groq",
        "qwen/qwen3.8-27b",
        lambda: "https://api.groq.com/openai/v1/chat/completions",
        "GROQ_API_KEY",
        {"reasoning_effort": "none"},
    ),
    Host(
        "cloudflare",
        "@cf/qwen/qwen3.8-27b",
        _cloudflare_url,
        "CLOUDFLARE_AI_WORKER_TOKEN",
        {"chat_template_kwargs": {"enable_thinking": False}},
    ),
)


def strip_thinking(text: str) -> str:
    return _THINK.sub("", text).strip()


def call(
    host: Host, messages: Sequence[Mapping[str, str]], *, temperature: float, timeout: float
) -> dict[str, Any]:
    """One request to one host: ``{content, usage, ms, provider}``. Raises on any failure."""
    key = os.environ.get(host.key_env, "")
    if not key:
        raise HostedError(f"{host.key_env} is not set")
    body = {"model": host.model, "messages": list(messages), "temperature": temperature}
    body |= host.extra
    request = urllib.request.Request(  # noqa: S310 - https only, fixed hosts
        host.url(),
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "User-Agent": "legal-rag-verifier/stop74",
        },
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        out = json.loads(response.read())
    message = out["choices"][0]["message"]
    content = strip_thinking(message.get("content") or "")
    if not content:
        raise ValueError(f"{host.name}: empty reply")
    ms = (time.perf_counter() - t0) * 1000
    return {"content": content, "usage": out.get("usage") or {}, "ms": ms, "provider": host.name}


class Rotation:
    """The current host, shared across threads; it moves on at every failure."""

    def __init__(
        self,
        hosts: Sequence[Host] = HOSTS,
        *,
        send: Callable[..., dict[str, Any]] = call,
        sleep: Callable[[float], None] = time.sleep,
        timeout: float = 120,
    ) -> None:
        self.hosts = tuple(hosts)
        self.send = send
        self.sleep = sleep
        self.timeout = timeout
        self.current = 0
        self.failures: dict[str, int] = {h.name: 0 for h in self.hosts}
        self._lock = threading.Lock()

    def next(self) -> None:
        """Move on from the current host (a reply with no valid label)."""
        self._rotate(self.current)

    def _rotate(self, failed: int) -> None:
        with self._lock:
            if self.current == failed:
                self.current = (failed + 1) % len(self.hosts)

    def chat(
        self, messages: Sequence[Mapping[str, str]], *, temperature: float = 0.0
    ) -> dict[str, Any]:
        last = ""
        for round_ in range(ROUNDS):
            for _ in self.hosts:
                i = self.current
                host = self.hosts[i]
                try:
                    return self.send(host, messages, temperature=temperature, timeout=self.timeout)
                except (
                    urllib.error.URLError,
                    TimeoutError,
                    ConnectionError,
                    ValueError,
                    KeyError,
                    IndexError,
                    HostedError,
                ) as exc:
                    last = f"{host.name}: {_describe(exc)}"
                    with self._lock:
                        self.failures[host.name] += 1
                    print(f"hosted {last}; rotating", file=sys.stderr, flush=True)
                    self._rotate(i)
            self.sleep(BACKOFF[min(round_, len(BACKOFF) - 1)])
        raise HostedError(f"every host failed for {ROUNDS} rounds (last: {last})")


def _describe(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        body = ""
        with contextlib.suppress(OSError):
            body = exc.read().decode("utf-8", "replace")[:200]
        return f"HTTP {exc.code} {body}".strip()
    return repr(exc)[:200]


def judge_chat(rotation: Rotation) -> Callable[[list[dict[str, str]]], dict[str, Any]]:
    """``aj.ask``'s chat: ``{content, ms, tokens, provider}`` at temperature 0."""

    def chat(messages: list[dict[str, str]]) -> dict[str, Any]:
        out = rotation.chat(messages)
        return {**out, "tokens": (out["usage"] or {}).get("completion_tokens")}

    return chat
