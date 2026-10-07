# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - unreleased

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
  injection A/B; the placement and attention replay. Proof-of-concept verdict: `docs/VERDICT.md`.
