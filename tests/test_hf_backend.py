"""HF backend: the rollback invariant on a cached tiny random Llama (CPU, fp32).

After a rollback the cache must be exactly what a fresh prefill of the committed prefix gives:
the next-token logits and the greedy continuation must match. Skipped without torch or weights.
"""

from __future__ import annotations

from typing import Any

import pytest

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")

from legal_rag_verifier.backends.hf import HFBackend  # noqa: E402
from legal_rag_verifier.engine import Allow, Ban, InFlightGenerator  # noqa: E402
from legal_rag_verifier.premise import Premise  # noqa: E402
from legal_rag_verifier.verifier import Verifier  # noqa: E402

pytestmark = [pytest.mark.torch, pytest.mark.model]
TINY = "hf-internal-testing/tiny-random-LlamaForCausalLM"


class CharTokenizer:
    """Stand-in for the checkpoint's sentencepiece tokenizer: one token per character."""

    eos_token_id = 2
    chat_template = None

    def __call__(self, text: str, *, add_special_tokens: bool = False) -> dict[str, list[int]]:
        return {"input_ids": [ord(c) % 32000 for c in text]}

    def decode(self, ids: list[int], *, skip_special_tokens: bool = True) -> str:
        return "".join(chr(i) for i in ids if i > 2)


@pytest.fixture(scope="module")
def model() -> Any:
    try:
        loaded = transformers.AutoModelForCausalLM.from_pretrained(
            TINY, local_files_only=True, dtype=torch.float32
        )
    except OSError:
        pytest.skip(f"{TINY} is not in the local cache")
    torch.manual_seed(0)
    return loaded


def backend(model: Any) -> HFBackend:
    return HFBackend(model, CharTokenizer(), model_id=TINY)


PROMPT = tuple(range(100, 140))
COMMITTED = (*PROMPT, *range(200, 212))
REJECTED = tuple(range(300, 318))


def test_rollback_then_extend_matches_a_fresh_prefill(model: Any) -> None:
    rolled = backend(model)
    rolled.next_logits((*COMMITTED, *REJECTED))  # the cache now holds a rejected sentence
    after, hit = rolled.next_logits(COMMITTED)  # rollback: truncate to the committed prefix
    fresh, fresh_hit = backend(model).next_logits(COMMITTED)
    assert hit == len(COMMITTED) - 1
    assert fresh_hit == 0
    assert torch.allclose(after, fresh, atol=1e-6, rtol=0)
    assert int(after.argmax()) == int(fresh.argmax())


def test_greedy_continuation_after_rollback_equals_fresh(model: Any) -> None:
    rolled = backend(model)
    rolled.extend(COMMITTED, stop=(), max_new=15, constraint=None)
    rolled.next_logits((*COMMITTED, *REJECTED))
    again = rolled.extend(COMMITTED, stop=(), max_new=15, constraint=None)
    fresh = backend(model).extend(COMMITTED, stop=(), max_new=15, constraint=None)
    assert again.tokens == fresh.tokens
    assert again.prefix_cache_hit_tokens == len(COMMITTED) - 1


def test_extending_a_committed_sentence_reuses_the_whole_prefix(model: Any) -> None:
    hf = backend(model)
    first = hf.extend(COMMITTED, stop=(), max_new=6, constraint=None)
    second = hf.extend((*COMMITTED, *first.tokens), stop=(), max_new=6, constraint=None)
    assert second.prefix_cache_hit_tokens == len(COMMITTED) + len(first.tokens) - 1
    fresh = backend(model).extend((*COMMITTED, *first.tokens), stop=(), max_new=6, constraint=None)
    assert second.tokens == fresh.tokens


def test_constraints_mask_the_logits(model: Any) -> None:
    hf = backend(model)
    free = hf.extend(COMMITTED, stop=(), max_new=3, constraint=None)
    banned = hf.extend(COMMITTED, stop=(), max_new=1, constraint=Ban(frozenset({free.tokens[0]})))
    assert banned.tokens[0] != free.tokens[0]
    forced = hf.extend(COMMITTED, stop=(), max_new=5, constraint=Allow(((7001, 7002, 7003),)))
    assert forced.tokens[:3] == (7001, 7002, 7003)


def test_engine_runs_end_to_end_on_the_hf_backend(model: Any) -> None:
    premise = Premise.from_text("The limit of a compensatory award is £123,543.")
    engine = InFlightGenerator(backend(model), Verifier(), max_new_tokens=40)
    answer = engine.generate_verified("What is the limit?", premise)
    assert answer.trace["backend"] == "hf"
    assert answer.trace["model"] == TINY
    assert (
        answer.trace["answer_tokens"] <= 40 + len(engine.backend.encode(" " + engine.refusal)) * 3
    )
    assert answer.trace["stop_reason"] in {"eos", "length", "rollback_budget"}
