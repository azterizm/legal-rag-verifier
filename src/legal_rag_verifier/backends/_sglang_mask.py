"""Server-side logit mask for the SGLang backend (imported by the SGLang server, needs sglang).

Sent with each constrained one-token request as ``custom_logit_processor``; the server must run
with ``--enable-custom-logit-processor``. ``custom_params`` carries ``allowed`` or ``banned``
token ids for that single step.
"""

from __future__ import annotations

from typing import Any

import torch
from sglang.srt.sampling.custom_logit_processor import CustomLogitProcessor


class MaskProcessor(CustomLogitProcessor):  # type: ignore[misc]
    """Keep only ``allowed`` token ids, or drop ``banned`` ones, per request in the batch."""

    def __call__(self, logits: Any, custom_param_list: list[dict[str, Any] | None]) -> Any:
        for i, params in enumerate(custom_param_list):
            if not params:
                continue
            allowed = params.get("allowed")
            if allowed:
                row = torch.full_like(logits[i], float("-inf"))
                row[allowed] = logits[i][allowed]
                logits[i] = row
            banned = params.get("banned")
            if banned:
                logits[i][banned] = float("-inf")
        return logits
