"""Stop 67: the cache edits of the retry arms, on a tiny random Qwen2 from a config (CPU, fp32)."""

from __future__ import annotations

import math
from typing import Any

import pytest

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")

from scripts import kv_retry as kv  # noqa: E402

pytestmark = [pytest.mark.torch]
VOCAB = 400


class CharTokenizer:
    """One token per character, so any id decodes."""

    eos_token_id = 2
    chat_template = None

    def __call__(self, text: str, *, add_special_tokens: bool = False) -> dict[str, list[int]]:
        return {"input_ids": [ord(c) % VOCAB for c in text]}

    def decode(self, ids: list[int], *, skip_special_tokens: bool = True) -> str:
        return "".join(chr(i) for i in ids if i > 2)


def tiny(*, attention: str = "eager") -> Any:
    config = transformers.Qwen2Config(
        vocab_size=VOCAB,
        hidden_size=64,
        intermediate_size=128,
        num_hidden_layers=2,
        num_attention_heads=4,
        num_key_value_heads=2,
        max_position_embeddings=4096,
        attn_implementation=attention,
    )
    torch.manual_seed(0)
    return transformers.Qwen2ForCausalLM(config).float().eval()


@pytest.fixture(scope="module")
def backend() -> kv.ArmBackend:
    model = tiny()
    kv.install(model)
    return kv.ArmBackend(model, CharTokenizer(), model_id="tiny")


STATE: dict[str, Any] = {
    "hash": "h",
    "prompt": list(range(100, 140)),
    "committed": list(range(200, 212)),
    "x": list(range(300, 310)),
    "x_turn": list(range(301, 310)),
    "turn": list(range(50, 70)),
    "turn_span": [5, 15],
    "passage": list(range(150, 165)),
    "far_at": 10,
    "b_seed": [],
    "b_constraint": {"ban": [300]},
}


def test_the_attention_function_gives_the_model_s_own_logits() -> None:
    ids = torch.tensor([list(range(100, 160))])
    reference = tiny(attention="sdpa")(input_ids=ids).logits
    model = tiny()
    kv.install(model)
    assert torch.allclose(model(input_ids=ids).logits, reference, atol=1e-4)


def test_rotated_keys_equal_keys_computed_at_that_position(backend: kv.ArmBackend) -> None:
    tokens = STATE["passage"]
    alone = backend.alone(tokens)
    backend.reset()
    backend.pos = 37
    backend.feed(tokens)
    for (k, _), layer in zip(alone, backend._cache.layers, strict=True):
        assert torch.allclose(kv.rotate(backend.model, k, 37), layer.keys, atol=1e-4)
    back = kv.rotate(backend.model, kv.rotate(backend.model, alone[0][0], 37), -37)
    assert torch.allclose(back, alone[0][0], atol=1e-4)


def test_a_spliced_passage_removed_leaves_the_stream_with_a_gap(backend: kv.ArmBackend) -> None:
    stream = [*STATE["prompt"], *STATE["committed"]]
    n = len(STATE["passage"])
    kv.prepare(backend, STATE, "K")
    assert backend.slots() == len(stream) + n
    assert backend.passage == (len(stream) - 1, len(stream) - 1 + n)
    backend.remove_passage()
    logits, _ = backend.next_logits(stream)
    assert backend.slots() == len(stream)
    reference = kv.ArmBackend(backend.model, CharTokenizer(), model_id="tiny")
    reference.feed(stream[:-1])
    reference.pos += n  # the last token at the position it has after the passage
    reference.feed(stream[-1:])
    assert torch.allclose(logits, reference._logits, atol=1e-4)


def test_far_splice_moves_the_later_keys_and_keeps_the_retry_position(
    backend: kv.ArmBackend,
) -> None:
    stream = [*STATE["prompt"], *STATE["committed"]]
    n, far = len(STATE["passage"]), STATE["far_at"]
    kv.prepare(backend, STATE, "K-far")
    assert backend.passage == (far, far + n)
    assert backend._positions[far - 1] == far - 1
    assert backend._positions[far] == far + n
    assert backend.pos == len(stream) + n
    near = kv.ArmBackend(backend.model, CharTokenizer(), model_id="tiny")
    kv.prepare(near, STATE, "K")
    assert near.pos == backend.pos


def test_a_factor_of_one_is_the_plain_splice_and_a_larger_one_raises_the_share(
    backend: kv.ArmBackend,
) -> None:
    kv.prepare(backend, STATE, "K")
    plain = backend._logits.clone()
    kv.prepare(backend, STATE, "KA", math.log(1.0))
    assert torch.allclose(backend._logits, plain)
    shares = {f: kv.run_arm(backend, STATE, "KA", f)["share"] for f in (1.0, 4.0)}
    assert shares[4.0] > shares[1.0]


def test_the_likelihood_reading_leaves_the_cache_as_it_was(backend: kv.ArmBackend) -> None:
    kv.prepare(backend, STATE, "P")
    slots, logits = backend.slots(), backend._logits.clone()
    value = backend.logprob(STATE["x"])
    assert value < 0
    assert backend.slots() == slots
    assert torch.equal(backend._logits, logits)
    assert backend.logprob(STATE["x"]) == pytest.approx(value, abs=1e-4)


def test_every_arm_runs_and_the_ban_arm_avoids_x_s_first_token(backend: kv.ArmBackend) -> None:
    out = kv.run_state(backend, STATE, kv.ARMS, 2.0)
    assert set(out["arms"]) == set(kv.ARMS)
    assert not out["arms"]["B"]["retry"].startswith(chr(300))
    assert out["arms"]["B"]["share"] is None
    assert all(out["arms"][a]["share"] is not None for a in ("T", "P", "K", "K-far", "KA"))
    assert out["arms"]["K"]["computed"] < out["arms"]["P"]["computed"] + len(STATE["passage"])
    assert set(out["parity"]) == {"first_token", "same_text", "greedy"}
