"""Tokenizer methods shared by backends that wrap a Hugging Face tokenizer (duck-typed, stdlib)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from legal_rag_verifier.engine import Tokens


class TokenizerMixin:
    """``chat``, ``encode`` and ``decode`` over ``self.tokenizer``."""

    tokenizer: Any

    def chat(self, messages: Sequence[Mapping[str, str]]) -> Tokens:
        if getattr(self.tokenizer, "chat_template", None):
            encoded = self.tokenizer.apply_chat_template(
                [dict(m) for m in messages], add_generation_prompt=True, return_dict=True
            )
            return tuple(int(t) for t in encoded["input_ids"])
        text = "\n\n".join(f"{m['role']}: {m['content']}" for m in messages) + "\n\nassistant:"
        return self.encode(text)

    def encode(self, text: str) -> Tokens:
        return tuple(int(t) for t in self.tokenizer(text, add_special_tokens=False)["input_ids"])

    def decode(self, tokens: Sequence[int]) -> str:
        return str(self.tokenizer.decode(list(tokens), skip_special_tokens=True))
