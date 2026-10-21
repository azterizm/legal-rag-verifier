# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- `legal_rag_verifier.__version__` reads the installed package version. It said `0.1.0.dev0` in 0.2.0.

### Changed
- Python 3.14 is tested in CI and listed in the classifiers.

### Added
- `docs/RESEARCH.md`: an index of the evaluation. Each test with its method, figures, scripts and
  results.

### Evaluation
- Stops 67 to 72, in `scripts/` and not in the package: retries after a real error and edits to the
  KV cache; the live loop on 240 questions with three generators, closed-book and with the source
  in the prompt; the 7B and 27B loops against Gemini 3.8 Flash and Claude Opus 4.6. No package
  change. Figures in `docs/measurements.md`, methods in `docs/GRID.md`.
- Stop 73, in `scripts/consens.py`: Iris.ai's ConSens per sentence, Llama 3.2 1B on one L40S,
  against the LLM judge on the second fresh test. No package change.

## [0.2.0] - 2026-10-13

### Added
- `VerifierConfig.ungrounded_figure` (`"rollback"` by default, or `"judge"`): with `"judge"` a
  sentence whose only failed claims are figures not found in the source goes to the entailment
  check, which decides. Recorded in every trace's config.

### Fixed
- A list number followed by text ("1. The employee ...") no longer ends a sentence, and a list
  number at the start of a text is not read as a figure claim.

### Evaluation
- An LLM judge in the entailment check's place, in `scripts/` and not in the package: Qwen 27B at
  4 bits as generator and judge on one SGLang server. Two hand-graded tests (354 and 151
  sentences), the live loop on 40 questions, a 1B judge trained on its labels
  ([adapters](https://huggingface.co/azterizm/minicpm5-1b-clause-judge)) and two hosted decision
  APIs as the judge. Figures in `docs/measurements.md`, methods in `docs/GRID.md`.
- `docs/VERDICT.md` now states both findings: the loop with the DeBERTa head as the auditor, and
  with the LLM judge.

## [0.1.0] - 2026-10-08

The first release: sentence-level verification during generation for legal RAG, United Kingdom,
English.

### Added
- `Premise`: the provisions an answer must be grounded in, as windows with coordinates, declared
  citations, instrument titles and temporal facts (`from_records`, `from_provision`, `from_text`).
- `Verifier`: a deterministic claim check (figures, dates, durations, citations, instrument titles,
  modal verbs, qualifiers, versions) followed by an optional NLI head, per sentence
  (`check_sentence`) or over a whole answer (`check_text`). Every verdict carries its reasons, the
  windows it was aligned to and a same-type repair where one exists.
- `SentenceNLIVerifier` (`[nli]` extra): DeBERTa-v3 cross-encoder, batched over premise windows,
  labels read from the model's `id2label`.
- Premise enrichment: an offline layer of per-provision elements and thresholds, each tied to a
  verbatim quote, attached to the windows the NLI head scores.
- `InFlightGenerator`: one request per sentence; a rejected sentence is rolled back and retried at
  most three times (eight per answer), then replaced by a fixed refusal. Retry modes: `allow`
  (constrain a rejected figure to grounded values), `ban` (restart without the rejected first
  token) and `inject` (insert the provision the sentence was checked against at the cut point and
  regenerate; `inject_template` may restate the question with `{query}`). Canonical per-sentence
  trace.
- Backends: Hugging Face transformers (`[hf]`, `DynamicCache` rollback) and SGLang (stdlib HTTP
  client; rollback is a prefix-cache hit; constraints applied by a server-side logit mask).
- Evaluation, all in `docs/measurements.md`: a dev battery (271 rows) and a held-out battery (346
  rows) sealed before it ran; the 2x2 grid (Gemini and Qwen 2.5 7B, full retry against
  sentence-level remediation, 103 test prompts, one shared detector, an independent judge); the
  injection A/B; the placement and attention replay; injection v2 (question restated in the inserted
  turn, `legal-rag-router` as the abstention gate). Proof-of-concept verdict: `docs/VERDICT.md`.

[0.2.0]: https://github.com/azterizm/legal-rag-verifier/releases/tag/v0.2.0
[0.1.0]: https://github.com/azterizm/legal-rag-verifier/releases/tag/v0.1.0
