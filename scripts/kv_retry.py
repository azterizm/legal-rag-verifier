"""Stop 67 (docs/GRID.md § Stop 67), in the container: six retries from one state.

The state is decided on this machine (``scripts/retry_states.py``): the prompt, the committed
answer, the rejected draft X, and per arm the tokens it needs. Here the generator runs each arm from
the same state over a held ``DynamicCache``:

- ``B``: the engine's default steering (a seed and an allow-list or ban).
- ``T``: stop 30's user turn at the cut, kept in the context.
- ``P``: the passage fed by a forward pass, then the last committed token fed again after it.
- ``K``: the passage's KV computed alone, keys rotated to the cursor, spliced in; the last committed
  token after it.
- ``K-far``: the same KV right after the system turn; every later key rotated forward by its length.
- ``KA``: ``K`` with the attention scores on the passage keys raised by ``ln(f)``.

In ``P``, ``K``, ``K-far`` and ``KA`` the passage sits before the last committed token, so the four
arms share the token that decodes the retry's first token, and its position. Every arm runs through
one attention function (eager, causal over cache slots), so the arms differ only in what they
change. Positions are kept per token: a splice leaves a gap in them, which rotary attention handles.
Greedy; the engine's own sentence boundary.
"""

from __future__ import annotations

import math
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from legal_rag_verifier.backends.hf import HFBackend
from legal_rag_verifier.engine import Allow, Ban, Constraint, InFlightGenerator, _Stream
from legal_rag_verifier.verifier import Verifier

ARMS = ("B", "T", "P", "K", "K-far", "KA")
SPLICED = frozenset({"K", "K-far", "KA"})
PASSAGE_ARMS = frozenset({"P", "K", "K-far", "KA"})
MAX_SENTENCE_TOKENS = 160
MAX_NEW_TOKENS = 512
CHUNK = 2048  # tokens per forward pass when a stream is fed


@dataclass
class Control:
    """What the attention function does on the next forward passes."""

    span: tuple[int, int] | None = None  # cache slots of the passage
    bias: float = 0.0  # added to the scores on ``span``
    record: bool = False  # keep the share of attention on ``span``
    shares: list[float] = field(default_factory=list)


CONTROL = Control()


def attention(  # noqa: PLR0917 - the signature transformers calls
    module: Any,
    query: Any,
    key: Any,
    value: Any,
    attention_mask: Any,
    scaling: float,
    dropout: float = 0.0,
    **kwargs: Any,
) -> tuple[Any, None]:
    """Eager attention, causal over cache slots: the queries are the last slots. Batch 1, no
    padding."""
    import torch  # noqa: PLC0415
    from transformers.models.qwen2.modeling_qwen2 import repeat_kv  # noqa: PLC0415

    keys = repeat_kv(key, module.num_key_value_groups)
    values = repeat_kv(value, module.num_key_value_groups)
    scores = torch.matmul(query, keys.transpose(2, 3)) * scaling
    q_len, k_len = scores.shape[-2], scores.shape[-1]
    causal = torch.ones(q_len, k_len, dtype=torch.bool, device=scores.device).tril(k_len - q_len)
    scores = scores.masked_fill(~causal, float("-inf"))
    span = CONTROL.span
    if span is not None and CONTROL.bias:
        scores[..., span[0] : span[1]] += CONTROL.bias
    probs = torch.nn.functional.softmax(scores, dim=-1, dtype=torch.float32)
    if span is not None and CONTROL.record:
        rest = (1.0 - probs[..., 0]).clamp_min(1e-9)  # all attention but the first token's
        share = probs[..., span[0] : span[1]].sum(-1) / rest  # [1, heads, q]
        CONTROL.shares.extend(share.mean(dim=1)[0].tolist())
    out = torch.matmul(probs.to(query.dtype), values)
    return out.transpose(1, 2).contiguous(), None


def install(model: Any) -> None:
    """Route the model's attention through :func:`attention`."""
    from transformers.models.qwen2 import modeling_qwen2  # noqa: PLC0415

    modeling_qwen2.eager_attention_forward = attention
    model.config._attn_implementation = "eager"


