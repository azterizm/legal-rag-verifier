"""M4 spike, run inside the Modal container next to a local SGLang server (``modal_m4.py``).

Same premise, queries and injected failure as ``live_demo.py``, on Qwen 2.5 7B served by SGLang
(RadixAttention), plus the rollback round trip: resubmitting the committed prefix after a rollback
(prefix-cache hit) against a cold prefill of the same tokens (cache flushed).
"""

from __future__ import annotations

import importlib.metadata
import statistics
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from live_demo import (  # type: ignore[import-not-found]  # noqa: E402
    NLI_MODELS,
    QUERIES,
    premise,
    run_steering,
)

from legal_rag_verifier.backends.sglang import SGLangBackend  # noqa: E402
from legal_rag_verifier.engine import InFlightGenerator  # noqa: E402
from legal_rag_verifier.verifier import Verifier  # noqa: E402


def round_trip(backend: SGLangBackend, tokens: list[int], repeats: int = 5) -> dict[str, Any]:
    """One-token request on ``tokens``: cold (cache flushed) vs warm (prefix cached)."""
    cold, warm, hits = [], [], []
    for _ in range(repeats):
        backend.flush_cache()
        t0 = time.perf_counter_ns()
        backend.generate(tokens, 1)
        cold.append(time.perf_counter_ns() - t0)
        t0 = time.perf_counter_ns()
        reply = backend.generate(tokens, 1)
        warm.append(time.perf_counter_ns() - t0)
        hits.append(int(reply["meta_info"]["cached_tokens"]))
    return {
        "tokens": len(tokens),
        "cold_ms_median": round(statistics.median(cold) / 1e6, 1),
        "warm_ms_median": round(statistics.median(warm) / 1e6, 1),
        "warm_cached_tokens": hits,
    }


def run(url: str, model_path: str, revision: str, max_new_tokens: int = 200) -> dict[str, Any]:
    from legal_rag_verifier.nli import SentenceNLIVerifier  # noqa: PLC0415

    backend = SGLangBackend.connect(url, model_path, revision=revision)
    verifier = Verifier(SentenceNLIVerifier(NLI_MODELS["base"], "cuda", local_files_only=False))
    s124 = premise()
    prompt = backend.chat(InFlightGenerator(backend, verifier).messages(QUERIES[0], s124))
    timing = round_trip(backend, list(prompt))
    print("round trip:", timing, flush=True)
    runs = {
        steering: run_steering(backend, verifier, s124, steering, max_new_tokens=max_new_tokens)
        for steering in ("allow", "ban")
    }
    return {
        "generator": backend.model_id,
        "sglang": importlib.metadata.version("sglang"),
        "nli": verifier.nli.model_id if verifier.nli else None,
        "round_trip": timing,
        "runs": runs,
    }
