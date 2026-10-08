# legal-rag-verifier

**Sentence-level verification for legal RAG, while the model generates.**

`legal-rag-verifier` checks each sentence of an answer against the statutory provisions it was
given, as the sentence is written. A deterministic claim check covers figures, dates, citations,
instrument titles, modal verbs and qualifiers; an NLI head (DeBERTa-v3) covers the prose. A
rejected sentence is rolled back and regenerated on the inference server's prefix cache, so only
that sentence is thrown away. The retry can insert the provision the sentence was checked against
at the cut point, which is what makes a small model recover.

Built by [Abdullah Memon](https://memonsystems.com) at Memon Systems Ltd. Layer 4 of the Memon
Systems hosted reference architecture, after [`legal-rag-router`](https://github.com/azterizm/legal-rag-router).

## Install

```bash
pip install legal-rag-verifier            # claim check only: no runtime dependencies
pip install "legal-rag-verifier[nli]"     # + DeBERTa-v3 NLI head (torch, transformers)
pip install "legal-rag-verifier[sglang]"  # + client for an SGLang server (tokenizer only)
pip install "legal-rag-verifier[hf]"      # + in-process Hugging Face generation
```

Python 3.11 or later. English and United Kingdom legislation in 0.1.0.

## Check a sentence

```python
from legal_rag_verifier.premise import Premise
from legal_rag_verifier.verifier import Verifier

premise = Premise.from_text(
    "The limit of a compensatory award is the lower of £123,543 and 52 multiplied by a week's pay.",
    titles=("Employment Rights Act 1996",),
    citations=("s124",),
)
verifier = Verifier()  # Verifier(SentenceNLIVerifier("cross-encoder/nli-deberta-v3-base")) adds NLI

verdict = verifier.check_sentence(premise, "The compensatory award is capped at £85,000.")
verdict.verdict  # Verdict.ROLLBACK
verdict.reasons  # (Reason.UNGROUNDED_FIGURE,)
verdict.ungrounded  # ['£85,000']
```

`check_text` runs the same checks over a whole answer, for post-hoc use.

## Generate with rollback

```python
from legal_rag_verifier.backends.sglang import SGLangBackend
from legal_rag_verifier.engine import InFlightGenerator
from legal_rag_verifier.nli import SentenceNLIVerifier

backend = SGLangBackend.connect("http://127.0.0.1:30000", "Qwen/Qwen2.5-7B-Instruct")
generator = InFlightGenerator(
    backend,
    Verifier(SentenceNLIVerifier("cross-encoder/nli-deberta-v3-base")),
    steering="inject",
)
answer = generator.generate_verified("What is the cap on the compensatory award?", premise)
answer.text  # the verified answer
answer.trace  # per sentence: verdicts, retries, what was inserted, prefix-cache hits, timings
```

The engine sends one request per sentence. A rejected sentence is not resubmitted, so the next
request reuses the verified prefix from the server's cache (SGLang's RadixAttention). Each sentence
gets at most three retries and each answer at most eight; after that the engine writes a fixed
refusal for that point and moves on. Retry modes:

- `allow`: constrain a rejected figure to the grounded values of the same type, then `ban`;
- `ban`: restart the sentence with its rejected first token banned;
- `inject`: insert the provision the sentence was checked against at the cut point (a new user
  turn; `inject_template`, which may restate the question with `{query}`) and regenerate. The
  provision stays in the context and never enters the answer.

The SGLang server needs `--enable-custom-logit-processor` for `allow` and `ban`. Full API:
[`docs/API.md`](docs/API.md).

## Evidence

Every figure below is measured; methods and raw results are in [`docs/`](docs/) and `results/`.

**Detector, sealed held-out battery** (346 rows, sealed before it ran once; claim check +
`nli-deberta-v3-base` + enrichment): 80.0 % of planted errors caught (124/155), 7.9 % of correct
sentences rolled back (15/191), 89.2 % rollback precision. Weakest: dropped qualifiers (6/18).

**Rollback on Qwen 2.5 7B, SGLang, one NVIDIA L4:** every retry reused the verified prefix from the
cache. A retry request costs 117 ms in bf16 (69 ms in FP8), against 270 ms (170 ms) to re-prefill.
Checking sentence by sentence released the first verified sentence after 3.8 s, against 8.1 s when
the whole answer was checked first.

**Inserting the provision at the cut point** (48 rejected sentences retried from the same state):
the retry passed the auditor 39 times with the provision inserted, against 19 with decode-level
steering (exact McNemar p = 1.1e-5). The same text at the top of the prompt passed 17 of 46; a new
turn without the provision, 14. With the provision inserted, the regenerated sentence became more
likely in 46 of 46 states, the rejected sentence less likely in 45 of 46, and attention on
provision text rose in 46 of 46.

**Open:** the inserted provision makes the model faithful to the provision, not always to the
question. Restating the question in the inserted turn recovers part of that loss. See [`docs/VERDICT.md`](docs/VERDICT.md) for the proof-of-concept verdict and its
limits.

## Development

```bash
uv sync
uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest
```

Progress and decisions: [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Licence

AGPL-3.0-only (see `LICENSE`). Contains public sector information licensed under the Open
Government Licence v3.0 (see `NOTICE`).