def load(model_name: str, revision: str) -> Any:
    import torch  # noqa: PLC0415
    from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: PLC0415

    tokenizer = AutoTokenizer.from_pretrained(model_name, revision=revision)
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        revision=revision,
        dtype=torch.bfloat16,
        device_map="cuda",
        attn_implementation="eager",
    )
    install(model)
    return ArmBackend(model, tokenizer, model_id=f"{model_name}@{revision}")


def rotate(model: Any, keys: Any, delta: int) -> Any:
    """Keys computed at positions p, as if computed at p + ``delta`` (rotary attention)."""
    import torch  # noqa: PLC0415
    from transformers.models.qwen2.modeling_qwen2 import rotate_half  # noqa: PLC0415

    if delta == 0:
        return keys
    k = keys.float()
    ids = torch.full((1, k.shape[-2]), delta, device=k.device, dtype=torch.long)
    cos, sin = model.model.rotary_emb(k, ids)
    out = k * cos.unsqueeze(1) + rotate_half(k) * sin.unsqueeze(1)  # type: ignore[no-untyped-call,unused-ignore]
    return out.to(keys.dtype)


def constraint_of(spec: Mapping[str, Any] | None) -> Constraint | None:
    if not spec:
        return None
    if "ban" in spec:
        return Ban(frozenset(spec["ban"]))
    return Allow(tuple(tuple(s) for s in spec["allow"]))


