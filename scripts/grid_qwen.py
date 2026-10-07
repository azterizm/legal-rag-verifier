"""Grid cells 4B (in-flight rollback) and 4D (full retry) on Qwen 2.5 7B / SGLang, in the container.

Both cells use the same server, verifier (claim check + DeBERTa-v3-base on the same GPU, premise
enrichment attached) and prompt; the server's prefix cache is flushed before every answer so no
answer reuses another's cache.

``4B-inject`` (stop 27, the injection A/B) is 4B with ``steering="inject"``: on a rollback the
aligned windows are written into the context and the sentence is regenerated. Two ways to write
them were tried on the dev split before the test run: ``note`` (plain text in the answer stream,
the engine default) and ``turn`` (a user turn in Qwen's chat format, then a new assistant turn);
cells ``4B-inject-note`` / ``4B-inject-turn``. ``INJECT_STYLE`` is the one chosen there.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from grid_cells import (  # type: ignore[import-not-found]  # noqa: E402
    CONTINUE,
    Messages,
    Reply,
    full_retry,
    in_flight,
)

from legal_rag_verifier.backends.sglang import SGLangBackend  # noqa: E402
from legal_rag_verifier.engine import (  # noqa: E402
    INJECT_TEMPLATE,
    SYSTEM_PROMPT,
    InFlightGenerator,
)
from legal_rag_verifier.premise import Premise  # noqa: E402
from legal_rag_verifier.verifier import Verifier  # noqa: E402

MAX_NEW_TOKENS = 512
INJECT = {
    "note": INJECT_TEMPLATE,
    "turn": (
        "<|im_end|>\n<|im_start|>user\nThe provision for your next point:\n{source}\n\n"
        + CONTINUE
        + "<|im_end|>\n<|im_start|>assistant\n"
    ),
}
INJECT_STYLE = "turn"  # chosen on the dev pilot (docs/GRID.md, stop 27), before the test run


class QwenCells:
    def __init__(self, url: str, model_path: str, revision: str) -> None:
        from legal_rag_verifier.nli import SentenceNLIVerifier  # noqa: PLC0415

        self.backend = SGLangBackend.connect(url, model_path, revision=revision)
        self.verifier = Verifier(
            SentenceNLIVerifier("cross-encoder/nli-deberta-v3-base", "cuda", local_files_only=False)
        )
        self.engine = InFlightGenerator(self.backend, self.verifier, max_new_tokens=MAX_NEW_TOKENS)
        self.inject = {
            style: InFlightGenerator(
                self.backend,
                self.verifier,
                max_new_tokens=MAX_NEW_TOKENS,
                steering="inject",
                inject_template=template,
            )
            for style, template in INJECT.items()
        }

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
        elif cell.startswith("4B-inject"):
            style = cell.removeprefix("4B-inject").lstrip("-") or INJECT_STYLE
            if style not in self.inject:
                raise ValueError(f"no injection style chosen for {cell!r}")
            record = in_flight(self.inject[style], query, premise)
        elif cell == "4D":
            record = full_retry(self.chat, self.verifier, query, premise, SYSTEM_PROMPT)
        else:
            raise ValueError(cell)
        return record
