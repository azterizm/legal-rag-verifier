"""Grid cells 4B (in-flight rollback) and 4D (full retry) on Qwen 2.5 7B / SGLang, in the container.

Both cells use the same server, verifier (claim check + DeBERTa-v3-base on the same GPU, premise
enrichment attached) and prompt; the server's prefix cache is flushed before every answer so no
answer reuses another's cache.

``4B-inject`` (stop 27, the injection A/B) is 4B with ``steering="inject"``: on a rollback the
aligned windows are written into the context and the sentence is regenerated. Two ways to write
them were tried on the dev split before the test run: ``note`` (plain text in the answer stream,
the engine default) and ``turn`` (a user turn in Qwen's chat format, then a new assistant turn);
cells ``4B-inject-note`` / ``4B-inject-turn``. ``INJECT_STYLE`` is the one chosen there.
``4B-inject-v2`` (stop 30) uses the ``v2`` turn; its router gate is applied before this runs
(``grid_cells.gated``).
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
    DEFAULT_REFUSAL,
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
    # stop 30, injection v2: positive wording, the question restated, no rejected sentence
    "v2": (
        '<|im_end|>\n<|im_start|>user\nThe provision relevant to the question "{query}":\n'
        "{source}\n\nContinue your answer to the question from exactly where it stops."
        "<|im_end|>\n<|im_start|>assistant\n"
    ),
}
INJECT_STYLE = "turn"  # chosen on the dev pilot (docs/GRID.md, stop 27), before the test run

# stop 37, the software battery: the same prompts with legislation wording replaced (docs/GRID.md)
SOFTWARE_PROMPT = (
    "You answer questions about software using only the documentation below. State figures, "
    "defaults, version numbers and names exactly as the documentation gives them. If the "
    "documentation does not answer the question, say so. Answer in a few plain sentences, without "
    "headings or lists.\n\nDocumentation:\n{premise}"
)
SOFTWARE_REFUSAL = "I cannot state this point reliably from the documentation provided."
SOFTWARE_INJECT = {
    "v2": (
        '<|im_end|>\n<|im_start|>user\nThe documentation relevant to the question "{query}":\n'
        "{source}\n\nContinue your answer to the question from exactly where it stops."
        "<|im_end|>\n<|im_start|>assistant\n"
    ),
}


class QwenCells:
    def __init__(self, url: str, model_path: str, revision: str, domain: str = "legal") -> None:
        from legal_rag_verifier.nli import SentenceNLIVerifier  # noqa: PLC0415

        self.backend = SGLangBackend.connect(url, model_path, revision=revision)
        self.verifier = Verifier(
            SentenceNLIVerifier("cross-encoder/nli-deberta-v3-base", "cuda", local_files_only=False)
        )
        if domain == "software":
            self.system_prompt, refusal, templates = (
                SOFTWARE_PROMPT,
                SOFTWARE_REFUSAL,
                SOFTWARE_INJECT,
            )
        elif domain == "legal":
            self.system_prompt, refusal, templates = SYSTEM_PROMPT, DEFAULT_REFUSAL, INJECT
        else:
            raise ValueError(domain)
        self.engine = InFlightGenerator(
            self.backend,
            self.verifier,
            max_new_tokens=MAX_NEW_TOKENS,
            system_prompt=self.system_prompt,
            refusal=refusal,
        )
        self.inject = {
            style: InFlightGenerator(
                self.backend,
                self.verifier,
                max_new_tokens=MAX_NEW_TOKENS,
                steering="inject",
                inject_template=template,
                system_prompt=self.system_prompt,
                refusal=refusal,
            )
            for style, template in templates.items()
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
            record = full_retry(self.chat, self.verifier, query, premise, self.system_prompt)
        else:
            raise ValueError(cell)
        return record
