"""Stop 59: the LLM judge inside the in-flight loop (docs/GRID.md § Stop 59).

Runs in the container beside one SGLang server that serves both roles. The engine and the
verifier are the package's; this file only supplies the judge as the entailment scorer, the
answer so far for its prompt, and this model's chat format.
"""

from __future__ import annotations

import sys
import time
import urllib.error
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import auditor_judge as aj  # type: ignore[import-not-found]

from legal_rag_verifier.backends.sglang import SGLangBackend
from legal_rag_verifier.engine import (
    DEFAULT_REFUSAL,
    SYSTEM_PROMPT,
    InFlightGenerator,
    Tokens,
)
from legal_rag_verifier.premise import Premise
from legal_rag_verifier.verifier import NLIProbs, SentenceVerdict, Verifier

ARMS = ("source", "closed")
MAX_NEW_TOKENS = 512
# Stop 43's prompts (scripts/fresh_battery.py), repeated here so the container needs no battery.
SOFTWARE_PROMPT = (
    "You answer questions about software using only the documentation below. State figures, "
    "defaults, version numbers and names exactly as the documentation gives them. If the "
    "documentation does not answer the question, say so. Answer in a few plain sentences, without "
    "headings or lists.\n\nDocumentation:\n{premise}"
)
CLOSED = {
    "software": (
        "You answer questions about software. State figures, defaults, version numbers and names "
        "exactly. If you do not know the answer, say so. Answer in a few plain sentences, without "
        "headings or lists."
    ),
    "legal": (
        "You answer questions about legislation. State figures, dates, section numbers and the "
        "names of Acts exactly. If you do not know the answer, say so. Answer in a few plain "
        "sentences, without headings or lists."
    ),
}
PROMPTS = {"software": SOFTWARE_PROMPT, "legal": SYSTEM_PROMPT}
REFUSALS = {
    "software": "I cannot state this point reliably from the documentation provided.",
    "legal": DEFAULT_REFUSAL,
}
# Stop 30's injected turn (scripts/grid_qwen.py, "v2"), in Qwen3.8's chat format with thinking off.
_TURN = (
    '<|im_end|>\n<|im_start|>user\nThe {what} relevant to the question "{{query}}":\n'
    "{{source}}\n\nContinue your answer to the question from exactly where it stops."
    "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
)
INJECT = {
    "software": _TURN.format(what="documentation"),
    "legal": _TURN.format(what="provision"),
}

Chat = Callable[[list[dict[str, str]]], dict[str, Any]]


class ThinkingOff(SGLangBackend):
    """The engine's SGLang backend with the chat prompt rendered with thinking off."""

    def chat(self, messages: Sequence[Mapping[str, str]]) -> Tokens:
        encoded = self.tokenizer.apply_chat_template(
            [dict(m) for m in messages],
            add_generation_prompt=True,
            return_dict=True,
            enable_thinking=False,
        )
        return tuple(int(t) for t in encoded["input_ids"])


class LiveJudge:
    """The judge as the verifier's entailment scorer: one call per clause, the stop 42 prompt.
    ``prefix`` is the answer so far. A reply that never parses counts as not stated. ``reply``:
    ``"short"`` asks for no reason (stop 61, the default by your decision of 2026-10-12);
    ``"reason"`` is the prompt as stop 59 ran it."""

    def __init__(self, chat: Chat, model_id: str, reply: str = "short") -> None:
        if reply not in {"short", "reason"}:
            raise ValueError(reply)
        self.chat = chat
        self.model_id = model_id
        self.reply = reply
        self.prefix = ""
        self.calls: list[dict[str, Any]] = []

    def score(self, premises: Sequence[str], hypothesis: str) -> list[NLIProbs]:
        t0 = time.perf_counter()
        try:
            build = aj.short_prompt if self.reply == "short" else aj.user_prompt
            reply = aj.ask(self.chat, build(hypothesis, premises, self.prefix))
        except (urllib.error.URLError, TimeoutError, KeyError) as exc:
            reply = {"label": "error", "passage": 0, "reason": repr(exc), "attempts": 0}
        label = reply["label"] if reply["label"] in aj.LABELS else "not_stated"
        self.calls.append(
            {
                "label": reply["label"],
                "attempts": reply.get("attempts"),
                "tokens": reply.get("tokens"),
                "ms": round((time.perf_counter() - t0) * 1000),
            }
        )
        return list(aj.one_hot(label, int(reply.get("passage") or 0), len(premises)))


class LoopVerifier(Verifier):
    """The package verifier, telling the judge which sentences are already committed."""

    def __init__(self, judge: LiveJudge) -> None:
        super().__init__(judge, aj.STRICT_FIGURES)
        self.judge = judge
        self.committed: list[str] = []

    def reset(self) -> None:
        self.committed = []
        self.judge.calls = []

    def check_sentence(
        self, premise: Premise, sentence: str, *, query: str | None = None
    ) -> SentenceVerdict:
        self.judge.prefix = " ".join(self.committed)
        verdict = super().check_sentence(premise, sentence, query=query)
        if verdict.emitted:
            self.committed.append(sentence)
        return verdict


def engine(backend: Any, verifier: Verifier, arm: str, domain: str) -> InFlightGenerator:
    """``source``: the source in the prompt, default steering. ``closed``: the answer starts from
    memory and a rollback writes the source into the context as a user turn."""
    if arm == "source":
        return InFlightGenerator(
            backend,
            verifier,
            max_new_tokens=MAX_NEW_TOKENS,
            system_prompt=PROMPTS[domain],
            refusal=REFUSALS[domain],
        )
    if arm == "closed":
        return InFlightGenerator(
            backend,
            verifier,
            max_new_tokens=MAX_NEW_TOKENS,
            steering="inject",
            inject_template=INJECT[domain],
            system_prompt=CLOSED[domain],
            refusal=REFUSALS[domain],
        )
    raise ValueError(arm)


def answer(
    backend: Any, verifier: LoopVerifier, arm: str, item: Mapping[str, Any]
) -> dict[str, Any]:
    """One answer with its trace. The server's cache is emptied first, so no answer reuses
    another's prefix."""
    verifier.reset()
    backend.flush_cache()
    t0 = time.perf_counter()
    out = engine(backend, verifier, arm, item["domain"]).generate_verified(
        item["query"], item["premise"]
    )
    seconds = time.perf_counter() - t0
    return {
        "key": f"{item['id']}:{arm}",
        "text": out.text,
        "model": backend.model_id,
        "seconds": round(seconds, 3),
        "judge_calls": list(verifier.judge.calls),
        "trace": out.trace,
    }
