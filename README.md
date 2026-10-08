# legal-rag-verifier

**Sentence-level verification for legal RAG, while the model generates.**

[![PyPI](https://img.shields.io/pypi/v/legal-rag-verifier)](https://pypi.org/project/legal-rag-verifier/)
[![CI](https://github.com/azterizm/legal-rag-verifier/actions/workflows/ci.yml/badge.svg)](https://github.com/azterizm/legal-rag-verifier/actions/workflows/ci.yml)
[![Python 3.11–3.13](https://img.shields.io/badge/python-3.11%E2%80%933.13-blue)](https://github.com/azterizm/legal-rag-verifier/blob/main/pyproject.toml)
[![Licence: AGPL-3.0-only](https://img.shields.io/badge/licence-AGPL--3.0--only-blue)](https://github.com/azterizm/legal-rag-verifier/blob/main/LICENSE)
![Runtime dependencies: none](https://img.shields.io/badge/runtime%20dependencies-none-brightgreen)

`legal-rag-verifier` checks each sentence of an answer against the statutory provisions it was
given, as the sentence is written. A deterministic claim check covers figures, dates, citations,
instrument titles, modal verbs and qualifiers; an NLI head (DeBERTa-v3) covers the prose. A
rejected sentence is rolled back and regenerated on the inference server's prefix cache, so only
that sentence is thrown away. The retry can insert the provision the sentence was checked against
at the cut point, which is what makes a small model recover.

**Status: proof of concept.** The mechanism holds on a production inference server; the full loop is
not yet production-ready. The [verdict](https://github.com/azterizm/legal-rag-verifier/blob/main/docs/VERDICT.md) states what holds, what does not and
what is required first.

Built by [Abdullah Memon](https://memonsystems.com) at [Memon Systems Ltd](https://memonsystems.com).
Layer 4 of the Memon Systems hosted reference architecture, after
[`legal-rag-router`](https://github.com/azterizm/legal-rag-router), which can serve as its
abstention gate.

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
[`docs/API.md`](https://github.com/azterizm/legal-rag-verifier/blob/main/docs/API.md).

## Evidence

Every figure below is measured. Figures: [`docs/measurements.md`](https://github.com/azterizm/legal-rag-verifier/blob/main/docs/measurements.md).
Methods, fixed before each run: [`docs/GRID.md`](https://github.com/azterizm/legal-rag-verifier/blob/main/docs/GRID.md). Raw results:
[`results/`](https://github.com/azterizm/legal-rag-verifier/tree/main/results).

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
question. Restating the question in the inserted turn recovers part of that loss. See
[`docs/VERDICT.md`](https://github.com/azterizm/legal-rag-verifier/blob/main/docs/VERDICT.md) for the proof-of-concept verdict and its limits.

## Reproduce the evidence

The repository, not the package, holds everything behind the figures: the batteries and their
seals (`batteries/`), the per-provision enrichment (`enrichment/`), every answer, trace and
judgement (`results/`) and the scripts that produced them (`scripts/`). The rollback-point tables
and the placement and attention report re-derive from the committed results, with no GPU or API
key:

```bash
git clone https://github.com/azterizm/legal-rag-verifier && cd legal-rag-verifier && uv sync
uv run python scripts/grid_inject.py --cells 4B 4B-inject 4B-inject-v2
uv run python scripts/replay_report.py
```

Re-scoring the grid (`scripts/grid_score.py`) and re-running the batteries also need the statute
corpus, built with [`legal-rag-router`](https://github.com/azterizm/legal-rag-router) and copied
to `data/`; it is not redistributed here. Generation runs used Modal (`scripts/modal_m4.py`).

## Development

```bash
uv sync
uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest
```

Progress and decisions: [`docs/ROADMAP.md`](https://github.com/azterizm/legal-rag-verifier/blob/main/docs/ROADMAP.md). Contributing:
[`CONTRIBUTING.md`](https://github.com/azterizm/legal-rag-verifier/blob/main/CONTRIBUTING.md). Security: [`SECURITY.md`](https://github.com/azterizm/legal-rag-verifier/blob/main/SECURITY.md).

## Citation

If you use the verifier or its evaluation, cite it with [`CITATION.cff`](https://github.com/azterizm/legal-rag-verifier/blob/main/CITATION.cff)
("Cite this repository" on GitHub).

## Consultancy

`legal-rag-verifier` is built and maintained by **Abdullah Memon** at
**[Memon Systems Ltd](https://memonsystems.com)**, which designs and audits retrieval systems for
legal and other regulated domains. For help putting verification into production or testing your
own legal RAG, see [engagements](https://memonsystems.com/engagements) or write to
abdullah@memonsystems.com.

## Licence

AGPL-3.0-only (see [`LICENSE`](https://github.com/azterizm/legal-rag-verifier/blob/main/LICENSE)). Contains public sector information licensed under the
Open Government Licence v3.0 (see [`NOTICE`](https://github.com/azterizm/legal-rag-verifier/blob/main/NOTICE)).
