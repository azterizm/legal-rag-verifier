"""Grid cells 4B (in-flight rollback) and 4D (full retry) on Qwen 2.5 7B / SGLang, in the container.

Both cells use the same server, verifier (claim check + DeBERTa-v3-base on the same GPU, premise
enrichment attached) and prompt; the server's prefix cache is flushed before every answer so no
answer reuses another's cache.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from grid_cells import (  # type: ignore[import-not-found]  # noqa: E402
    Messages,
    Reply,
    full_retry,
    in_flight,
)

from legal_rag_verifier.backends.sglang import SGLangBackend  # noqa: E402
from legal_rag_verifier.engine import SYSTEM_PROMPT, InFlightGenerator  # noqa: E402
from legal_rag_verifier.premise import Premise  # noqa: E402
from legal_rag_verifier.verifier import Verifier  # noqa: E402

MAX_NEW_TOKENS = 512


class QwenCells:
    def __init__(self, url: str, model_path: str, revision: str) -> None:
        from legal_rag_verifier.nli import SentenceNLIVerifier  # noqa: PLC0415

        self.backend = SGLangBackend.connect(url, model_path, revision=revision)
        self.verifier = Verifier(
            SentenceNLIVerifier("cross-encoder/nli-deberta-v3-base", "cuda", local_files_only=False)
        )
        self.engine = InFlightGenerator(self.backend, self.verifier, max_new_tokens=MAX_NEW_TOKENS)

    def chat(self, messages: Messages) -> Reply:
        prompt = self.backend.chat(messages)
        segment = self.backend.extend(prompt, stop=(), max_new=MAX_NEW_TOKENS, constraint=None)
        return Reply(
            segment.text,
            len(segment.tokens),
            len(prompt),
            segment.latency_ns,
            segment.prefix_cache_hit_tokens,
        )

    def run(self, cell: str, query: str, premise: Premise) -> dict[str, Any]:
        self.backend.flush_cache()
        record: dict[str, Any]
        if cell == "4B":
            record = in_flight(self.engine, query, premise)
        elif cell == "4D":
            record = full_retry(self.chat, self.verifier, query, premise, SYSTEM_PROMPT)
        else:
            raise ValueError(cell)
        return record
