# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Evaluation
- Stop 78, the live check against a real Modal server (Qwen 3.8 27B 4-bit, L40S) through the released
  0.5.0 package: PASS on all three rules. 91.4% accuracy (138/151 correct, 8 false rollbacks, 62 caught;
  stop 61 was 136/151), 0 errors in 141 calls, server-side p50 0.58 s (client p50 1.28 s from Pakistan to
  Modal us-east; baseline round trip 0.71 s). Spend $1.41. answer-check-mcp live smoke on the same server: PASS.

## [0.5.0] - 2026-11-02

### Added
- `legal_rag_verifier.judge`: the LLM judge behind the README's results, as a package module. It
  is stdlib only and calls any OpenAI-compatible `/v1/chat/completions` endpoint. The measured
  prompt is fixed, and its hashes are checked at import.
- `OpenAIChat`, the HTTP client; `Judge`, the entailment check, built by hand or with
  `Judge.from_preset(name, base_url)`; `JudgedVerifier`, which gives each sentence's prompt all
  earlier sentences in `check_text` (post-hoc) and only the emitted sentences in the engine path
  (live), cleared by `reset()` between answers; `PRESETS`, with one measured preset,
  `"qwen27-ar4"` (Qwen3.8 27B at 4 bits on SGLang); and `STRICT_FIGURES`, the config it was
  measured with.
- The judge keeps its own call log, one record per call, read from `JudgedVerifier.calls`. The
  trace does not change.
- At most 3 attempts per prompt, shared by transport failures and replies that do not parse. After
  the third the sentence is scored not stated, so a judge that cannot be reached rolls back every
  sentence under `STRICT_FIGURES`.
- The API key is read from an environment variable at call time. It appears in no repr, call
  record or exception text, and is never sent across a redirect: redirects are not followed.
- Any other model, sampling, prompt or config is unmeasured.

### Changed
- Building `SentenceNLIVerifier` emits a `UserWarning`. The DeBERTa head did not improve answers:
  58.3%–68.7% on two hand-graded tests (software and UK statutes), vs 90.1%–93.8% for the LLM
  judge. See `docs/VERDICT.md`.
- `SGLangBackend` raises an `ImportError` when steering `allow` or `ban` cannot build its logit
  mask. It says what to do: install `torch` and `sglang` on the client (the `[sglang]` extra
  installs neither), pass a mask built elsewhere as `processor=`, or use `steering="inject"`.
  Before, a bare `ModuleNotFoundError` was raised mid-answer. The README and `docs/API.md` now
  state the requirement.

### Evaluation
- Stop 77, a free replay test (`tests/test_judge_replay.py`): a fake endpoint serves the recorded
  labels by prompt hash, and the package's `JudgedVerifier` reproduces the published judge figures
  exactly: 90.1% (136/151) on the second fresh test and 93.8% (332/354) on the first. Every prompt
  the package sends is recorded (140 and 347 unique, none unknown). The test runs only where the
  local results and corpus exist, and skips elsewhere.
- The paid live check against a real server is not yet run.

## [0.4.0] - 2026-10-23

### Added
- `VerifierConfig(totals="line")`, off by default: a money figure equal to two money figures of
  one currency on one line of the source, added, is grounded, unless either is inside brackets
  on that line. An offer's price plus its shipping ("€903.99 + €4.99 = €908.98") is grounded;
  its old price plus shipping, sums across lines and wrong totals are not. The config key is in
  every trace.

### Evaluation
- Stop 76, in test 1 of `product-answer-checks` (arm 2t): on Claude Opus 4.6's answers the claim
  check with totals removes 25 right sentences instead of 106 and leaves 2 answers empty instead
  of 9, but keeps 30 wrong sentences instead of 21. Each of the 9 is a correct total inside a
  wrong claim (wrong shop, or a budget). On Gemini 3.8 Flash's answers it removes 11 right
  sentences instead of 75, and keeps no wrong one. With the 1B judge after it, Opus 4.6's answers
  keep 9 wrong sentences instead of 5 and lose 114 right ones instead of 148.

## [0.3.0] - 2026-10-22

### Fixed
- `legal_rag_verifier.__version__` reads the installed package version. It said `0.1.0.dev0` in 0.2.0.

### Changed
- Python 3.14 is tested in CI and listed in the classifiers.
- The claim check reads French number, currency, date and duration formats: "279,99 €",
  "1 299,99 €", "30 heures", "5 novembre 2026" read as "€279.99", "€1,299.99", "30 hours",
  "5 November 2026". Modal verbs, qualifiers and number words stay English only.

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
- Stop 75, in `scripts/claims75.py`: the French formats change no claim in the 31,850 English
  texts of the batteries and answers, but change 4,573 of the 6.4 million texts of the UK corpus,
  mostly wrongly ("an" after a number, "£" in flattened tables, chemical locants). With
  narrower rules ("an" only when no word follows, no trailing "£" or "$", a wider guard on the
  decimal comma), and "an" read only before the end of a line, punctuation or "de", 579 change:
  every one right outside the decimal comma, which is about two-thirds right (lists, codes, glued
  tables and chemical names still misread). "0,965 kWh" reads as 0.965 (from test 1's French
  listings); 614 texts change, the new readings all right in a sample of 40.
- Test 1 of [`product-answer-checks`](https://github.com/azterizm/product-answer-checks) runs this
  release's claim check on French and English product listings.

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

[0.5.0]: https://github.com/azterizm/legal-rag-verifier/releases/tag/v0.5.0
[0.4.0]: https://github.com/azterizm/legal-rag-verifier/releases/tag/v0.4.0
[0.3.0]: https://github.com/azterizm/legal-rag-verifier/releases/tag/v0.3.0
[0.2.0]: https://github.com/azterizm/legal-rag-verifier/releases/tag/v0.2.0
[0.1.0]: https://github.com/azterizm/legal-rag-verifier/releases/tag/v0.1.0
