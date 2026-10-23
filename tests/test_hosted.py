"""Stop 74: the two hosts in rotation (no network call)."""

from __future__ import annotations

import urllib.error
from typing import Any

import pytest

from scripts import hosted


def _send(fail: set[str], seen: list[str]) -> Any:
    def send(host: hosted.Host, messages: Any, *, temperature: float, timeout: float) -> Any:
        seen.append(host.name)
        if host.name in fail:
            raise urllib.error.URLError("down")
        return {"content": "{}", "usage": {}, "ms": 1.0, "provider": host.name}

    return send


def test_a_failure_rotates_to_the_other_host_and_stays_there() -> None:
    seen: list[str] = []
    r = hosted.Rotation(send=_send({"groq"}, seen), sleep=lambda s: None)
    assert r.chat([])["provider"] == "cloudflare"
    assert r.chat([])["provider"] == "cloudflare"
    assert seen == ["groq", "cloudflare", "cloudflare"]
    assert r.failures == {"groq": 1, "cloudflare": 0}


def test_both_hosts_failing_backs_off_then_gives_up() -> None:
    seen: list[str] = []
    waits: list[float] = []
    r = hosted.Rotation(send=_send({"groq", "cloudflare"}, seen), sleep=waits.append)
    with pytest.raises(hosted.HostedError):
        r.chat([])
    assert len(seen) == 2 * hosted.ROUNDS
    assert len(waits) == hosted.ROUNDS


def test_next_moves_on_without_a_failure() -> None:
    r = hosted.Rotation(send=_send(set(), []), sleep=lambda s: None)
    r.next()
    assert r.chat([])["provider"] == "cloudflare"
    r.next()
    assert r.chat([])["provider"] == "groq"


def test_thinking_is_stripped() -> None:
    assert hosted.strip_thinking('<think>\nhm\n</think>\n\n{"label": 1}') == '{"label": 1}'
