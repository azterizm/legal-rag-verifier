"""Stop 29, attention phase (runs in the container): attention and likelihood on recorded tokens.

Method: ``docs/GRID.md`` § Stop 29. Hugging Face transformers, eager attention, bf16, the
generator's revision. Nothing is generated: each context is prefilled, then the recorded tokens are
fed in and the attention from their positions and their log-probabilities are read. Contexts:

- ``none``: prompt + committed answer (no inserted turn);
- ``inserted``: prompt + committed answer + R1's inserted turn;
- ``top``: R3's prompt (provision after the query) + committed answer.

Sequences: X (the rejected draft) and S + N (R1's regenerated sentence and its first follow-on). Per
sequence part: log P, per-layer attention share to each span (attention to the span over all
attention except to the first token, mean over heads, then over the part's positions), and how often
the model's top token equals the recorded one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

MODEL = "Qwen/Qwen2.5-7B-Instruct"


def load(revision: str) -> tuple[Any, Any]:
    import torch  # noqa: PLC0415
    import transformers  # noqa: PLC0415
    from transformers import AutoModelForCausalLM  # noqa: PLC0415

    major, minor = (int(x) for x in transformers.__version__.split(".")[:2])
    dtype = "dtype" if (major, minor) >= (4, 56) else "torch_dtype"
    loader: Any = AutoModelForCausalLM
    model = loader.from_pretrained(
        MODEL, revision=revision, attn_implementation="eager", **{dtype: torch.bfloat16}
    ).to("cuda")
    model.eval()
    return model, torch


PREFILL_CHUNK = 1024  # eager attention materialises chunk x context weights per layer
FEED_CHUNK = 32


def _shares(torch: Any, attentions: Sequence[Any], spans: Mapping[str, list[list[int]]]) -> Any:
    """Per span: a layers x positions tensor of attention share from each fed position to the span
    (attention to the span over all attention except to the first token, mean over heads)."""
    rows = []
    for layer in attentions:
        att = layer[0].float()  # heads x positions x keys
        total = att[..., 1:].sum(-1)
        per_span = []
        for ranges in spans.values():
            mass = torch.zeros_like(total)
            for start, end in ranges:
                mass += att[..., start:end].sum(-1)
            per_span.append((mass / total).mean(0))  # positions
        rows.append(torch.stack(per_span))  # spans x positions
    return torch.stack(rows)  # layers x spans x positions


def _feed(
    model: Any,
    torch: Any,
    prefix: Sequence[int],
    parts: Sequence[Sequence[int]],
    spans: Mapping[str, list[list[int]]],
    *,
    device: str = "cuda",
) -> list[dict[str, Any]]:
    """Prefill ``prefix``, feed the parts after it, and measure each part."""
    seq = [t for part in parts for t in part]
    if not seq:
        return [{"tokens": 0} for _ in parts]
    cache = None
    with torch.no_grad():
        for at in range(0, len(prefix), PREFILL_CHUNK):
            ids = torch.tensor([list(prefix[at : at + PREFILL_CHUNK])], device=device)
            pre = model(input_ids=ids, past_key_values=cache, use_cache=True)
            cache, last = pre.past_key_values, pre.logits[0, -1:].float()
            del pre
        logits, shares = [last], []
        for at in range(0, len(seq), FEED_CHUNK):
            ids = torch.tensor([seq[at : at + FEED_CHUNK]], device=device)
            out = model(
                input_ids=ids, past_key_values=cache, use_cache=True, output_attentions=True
            )
            cache = out.past_key_values
            logits.append(out.logits[0].float())
            shares.append(_shares(torch, out.attentions, spans))
            del out
    logit = torch.cat(logits)[:-1]
    share = torch.cat(shares, dim=-1)  # layers x spans x positions
    target = torch.tensor(seq, device=device)
    token_logp = torch.log_softmax(logit, -1).gather(1, target[:, None])[:, 0]
    top = logit.argmax(-1) == target
    results: list[dict[str, Any]] = []
    at = 0
    for part in parts:
        rows = slice(at, at + len(part))
        results.append(
            {
                "tokens": len(part),
                "logp": round(float(token_logp[rows].sum()), 4) if part else None,
                "top1_match": int(top[rows].sum()) if part else 0,
                "attention": {
                    name: [round(float(v), 6) for v in share[:, k, rows].mean(-1)]
                    for k, name in enumerate(spans)
                }
                if part
                else None,
            }
        )
        at += len(part)
    del cache
    if device == "cuda":
        torch.cuda.empty_cache()
    return results


def measure(
    model: Any, torch: Any, record: Mapping[str, Any], device: str = "cuda"
) -> dict[str, Any]:
    replay = record["replay"]
    spans = replay["spans"]
    prompt, committed, note = replay["prompt"], replay["committed"], replay["note"]
    x = record["X"]["tokens"]
    s = record["R1"]["tokens"]
    follow = record["R1"]["follow_on"]
    n = follow[0]["tokens"] if follow else []
    base = {"inserted_windows": spans["inserted_windows"], "other_windows": spans["other_windows"]}
    contexts = {
        "none": ([*prompt, *committed], base),
        "inserted": (
            [*prompt, *committed, *note],
            {**base, "inserted_copy": spans["inserted_copy"]},
        ),
        "top": ([*replay["prompt_top"], *committed], {**base, "top_copy": spans["top_copy"]}),
    }
    out: dict[str, Any] = {"id": record["id"]}
    for name, (prefix, named) in contexts.items():
        [x_part] = _feed(model, torch, prefix, [x], named, device=device)
        s_part, n_part = _feed(model, torch, prefix, [s, n], named, device=device)
        out[name] = {"X": x_part, "S": s_part, "N": n_part}
    return out