class ArmBackend(HFBackend):
    """The engine's HF backend over a cache that can also hold a passage outside the token stream.

    ``_cached`` is the token stream the engine sees; ``_positions`` their positions; ``passage``
    the cache slots of a passage that is not in the stream. A stream token's slot is its index, plus
    the passage length when it comes after the passage."""

    def __init__(self, model: Any, tokenizer: Any, *, model_id: str | None = None) -> None:
        super().__init__(model, tokenizer, model_id=model_id)
        self.reset()
        self.computed = 0  # tokens through the model since the last ``reset``

    def reset(self) -> None:
        from transformers import DynamicCache  # noqa: PLC0415

        self._cache = DynamicCache(config=self.model.config)
        self._cached = []
        self._positions: list[int] = []
        self._logits: Any = None
        self.passage: tuple[int, int] | None = None
        self.pos = 0
        self.computed = 0

    # ------------------------------------------------------------------ cache
    def _layers(self) -> list[Any]:
        return list(self._cache.layers)

    def slots(self) -> int:
        return int(self._cache.get_seq_length())

    def _slot(self, index: int) -> int:
        if self.passage is not None and index >= self.passage[0]:
            return index + self.passage[1] - self.passage[0]
        return index

    def _forward(self, tokens: Sequence[int], positions: Sequence[int]) -> Any:
        torch = self._torch
        ids = torch.tensor([list(tokens)], device=self.device)
        pos = torch.tensor([list(positions)], device=self.device)
        with torch.inference_mode():
            out = self.model(
                input_ids=ids, position_ids=pos, past_key_values=self._cache, use_cache=True
            )
        self._cache = out.past_key_values
        self.computed += len(tokens)
        return out.logits[0]

    def feed(self, tokens: Sequence[int]) -> None:
        """Append ``tokens`` to the stream at the next positions."""
        if not tokens:
            return
        for at in range(0, len(tokens), CHUNK):  # eager scores grow with length x context
            piece = list(tokens[at : at + CHUNK])
            positions = list(range(self.pos, self.pos + len(piece)))
            logits = self._forward(piece, positions)
            self._cached += piece
            self._positions += positions
            self.pos += len(piece)
        self._logits = logits[-1].float()

    def _crop_stream(self, keep: int) -> None:
        """Drop stream tokens from ``keep`` on; they must all come after the passage."""
        drop = len(self._cached) - keep
        if drop <= 0:
            return
        if self.passage is not None and self._slot(keep) < self.passage[1]:
            raise RuntimeError("cannot roll back into the passage")
        self._cache.crop(-drop)
        self.pos = self._positions[keep]
        self._cached, self._positions = self._cached[:keep], self._positions[:keep]
        self._logits = None

    def next_logits(self, committed: Sequence[int]) -> tuple[Any, int]:
        shared = 0
        for a, b in zip(self._cached, committed, strict=False):
            if a != b:
                break
            shared += 1
        if shared == len(self._cached) == len(committed) and self._logits is not None:
            return self._logits, shared
        keep = min(shared, len(committed) - 1)
        self._crop_stream(keep)
        self.feed(committed[keep:])
        return self._logits, keep

    def _step(self, token: int) -> Any:
        self.feed([token])
        return self._logits

    # ------------------------------------------------------------------ the passage
    def alone(self, tokens: Sequence[int]) -> list[tuple[Any, Any]]:
        """The passage's keys and values computed with nothing before it, at positions 0 to n-1."""
        from transformers import DynamicCache  # noqa: PLC0415

        torch = self._torch
        cache = DynamicCache(config=self.model.config)
        ids = torch.tensor([list(tokens)], device=self.device)
        pos = torch.arange(len(tokens), device=self.device)[None]
        with torch.inference_mode():
            self.model(input_ids=ids, position_ids=pos, past_key_values=cache, use_cache=True)
        self.computed += len(tokens)
        return [(layer.keys, layer.values) for layer in cache.layers]  # type: ignore[union-attr,unused-ignore]

    def splice(self, kv: Sequence[tuple[Any, Any]], at: int) -> None:
        """Insert a passage computed alone before stream token ``at``: its keys rotated to that
        token's position, the keys of every later stream token rotated forward by its length."""
        if self.passage is not None:
            raise RuntimeError("one passage at a time")
        torch = self._torch
        n = int(kv[0][0].shape[-2])
        start = self._positions[at] if at < len(self._positions) else self.pos
        for layer, (k, v) in zip(self._layers(), kv, strict=True):
            head_k, tail_k = layer.keys[..., :at, :], layer.keys[..., at:, :]
            head_v, tail_v = layer.values[..., :at, :], layer.values[..., at:, :]
            tail_k = rotate(self.model, tail_k, n) if tail_k.shape[-2] else tail_k
            layer.keys = torch.cat([head_k, rotate(self.model, k, start), tail_k], dim=-2)
            layer.values = torch.cat([head_v, v, tail_v], dim=-2)
        self._positions = self._positions[:at] + [p + n for p in self._positions[at:]]
        self.pos += n
        self.passage = (at, at + n)

    def feed_passage(self, tokens: Sequence[int]) -> None:
        """The passage through the model after the stream, outside the stream."""
        if self.passage is not None:
            raise RuntimeError("one passage at a time")
        at = len(self._cached)
        self._forward(tokens, list(range(self.pos, self.pos + len(tokens))))
        self.pos += len(tokens)
        self.passage = (at, at + len(tokens))

    def remove_passage(self) -> None:
        """Take the passage out of the cache; the stream's positions keep their gap. The last
        stream token is fed again on the next call, so its logits no longer see the passage."""
        if self.passage is None:
            return
        a, b = self.passage
        torch = self._torch
        for layer in self._layers():
            layer.keys = torch.cat([layer.keys[..., :a, :], layer.keys[..., b:, :]], dim=-2)
            layer.values = torch.cat([layer.values[..., :a, :], layer.values[..., b:, :]], dim=-2)
        self.passage = None
        self._crop_stream(len(self._cached) - 1)

    # ------------------------------------------------------------------ readings
    def logprob(self, tokens: Sequence[int]) -> float:
        """log P(``tokens``) after the stream, leaving the cache as it was."""
        torch = self._torch
        if self._logits is None:
            raise RuntimeError("no logits: feed the stream first")
        first = torch.log_softmax(self._logits, -1)[tokens[0]].item()
        if len(tokens) == 1:
            return float(first)
        keep, logits_before = len(self._cached), self._logits
        record, CONTROL.record = CONTROL.record, False
        positions = list(range(self.pos, self.pos + len(tokens) - 1))
        logits = self._forward(tokens[:-1], positions).float()
        CONTROL.record = record
        rows = torch.arange(len(tokens) - 1, device=logits.device)
        rest = torch.log_softmax(logits, -1)[rows, torch.tensor(tokens[1:], device=logits.device)]
        self._cache.crop(-(len(tokens) - 1))
        self._cached, self._positions = self._cached[:keep], self._positions[:keep]
        self.pos = positions[0]
        self._logits = logits_before
        return float(first + rest.sum().item())


# ---------------------------------------------------------------------- one state


