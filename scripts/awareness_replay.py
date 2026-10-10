"""Stops 48 and 49 (runs in the container): the awareness measures, read from the model itself.

Method: ``docs/GRID.md`` § Stops 48 and 49. Hugging Face transformers, eager attention, bf16.

- Generator (G): nothing is generated. Each answer is fed after the with-source prompt (attention
  to the source, log-likelihood) and after the closed-book prompt (log-likelihood), per sentence.
- Judge (J): the reply is sampled here, one token at a time, and the attention from each new token
  to the passages and to the sentence is read in the same pass. The reply is then scored after the
  prompt without passages.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from typing import Any

from attention_replay import PREFILL_CHUNK, _feed, _shares  # type: ignore[import-not-found]
from auditor_judge import CLOSE_THINK, SYSTEM, parse_reply  # type: ignore[import-not-found]
from awareness import (  # type: ignore[import-not-found]
    PARSE_SEEDS,
    RETRY_SEEDS,
    partition,
    summarise,
    token_spans,
)

SCORE_CHUNK = 256
DEVICE = "cuda"  # the laptop smoke test sets "cpu"


class Recorder:
    """Attention weights taken at each attention module, for a model whose layers compute them
    under eager attention and then drop them (K2 Horizon's custom code)."""

    def __init__(self, model: Any) -> None:
        self.on = False
        self.got: list[Any] = []
        self.modules = 0
        for name, module in model.named_modules():
            if name.endswith("self_attn"):
                module.register_forward_hook(self._hook)
                self.modules += 1

    def _hook(self, module: Any, args: Any, output: Any) -> None:
        if self.on and isinstance(output, tuple) and len(output) > 1 and output[1] is not None:
            self.got.append(output[1])

    def take(self) -> list[Any]:
        got, self.got = self.got, []
        return got


def load(model_id: str, revision: str, *, custom: bool) -> tuple[Any, Any, Any]:
    import torch  # noqa: PLC0415
    import transformers  # noqa: PLC0415

    tokenizer = transformers.AutoTokenizer.from_pretrained(
        model_id, revision=revision, trust_remote_code=custom
    )
    failure: Exception | None = None
    # A model published with an image tower is not in the causal LM mapping; text goes in alike.
    for auto in ("AutoModelForCausalLM", "AutoModelForImageTextToText"):
        try:
            model, info = getattr(transformers, auto).from_pretrained(
                model_id,
                revision=revision,
                dtype=torch.bfloat16,
                attn_implementation="eager",
                trust_remote_code=custom,
                device_map=DEVICE,
                output_loading_info=True,
            )
        except ValueError as exc:  # not a class of this mapping
            failure = exc
            continue
        if info["missing_keys"]:  # weights saved under another class: not this loader
            failure = RuntimeError(f"{auto}: {len(info['missing_keys'])} weights missing")
            del model
            torch.cuda.empty_cache()
            continue
        model.eval()
        model.aware_recorder = Recorder(model) if custom else None
        return model, tokenizer, torch
    raise RuntimeError(f"no loader for {model_id}") from failure


def render(
    tokenizer: Any, messages: Sequence[Mapping[str, str]], template: Mapping[str, Any]
) -> str:
    text: str = tokenizer.apply_chat_template(
        list(messages), tokenize=False, add_generation_prompt=True, **template
    )
    return text


def encode(tokenizer: Any, text: str) -> tuple[list[int], list[tuple[int, int]] | None]:
    """Token ids of ``text`` as rendered, with character offsets when the tokenizer has them."""
    if getattr(tokenizer, "is_fast", False):
        enc = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
        return list(enc["input_ids"]), [(int(s), int(e)) for s, e in enc["offset_mapping"]]
    return list(tokenizer(text, add_special_tokens=False)["input_ids"]), None


def spans_of(
    tokenizer: Any,
    text: str,
    offsets: Sequence[tuple[int, int]] | None,
    ranges: Sequence[tuple[int, int]],
) -> list[list[int]]:
    """Token ranges covering the character ranges. Without offsets, by the token count of the
    text before each end of the range (one token of error at most at each end)."""
    if offsets is not None:
        spans: list[list[int]] = token_spans(offsets, ranges)
        return spans

    def count(upto: int) -> int:
        return len(tokenizer(text[:upto], add_special_tokens=False)["input_ids"])

    return [[count(start), count(end)] for start, end in ranges]


def _prefill(model: Any, torch: Any, prefix: Sequence[int]) -> tuple[Any, Any]:
    cache, last = None, None
    for at in range(0, len(prefix), PREFILL_CHUNK):
        ids = torch.tensor([list(prefix[at : at + PREFILL_CHUNK])], device=DEVICE)
        pre = model(input_ids=ids, past_key_values=cache, use_cache=True)
        cache, last = pre.past_key_values, pre.logits[0, -1:].float()
        del pre
    return cache, last


def score(
    model: Any, torch: Any, prefix: Sequence[int], parts: Sequence[Sequence[int]]
) -> list[dict[str, Any]]:
    """Each part fed in order after ``prefix``: its log-likelihood, and how many of its tokens
    are the model's top token. No attention is read."""
    seq = [t for part in parts for t in part]
    if not seq:
        return [{"logp": None, "top1_match": 0} for _ in parts]
    with torch.no_grad():
        cache, last = _prefill(model, torch, prefix)
        logits = [last]
        for at in range(0, len(seq), SCORE_CHUNK):
            ids = torch.tensor([seq[at : at + SCORE_CHUNK]], device=DEVICE)
            out = model(input_ids=ids, past_key_values=cache, use_cache=True)
            cache = out.past_key_values
            logits.append(out.logits[0].float())
            del out
    logit = torch.cat(logits)[:-1]
    target = torch.tensor(seq, device=DEVICE)
    token_logp = torch.log_softmax(logit, -1).gather(1, target[:, None])[:, 0]
    top = logit.argmax(-1) == target
    results: list[dict[str, Any]] = []
    at = 0
    for part in parts:
        rows = slice(at, at + len(part))
        results.append(
            {
                "logp": round(float(token_logp[rows].sum()), 4) if part else None,
                "top1_match": int(top[rows].sum()) if part else 0,
            }
        )
        at += len(part)
    del cache
    if DEVICE == "cuda":
        torch.cuda.empty_cache()
    return results


# ---------------------------------------------------------------------- G: the generator


def generator_measure(
    model: Any, tokenizer: Any, torch: Any, item: Mapping[str, Any]
) -> dict[str, Any]:
    """One answer: per sentence, attention to the source and log-likelihood under both prompts."""
    t0 = time.time()
    text = render(tokenizer, item["with"], {})
    at = text.index(item["with"][0]["content"])
    ids, offsets = encode(tokenizer, text)
    start, end = item["span"]
    span = spans_of(tokenizer, text, offsets, [(at + start, at + end)])
    answer, answer_offsets = encode(tokenizer, item["text"])
    if answer_offsets is None:
        raise RuntimeError("the generator's tokenizer gives no offsets")
    parts = [[answer[i] for i in group] for group in partition(answer_offsets, item["ends"])]
    with_source = _feed(model, torch, ids, parts, {"source": span}, device=DEVICE)
    t1 = time.time()
    closed, _ = encode(tokenizer, render(tokenizer, item["without"], {}))
    without = score(model, torch, closed, parts)
    sentences = [
        {
            "tokens": w["tokens"],
            "logp": w.get("logp"),
            "logp_without": wo["logp"],
            "top1_match": w.get("top1_match", 0),
            "top1_match_without": wo["top1_match"],
            "attention": (w.get("attention") or {}).get("source"),
        }
        for w, wo in zip(with_source, without, strict=True)
    ]
    return {
        "key": item["key"],
        "prompt_tokens": len(ids),
        "span_tokens": sum(e - s for s, e in span),
        "sentences": sentences,
        "s_with": round(t1 - t0, 3),
        "s_without": round(time.time() - t1, 3),
    }


# ---------------------------------------------------------------------- J: the judge


def draw(
    torch: Any, logits: Any, sampling: Mapping[str, Any], seen: Sequence[int], rng: Any
) -> int:
    """One token: presence penalty on tokens already generated, temperature, top-k, top-p."""
    logits = logits.clone()
    penalty = sampling.get("presence_penalty")
    if penalty and seen:
        logits[sorted(set(seen))] -= penalty
    logits = logits / sampling["temperature"]
    top_k = sampling.get("top_k")
    if top_k:
        logits[logits < torch.topk(logits, top_k).values[-1]] = float("-inf")
    probs = torch.softmax(logits, -1)
    top_p = sampling.get("top_p")
    if top_p and top_p < 1:
        ordered, index = probs.sort(descending=True)
        ordered[ordered.cumsum(0) - ordered >= top_p] = 0.0
        probs = torch.zeros_like(probs).scatter(0, index, ordered)
    return int(torch.multinomial(probs / probs.sum(), 1, generator=rng))


def sample(
    model: Any,
    torch: Any,
    prompt: Sequence[int],
    spans: Mapping[str, list[list[int]]],
    *,
    sampling: Mapping[str, Any],
    seed: int,
    max_new: int,
    stop: frozenset[int],
) -> dict[str, Any]:
    """Sample a reply after ``prompt``. Per generated token: its log-probability and, when the
    model returns attention, the share of its attention on each span."""
    rng = torch.Generator(device=DEVICE).manual_seed(seed)
    tokens: list[int] = []
    logps: list[float] = []
    shares: list[Any] = []
    attention = True
    finish = "length"
    recorder = getattr(model, "aware_recorder", None)
    source = "output"
    with torch.no_grad():
        cache, last = _prefill(model, torch, prompt)
        for _ in range(max_new):
            token = draw(torch, last[0], sampling, tokens, rng)
            if token in stop:
                finish = "stop"
                break
            tokens.append(token)
            logps.append(float(torch.log_softmax(last[0], -1)[token]))
            if recorder is not None:
                recorder.on = attention
            step = model(
                input_ids=torch.tensor([[token]], device=DEVICE),
                past_key_values=cache,
                use_cache=True,
                output_attentions=attention,
            )
            cache, last = step.past_key_values, step.logits[0, -1:].float()
            got = getattr(step, "attentions", None)
            if recorder is not None:
                recorder.on = False
                taken = recorder.take()
                if not got and taken:
                    got, source = taken, "modules"
            if attention and got and got[0] is not None:
                shares.append(_shares(torch, got, spans))
            else:
                attention = False
            del step
    out: dict[str, Any] = {
        "ids": tokens,
        "tokens": len(tokens),
        "logp": round(sum(logps), 4) if tokens else None,
        "finish": finish,
        "attention": None,
        "attention_from": None,
    }
    if attention and shares:
        share = torch.cat(shares, dim=-1).mean(-1)  # layers x spans
        out["attention"] = {
            name: [round(float(v), 6) for v in share[:, k]] for k, name in enumerate(spans)
        }
        out["attention_from"] = source
    del cache
    if DEVICE == "cuda":
        torch.cuda.empty_cache()
    return out


def stop_ids(model: Any, tokenizer: Any) -> frozenset[int]:
    found = [tokenizer.eos_token_id, getattr(model.generation_config, "eos_token_id", None)]
    flat: list[int] = []
    for f in found:
        flat += [int(x) for x in (f if isinstance(f, list | tuple) else [f]) if x is not None]
    return frozenset(flat)


def judge_attempt(
    model: Any,
    tokenizer: Any,
    torch: Any,
    item: Mapping[str, Any],
    spec: Mapping[str, Any],
    *,
    attempt: int,
) -> list[dict[str, Any]]:
    """One attempt at a clause: sampled with seed ``attempt``; a reply that does not parse is
    sampled again with ``attempt`` + 100, then + 200. Every sample is returned."""
    system = {"role": "system", "content": SYSTEM}
    text = render(tokenizer, [system, {"role": "user", "content": item["user"]}], spec["template"])
    at = text.rindex(item["user"])
    ids, offsets = encode(tokenizer, text)
    spans = {
        name: spans_of(tokenizer, text, offsets, [(at + s, at + e)])
        for name, (s, e) in item["spans"].items()
    }
    blank, _ = encode(
        tokenizer,
        render(tokenizer, [system, {"role": "user", "content": item["blank"]}], spec["template"]),
    )
    stop = stop_ids(model, tokenizer)
    rows = []
    for offset in PARSE_SEEDS:
        t0 = time.time()
        out = sample(
            model,
            torch,
            ids,
            spans,
            sampling=spec["sampling"],
            seed=attempt + offset,
            max_new=spec["max_new"],
            stop=stop,
        )
        t1 = time.time()
        without = score(model, torch, blank, [out["ids"]])[0]["logp"]
        reply = CLOSE_THINK.split(tokenizer.decode(out.pop("ids"), skip_special_tokens=False))[-1]
        try:
            parsed = parse_reply(reply)
        except ValueError:  # includes a JSON decode error
            parsed = {"label": "error", "passage": 0, "reason": reply[-300:]}
        rows.append(
            {
                "sha": item["sha"],
                "attempt": attempt,
                "seed": attempt + offset,
                **parsed,
                **out,
                "logp_without": without,
                "prompt_tokens": len(ids),
                "span_tokens": {k: sum(e - s for s, e in v) for k, v in spans.items()},
                "offsets": offsets is not None,
                "s_generate": round(t1 - t0, 3),
                "s_measure": round(time.time() - t1, 3),
            }
        )
        if parsed["label"] != "error":
            break
    return rows


def judge_retry(
    model: Any, tokenizer: Any, torch: Any, item: Mapping[str, Any], spec: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Stop 49: attempts 1 to 5 until one is at or over the clause's threshold."""
    rows: list[dict[str, Any]] = []
    for attempt in RETRY_SEEDS:
        tried = judge_attempt(model, tokenizer, torch, item, spec, attempt=attempt)
        rows += tried
        value = summarise(tried[-1])[item["candidate"]]
        if tried[-1]["label"] != "error" and value is not None and value >= item["threshold"]:
            break
    return rows
