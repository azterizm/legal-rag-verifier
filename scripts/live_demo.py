"""Live M3 run: a local generator answers about ERA 1996 s.124, verified sentence by sentence.

Usage:
  uv run python scripts/live_demo.py [--model GEN_MODEL_ID] [--device mps] [--nli base|small|none]
      [--steering allow ban] [--max-new-tokens 200]

The premise is the committed fixture (real s.124 text) plus the 2026 uprating as a fact window,
linearised with its in-force date and amending S.I. First the rollback invariant is checked on the
real model (argmax and tolerance, since MPS 4-bit is not bit-exact), then each query is answered
once per steering mode on the same prompt. Traces go to results/live-demo-<steering>.json;
development figures only, no published rate (plan decision 4).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from conftest import (  # type: ignore[import-not-found]  # noqa: E402
    S124_FACTS,
    SI_2026_310,
    load_fixture,
)

from legal_rag_verifier.engine import InFlightGenerator  # noqa: E402
from legal_rag_verifier.premise import Premise  # noqa: E402
from legal_rag_verifier.verifier import NLIScorer, Verifier  # noqa: E402

DEFAULT_MODEL = "unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit"
NLI_MODELS = {
    "small": "cross-encoder/nli-deberta-v3-small",
    "base": "cross-encoder/nli-deberta-v3-base",
}
QUERIES = (
    "What is the maximum compensatory award for unfair dismissal, and where is it set?",
    (
        "Does the limit on the compensatory award apply if the employee was dismissed for "
        "whistleblowing?"
    ),
)


INJECTED = "The maximum compensatory award is £85,000."


class Injecting:
    """A backend whose first decode call returns ``INJECTED``, as if the model had written it."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.name, self.model_id = inner.name, inner.model_id
        self.chat, self.encode, self.decode = inner.chat, inner.encode, inner.decode
        self.pending = True

    def extend(self, committed: Any, **kwargs: Any) -> Any:
        if not self.pending:
            return self.inner.extend(committed, **kwargs)
        from legal_rag_verifier.engine import Segment  # noqa: PLC0415

        self.pending = False
        tokens = self.inner.encode(INJECTED)
        return Segment(tokens, INJECTED, "stop", 0, 0)


def invariant(backend: Any, prompt: tuple[int, ...]) -> dict[str, Any]:
    """Rollback-then-extend vs a fresh prefill of the same prefix, on the real model."""
    from legal_rag_verifier.backends.hf import HFBackend  # noqa: PLC0415

    backend.reset()
    first = backend.extend(prompt, stop=(), max_new=12, constraint=None)
    backend.next_logits((*prompt, *first.tokens))  # the cache now holds 12 decoded tokens
    rolled, hit = backend.next_logits(prompt)
    fresh_backend = HFBackend(backend.model, backend.tokenizer, model_id=backend.model_id)
    fresh, _ = fresh_backend.next_logits(prompt)
    diff = float((rolled - fresh).abs().max())
    return {
        "argmax_equal": int(rolled.argmax()) == int(fresh.argmax()),
        "max_abs_logit_diff": diff,
        "prefix_cache_hit_tokens": hit,
        "prompt_tokens": len(prompt),
    }


def summary(answer: Any) -> None:
    for i, sentence in enumerate(answer.trace["sentences"]):
        print(
            f"  [{i}] {sentence['outcome']:8} rollbacks={sentence['rollbacks']}  {sentence['text']}"
        )
        for attempt in sentence["attempts"]:
            verdict = attempt["verdict"]
            if verdict["verdict"] == "ROLLBACK":
                print(
                    f"      ✗ {', '.join(verdict['reasons'])}: {verdict['text']}"
                    f"  (discarded {attempt['tokens_discarded']} tokens)"
                )
    totals = answer.trace["totals"]
    print(
        f"  totals: rollbacks {totals['rollbacks']}, refused {totals['refused']}, "
        f"discarded {totals['tokens_discarded']} tokens, "
        f"decode {totals['decode_latency_ns'] / 1e9:.1f} s, "
        f"claim check {totals['claim_latency_ns'] / 1e6:.1f} ms, "
        f"NLI {totals['nli_latency_ns'] / 1e6:.0f} ms"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=os.environ.get("GEN_MODEL_ID", DEFAULT_MODEL))
    parser.add_argument("--device", default=None)
    parser.add_argument("--nli", choices=["none", *NLI_MODELS], default="base")
    parser.add_argument("--steering", nargs="+", choices=["allow", "ban"], default=["allow", "ban"])
    parser.add_argument("--max-new-tokens", type=int, default=200)
    parser.add_argument("--injected-only", action="store_true", help="skip the plain queries")
    args = parser.parse_args()

    from legal_rag_verifier.backends.hf import HFBackend  # noqa: PLC0415

    premise = Premise.from_records(
        load_fixture("era1996_s124.jsonl"), facts=S124_FACTS, extra_titles=[SI_2026_310]
    )
    backend = HFBackend.load(args.model, args.device)
    print(f"generator {backend.model_id} on {backend.device}", flush=True)
    scorer: NLIScorer | None = None
    if args.nli != "none":
        from legal_rag_verifier.nli import SentenceNLIVerifier  # noqa: PLC0415

        scorer = SentenceNLIVerifier(NLI_MODELS[args.nli], args.device)
    verifier = Verifier(scorer)

    prompt = backend.chat([{"role": "user", "content": QUERIES[0]}])
    inv = invariant(backend, prompt)
    print("rollback invariant:", json.dumps(inv), flush=True)

    out = ROOT / "results"
    for steering in args.steering:
        engine = InFlightGenerator(
            backend, verifier, steering=steering, max_new_tokens=args.max_new_tokens
        )
        runs = []
        for query in () if args.injected_only else QUERIES:
            backend.reset()
            answer = engine.generate_verified(query, premise)
            print(f"\n[{steering}] Q: {query}\nA: {answer.text}", flush=True)
            summary(answer)
            runs.append({"query": query, "answer": answer.text, "trace": answer.trace})
        # Injected failure: the first sentence states £85,000 (absent from the premise).
        backend.reset()
        injected = InFlightGenerator(
            Injecting(backend), verifier, steering=steering, max_new_tokens=args.max_new_tokens
        )
        answer = injected.generate_verified(QUERIES[0], premise)
        print(
            f"\n[{steering}, injected {INJECTED!r}] Q: {QUERIES[0]}\nA: {answer.text}", flush=True
        )
        summary(answer)
        runs.append(
            {
                "query": QUERIES[0],
                "injected": INJECTED,
                "answer": answer.text,
                "trace": answer.trace,
            }
        )
        path = out / f"live-demo-{steering}{'-injected' if args.injected_only else ''}.json"
        path.write_text(
            json.dumps({"invariant": inv, "runs": runs}, indent=1, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"trace → {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
