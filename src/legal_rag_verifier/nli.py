"""DeBERTa-v3 NLI head (``[nli]`` extra): one batched forward pass over every premise window.

Implements :class:`legal_rag_verifier.verifier.NLIScorer`. Each premise window is split into chunks
that fit the encoder with the hypothesis (sentence boundaries first, then words); a window's score
is that of its most *related* chunk (highest entailment + contradiction, i.e. lowest neutral), in
the style of SummaC-ZS (Laban et al. 2022). Label indices are read from the model's ``id2label``:
the cross-encoder checkpoints use 0 = contradiction, 1 = entailment, 2 = neutral.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any

from legal_rag_verifier.segmenter import split_sentences
from legal_rag_verifier.verifier import NLIProbs

__all__ = ["DEFAULT_MODEL", "SentenceNLIVerifier", "pick_device"]

DEFAULT_MODEL = "cross-encoder/nli-deberta-v3-small"
_MAX_HYPOTHESIS_TOKENS = 128
_SPECIAL_TOKENS = 3  # [CLS] premise [SEP] hypothesis [SEP]
# Fixed batch size and padded length bound the number of distinct input shapes: MPS compiles a
# new graph per shape, and unbounded shapes made it compile instead of compute (stop 15).
_BATCH = 16
_PAD_MULTIPLE = 64


def pick_device(preferred: str | None = None) -> str:
    """``cuda`` > ``mps`` > ``cpu`` unless ``preferred`` is given."""
    import torch  # noqa: PLC0415 - optional dependency

    if preferred:
        return preferred
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _snapshot(model_name: str, revision: str | None) -> str:
    """The commit hash a hub checkpoint resolved to in the local cache (or the local dir name)."""
    from pathlib import Path  # noqa: PLC0415

    if Path(model_name).exists():
        return Path(model_name).resolve().name
    from huggingface_hub import constants  # noqa: PLC0415 - comes with transformers

    ref = Path(constants.HF_HUB_CACHE) / f"models--{model_name.replace('/', '--')}" / "refs"
    ref /= revision or "main"
    if ref.is_file():
        return ref.read_text(encoding="utf-8").strip()
    return revision or "unknown"


class SentenceNLIVerifier:
    """Batched NLI scorer. ``model_id`` (name@revision) is recorded in every trace."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        device: str | None = None,
        *,
        revision: str | None = None,
        max_length: int = 512,
        local_files_only: bool = True,
    ) -> None:
        import torch  # noqa: PLC0415 - optional dependency
        from transformers import (  # noqa: PLC0415 - optional dependency
            AutoModelForSequenceClassification,
            AutoTokenizer,
        )

        self._torch = torch
        self.device = pick_device(device)
        self.max_length = max_length
        self.tokenizer: Any = AutoTokenizer.from_pretrained(
            model_name, revision=revision, local_files_only=local_files_only
        )
        model: Any = AutoModelForSequenceClassification.from_pretrained(
            model_name, revision=revision, local_files_only=local_files_only
        )
        self.model: Any = model.to(self.device).eval()
        labels = {str(v).lower(): int(k) for k, v in self.model.config.id2label.items()}
        try:
            self._entailment = labels["entailment"]
            self._neutral = labels["neutral"]
            self._contradiction = labels["contradiction"]
        except KeyError as exc:
            raise ValueError(f"{model_name}: id2label lacks an NLI label: {labels}") from exc
        self.model_id = f"{model_name}@{_snapshot(model_name, revision)}"
        self._premise_budget = max_length - _MAX_HYPOTHESIS_TOKENS - _SPECIAL_TOKENS
        self._chunks: dict[str, tuple[str, ...]] = {}

    # ------------------------------------------------------------------ chunking
    def _length(self, text: str) -> int:
        return len(self.tokenizer(text, add_special_tokens=False)["input_ids"])

    def chunks(self, premise: str) -> tuple[str, ...]:
        """Split ``premise`` into pieces that fit the premise budget (cached per text)."""
        cached = self._chunks.get(premise)
        if cached is not None:
            return cached
        if self._length(premise) <= self._premise_budget:
            out: tuple[str, ...] = (premise,)
        else:
            pieces: list[str] = []
            current = ""
            for sentence in [s.text for s in split_sentences(premise)]:
                for unit in self._fit(sentence):
                    candidate = f"{current} {unit}".strip()
                    if current and self._length(candidate) > self._premise_budget:
                        pieces.append(current)
                        current = unit
                    else:
                        current = candidate
            if current:
                pieces.append(current)
            out = tuple(pieces)
        self._chunks[premise] = out
        return out

    def _fit(self, sentence: str) -> list[str]:
        if self._length(sentence) <= self._premise_budget:
            return [sentence]
        words = sentence.split()
        out: list[str] = []
        current: list[str] = []
        for word in words:
            if current and self._length(" ".join([*current, word])) > self._premise_budget:
                out.append(" ".join(current))
                current = []
            current.append(word)
        if current:
            out.append(" ".join(current))
        return out

    # ------------------------------------------------------------------ scoring
    def score(self, premises: Sequence[str], hypothesis: str) -> list[NLIProbs]:
        """Every ``[chunk, hypothesis]`` pair, in fixed-shape batches; one result per premise."""
        torch = self._torch
        owners: list[int] = []
        pairs: list[str] = []
        for i, premise in enumerate(premises):
            for chunk in self.chunks(premise):
                owners.append(i)
                pairs.append(chunk)
        if not pairs:
            return []
        probs: list[list[float]] = []
        for start in range(0, len(pairs), _BATCH):
            batch = pairs[start : start + _BATCH]
            padded = batch + [batch[0]] * (_BATCH - len(batch))  # fixed batch shape
            encoded = self.tokenizer(
                padded,
                [hypothesis] * len(padded),
                padding=True,
                pad_to_multiple_of=_PAD_MULTIPLE,
                truncation="longest_first",
                max_length=self.max_length,
                return_tensors="pt",
            ).to(self.device)
            with torch.inference_mode():
                logits = self.model(**encoded).logits.float()
                probs += torch.softmax(logits, dim=-1).cpu().tolist()[: len(batch)]
        best: dict[int, NLIProbs] = {}
        for owner, row in zip(owners, probs, strict=True):
            candidate = NLIProbs(
                row[self._entailment], row[self._neutral], row[self._contradiction]
            )
            current = best.get(owner)
            if current is None or candidate.neutral < current.neutral:
                best[owner] = candidate
        return [best[i] for i in range(len(premises))]

    def synchronize(self) -> None:
        """Wait for queued device work (for wall-clock timing on MPS/CUDA)."""
        torch = self._torch
        if self.device == "mps":
            torch.mps.synchronize()
        elif self.device == "cuda":
            torch.cuda.synchronize()

    def timed_score(self, premises: Sequence[str], hypothesis: str) -> tuple[list[NLIProbs], int]:
        """:meth:`score` with device-synchronised wall time in nanoseconds."""
        self.synchronize()
        t0 = time.perf_counter_ns()
        result = self.score(premises, hypothesis)
        self.synchronize()
        return result, time.perf_counter_ns() - t0
