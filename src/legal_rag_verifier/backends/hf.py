"""Hugging Face transformers backend (``[hf]`` extra): greedy decode over a held ``DynamicCache``.

The cache is kept aligned to the last token sequence decoded. A call to :meth:`HFBackend.extend`
keeps the longest prefix it shares with ``committed`` and truncates the rest (a rollback), then
feeds only the tokens it has not seen. The last committed token is always re-fed, because the cache
stores keys and values, not the logits that follow them. ``prefix_cache_hit_tokens`` is the reused
length. Constraints are applied as a logits mask.
"""

from __future__ import annotations

import os
import time
from collections.abc import Sequence
from typing import Any, Literal

from legal_rag_verifier.backends._tokenizer import TokenizerMixin
from legal_rag_verifier.engine import Allow, Ban, Constraint, Segment

__all__ = ["HFBackend"]


class HFBackend(TokenizerMixin):
    """A causal LM and its tokenizer, decoding greedily for the engine."""

    name = "hf"

    def __init__(self, model: Any, tokenizer: Any, *, model_id: str | None = None) -> None:
        import torch  # noqa: PLC0415 - optional dependency

        self._torch = torch
        self.model: Any = model.eval()
        self.tokenizer: Any = tokenizer
        self.device = str(next(model.parameters()).device)
        self.model_id = model_id or str(getattr(model.config, "name_or_path", "unknown"))
        eos = getattr(model.generation_config, "eos_token_id", None)
        if eos is None:
            eos = tokenizer.eos_token_id
        self.eos: frozenset[int] = frozenset(eos if isinstance(eos, list) else [eos])
        self._cache: Any = None
        self._cached: list[int] = []  # tokens whose keys/values the cache holds

    @classmethod
    def load(
        cls,
        model_name: str,
        device: str | None = None,
        *,
        revision: str | None = None,
        dtype: str | None = None,
        local_files_only: bool = True,
    ) -> HFBackend:
        """Load a hub checkpoint (pre-quantized bnb checkpoints included) onto ``device``."""
        import torch  # noqa: PLC0415 - optional dependency
        from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: PLC0415

        from legal_rag_verifier.nli import _snapshot, pick_device  # noqa: PLC0415

        device = pick_device(device)
        if device == "mps":
            # transformers 5 copies weights to the device from several threads; on MPS that
            # segfaults or deadlocks (seen with 5.18). Serial loading is safe and as fast here.
            os.environ.setdefault("HF_DEACTIVATE_ASYNC_LOAD", "1")
        torch_dtype = (
            getattr(torch, dtype)
            if dtype
            else (torch.float32 if device == "cpu" else torch.float16)
        )
        tokenizer = AutoTokenizer.from_pretrained(
            model_name, revision=revision, local_files_only=local_files_only
        )
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            revision=revision,
            local_files_only=local_files_only,
            device_map=device,
            dtype=torch_dtype,
        )
        return cls(model, tokenizer, model_id=f"{model_name}@{_snapshot(model_name, revision)}")

    # ------------------------------------------------------------------ cache
    def next_logits(self, committed: Sequence[int]) -> tuple[Any, int]:
        """Logits for the token after ``committed``, and how many tokens the cache reused."""
        torch = self._torch
        if not committed:
            raise ValueError("committed must hold at least the prompt")
        shared = 0
        for a, b in zip(self._cached, committed, strict=False):
            if a != b:
                break
            shared += 1
        keep = min(shared, len(committed) - 1)
        if keep == 0 or self._cache is None:
            from transformers import DynamicCache  # noqa: PLC0415

            self._cache, keep = DynamicCache(config=self.model.config), 0
        elif len(self._cached) > keep:
            self._cache.crop(-(len(self._cached) - keep))  # negative: tokens to remove
        feed = torch.tensor([list(committed[keep:])], device=self.device)
        with torch.inference_mode():
            out = self.model(input_ids=feed, past_key_values=self._cache, use_cache=True)
        self._cache = out.past_key_values
        self._cached = list(committed)
        return out.logits[0, -1].float(), keep

    def _step(self, token: int) -> Any:
        torch = self._torch
        feed = torch.tensor([[token]], device=self.device)
        with torch.inference_mode():
            out = self.model(input_ids=feed, past_key_values=self._cache, use_cache=True)
        self._cache = out.past_key_values
        self._cached.append(token)
        return out.logits[0, -1].float()

    def reset(self) -> None:
        """Drop the cache (the next call prefills from scratch)."""
        self._cache, self._cached = None, []

    def synchronize(self) -> None:
        torch = self._torch
        if self.device.startswith("mps"):
            torch.mps.synchronize()
        elif self.device.startswith("cuda"):
            torch.cuda.synchronize()

    # ------------------------------------------------------------------ decoding
    def extend(
        self,
        committed: Sequence[int],
        *,
        stop: Sequence[str],
        max_new: int,
        constraint: Constraint | None,
    ) -> Segment:
        self.synchronize()
        t0 = time.perf_counter_ns()
        logits, hit = self.next_logits(committed)
        generated: list[int] = []
        finish: Literal["stop", "length", "eos"] = "length"
        span_open = isinstance(constraint, Allow)
        while len(generated) < max_new:
            token = self._choose(logits, constraint, generated, span_open=span_open)
            if span_open and isinstance(constraint, Allow):
                span_open = constraint.next_tokens([*generated, token]) is not None
            if token in self.eos:
                finish = "eos"
                break
            generated.append(token)
            if not span_open and any(s in self.decode([token]) for s in stop):
                finish = "stop"
                break
            if len(generated) < max_new:
                logits = self._step(token)
        self.synchronize()
        return Segment(
            tuple(generated),
            self.decode(generated),
            finish,
            hit,
            time.perf_counter_ns() - t0,
        )

    def _choose(
        self, logits: Any, constraint: Constraint | None, generated: list[int], *, span_open: bool
    ) -> int:
        torch = self._torch
        if isinstance(constraint, Ban):
            banned = constraint.banned(len(generated))
            if banned:
                logits = logits.clone()
                logits[list(banned)] = -torch.inf
        elif isinstance(constraint, Allow) and span_open:
            allowed = constraint.next_tokens(generated)
            if allowed is not None:
                mask = torch.full_like(logits, -torch.inf)
                index = list(allowed)
                mask[index] = logits[index]
                logits = mask
        return int(torch.argmax(logits).item())
