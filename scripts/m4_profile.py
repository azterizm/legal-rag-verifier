"""Where the warm rollback round trip goes (step 2 after M4), run in the Modal container.

M4 measured a one-token request on a cached 759-token prefix at 122 ms warm vs 212 ms cold. This
splits it: HTTP + scheduler overhead (a GET that does no model work), the first token (an "extend"
forward over the one uncached token, which SGLang does not run under CUDA graphs) and each further
token (a graphed decode step), the cost of the server-side logit mask the allow/ban constraints
use, and a cold prefill. Fit: ``t(n) ≈ t(1) + (n - 1) · decode``.
"""

from __future__ import annotations

import statistics
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from live_demo import QUERIES, premise  # type: ignore[import-not-found]  # noqa: E402

from legal_rag_verifier.backends.sglang import SGLangBackend  # noqa: E402
from legal_rag_verifier.engine import InFlightGenerator  # noqa: E402
from legal_rag_verifier.verifier import Verifier  # noqa: E402

REPEATS = 7


def _ms(samples: list[int]) -> float:
    return round(statistics.median(samples) / 1e6, 2)


def _timed(fn: Any, repeats: int = REPEATS) -> tuple[float, Any]:
    samples, last = [], None
    for _ in range(repeats):
        t0 = time.perf_counter_ns()
        last = fn()
        samples.append(time.perf_counter_ns() - t0)
    return _ms(samples), last


def profile(url: str, model_path: str, revision: str) -> dict[str, Any]:
    backend = SGLangBackend.connect(url, model_path, revision=revision)
    messages = InFlightGenerator(backend, Verifier()).messages(QUERIES[0], premise())
    prompt = list(backend.chat(messages))
    backend.generate(prompt, 1)  # warm the prefix and the kernels

    def get_info() -> None:
        with urllib.request.urlopen(f"{url}/get_model_info", timeout=60) as r:  # noqa: S310
            r.read()

    http_ms, _ = _timed(get_info, 20)
    warm: dict[int, float] = {}
    meta: dict[str, Any] = {}
    for n in (1, 2, 4, 16, 64):
        warm[n], reply = _timed(lambda n=n: backend.generate(prompt, n))
        meta = reply["meta_info"]
    decode_ms = round((warm[64] - warm[16]) / 48, 2)
    token = int(backend.generate(prompt, 1)["output_ids"][0])
    allow_ms, _ = _timed(lambda: backend.generate(prompt, 1, mask={"allowed": [token]}))
    ban_ms, _ = _timed(lambda: backend.generate(prompt, 1, mask={"banned": [token]}))

    def cold() -> None:
        backend.flush_cache()
        backend.generate(prompt, 1)

    cold_ms, _ = _timed(cold)
    # A resubmit after a rollback: the prefix plus one new token, the rest cached.
    grown = [*prompt, token]
    backend.generate(grown, 1)
    resubmit_ms, reply = _timed(lambda: backend.generate(grown, 1))
    return {
        "prompt_tokens": len(prompt),
        "http_get_ms": http_ms,
        "warm_ms_by_max_new_tokens": warm,
        "first_token_ms": warm[1],
        "decode_ms_per_token": decode_ms,
        "decode_tok_s": round(1000 / decode_ms, 1) if decode_ms > 0 else None,
        "first_token_minus_decode_ms": round(warm[1] - decode_ms, 2),
        "masked_one_token_ms": {"allowed": allow_ms, "banned": ban_ms},
        "cold_one_token_ms": cold_ms,
        "resubmit_one_token_ms": resubmit_ms,
        "resubmit_cached_tokens": int(reply["meta_info"].get("cached_tokens", 0)),
        "meta_info_sample": {k: v for k, v in meta.items() if k != "output_token_logprobs"},
    }
