# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[0.3.0]: https://github.com/azterizm/legal-rag-verifier/releases/tag/v0.3.0
[0.2.0]: https://github.com/azterizm/legal-rag-verifier/releases/tag/v0.2.0
[0.1.0]: https://github.com/azterizm/legal-rag-verifier/releases/tag/v0.1.0