def prepare(backend: ArmBackend, state: Mapping[str, Any], arm: str, bias: float = 0.0) -> None:
    """The cache for ``arm``: the stream is prompt + committed (+ the turn in T)."""
    stream = [*state["prompt"], *state["committed"]]
    backend.reset()
    CONTROL.span, CONTROL.bias, CONTROL.record, CONTROL.shares = None, 0.0, False, []
    if arm in ("G", "B"):
        backend.feed(stream)
        return
    # T, P, K, K-far, KA: the token before the retry is fed last, with the share recorded.
    if arm == "T":
        turn = state["turn"]
        a, b = state["turn_span"]
        CONTROL.span = (len(stream) + a, len(stream) + b)
        backend.feed([*stream, *turn[:-1]])
        last = turn[-1:]
    else:
        backend.feed(stream[:-1])
        if arm == "P":
            backend.feed_passage(state["passage"])
        else:
            at = state["far_at"] if arm == "K-far" else len(stream) - 1
            backend.splice(backend.alone(state["passage"]), at)
        CONTROL.span = backend.passage
        CONTROL.bias = bias if arm == "KA" else 0.0
        last = stream[-1:]
    CONTROL.record = True  # the token that decodes the retry's first token counts in the share
    backend.feed(last)
    CONTROL.record = False


def run_arm(
    backend: ArmBackend, state: Mapping[str, Any], arm: str, factor: float = 1.0
) -> dict[str, Any]:
    """One retry and its follow-on sentence, with the readings."""
    bias = math.log(factor) if arm == "KA" else 0.0
    backend.synchronize()
    t0 = time.perf_counter()
    prepare(backend, state, arm, bias)
    backend.synchronize()
    prepare_seconds = time.perf_counter() - t0
    computed = backend.computed
    engine = InFlightGenerator(
        backend, Verifier(), max_new_tokens=MAX_NEW_TOKENS, max_sentence_tokens=MAX_SENTENCE_TOKENS
    )
    prompt = tuple(state["prompt"])
    context = [*state["committed"], *(state["turn"] if arm == "T" else [])]
    logp_x = backend.logprob(state["x_turn"] if arm == "T" else state["x"])
    seed, constraint = ([], None)
    if arm == "B":
        seed, constraint = list(state["b_seed"]), constraint_of(state["b_constraint"])
    stream = _Stream(answer=list(state["committed"]), context=context)
    before = backend.computed
    CONTROL.record = CONTROL.span is not None
    t1 = time.perf_counter()
    draft = engine._draft(prompt, stream, seed, None, constraint)
    backend.synchronize()
    retry_seconds = time.perf_counter() - t1
    CONTROL.record = False
    shares = list(CONTROL.shares)
    computed += backend.computed - before
    CONTROL.span, CONTROL.bias = None, 0.0
    backend.remove_passage()
    stream.commit(draft.tokens)
    follow = engine._draft(prompt, stream, [], None, None)
    return {
        "arm": arm,
        "retry": backend.decode(draft.tokens).strip(),
        "retry_tokens": len(draft.tokens),
        "end": draft.end,
        "follow": backend.decode(follow.tokens).strip(),
        "logp_x": round(logp_x, 4),
        "share": round(sum(shares) / len(shares), 6) if shares else None,
        "prepare_seconds": round(prepare_seconds, 3),
        "retry_seconds": round(retry_seconds, 3),
        "computed": computed,
    }


def parity(backend: ArmBackend, state: Mapping[str, Any]) -> dict[str, Any]:
    """Greedy from the state with nothing changed: does it write X again?"""
    prepare(backend, state, "G")
    first = int(backend._torch.argmax(backend._logits).item())
    engine = InFlightGenerator(
        backend, Verifier(), max_new_tokens=MAX_NEW_TOKENS, max_sentence_tokens=MAX_SENTENCE_TOKENS
    )
    stream = _Stream(answer=list(state["committed"]), context=list(state["committed"]))
    draft = engine._draft(tuple(state["prompt"]), stream, [], None, None)
    text = backend.decode(draft.tokens).strip()
    return {
        "first_token": first == state["x"][0],
        "same_text": text == backend.decode(state["x"]).strip(),
        "greedy": text,
    }


def run_state(
    backend: ArmBackend, state: Mapping[str, Any], arms: Sequence[str], factor: float
) -> dict[str, Any]:
    out: dict[str, Any] = {"hash": state["hash"], "parity": parity(backend, state), "arms": {}}
    for arm in arms:
        out["arms"][arm] = run_arm(backend, state, arm, factor)
    backend.reset()
    return out
