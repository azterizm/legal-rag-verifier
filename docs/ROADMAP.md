# Phase 3 Roadmap — `legal-rag-verifier` 0.1.0

Source of truth: `docs/PLAN.md` (copy of `~/.claude/plans/polymorphic-questing-barto.md`, the **plan**), and in
the vault `26 Sept - Hosted Reference Architecture/` docs **04** (verifier spec), **05** (integration imports),
**07 §5** (2×2 grid) and **10 §2–3** (Phase 3 build order, risks).

Legend: 🧑 = needs you (an account, hardware, money or approval) · ⛔ = halt point: I stop and ask before going on.

> **This file is the single record of progress and decisions.** Update **§S Status** at every stop.

---

## S. Status

| Field | Value |
|---|---|
| Last updated | 2026-10-03 |
| Current stage | Phase 3, Mac session (M1–M3) |
| Current milestone | **M1 ✅ built — ⛔ API review** |
| Next step | M2 (NLI head + dev battery) after your go on the M1 API (`docs/API.md`) |
| Waiting on you | ⛔ M1 API review: names in `docs/API.md` §5 (reason codes, `Repair`, `GroundedBy`, `align_ratio`) |
| Blocked | Nothing |

### Stop log
Newest first. One line per stop: what was finished, and where to resume.

- 2026-10-03 (1): **M1 built; halted for the API review (⛔).**
  - Setup: repo scaffolded on the router's conventions (uv, hatchling, src layout, AGPL-3.0-only, ruff rule
    set, mypy --strict, pytest + hypothesis). Python 3.12 pinned locally (`.python-version`) for torch wheels.
  - Data (R9): `uk_scrap_data/` (134,221 files, 1.1 GB) and the router's `data/uk/` (134,220 files, 3.9 GB)
    copied, git-ignored, `diff -rq` clean against the router. `data/MANIFEST.json` (OGL v3.0) committed.
    The router's sealed batteries copied unchanged to `batteries/router/` with `SOURCE.json`: router commit
    `65fb6e4`, seal tags `battery-seal-2026-09-29-v2` (uk/*.jsonl) and `concept-seal-2026-09-29`
    (concept/uk.jsonl); every SHA-256 matches its seal file.
  - M1: claim check, legal-aware segmenter, `Premise` (tree windows, R10; temporal facts), `Verifier.check_text`
    (R5), query grounding (R4), dropped-qualifier check (R2), window-scoped figures/modals (R3). 115 tests
    (golden + hypothesis) pass; ruff and mypy --strict clean; coverage 89 % of `src/` (NLI paths come in M2).
  - Found while building: top-2 lexical alignment with no floor admits a weak second window and hides value
    swaps on short premises. Added `align_ratio=0.5` (a lower window must score ≥ half the best). It is a
    config parameter recorded in the trace; M2 calibrates it on the dev split. **Needs your OK (API).**
  - Found in the data: `amendment_history` is empty for every UK record, so temporal facts (in force from,
    amended by) are supplied by the caller (`Premise.from_provision(..., in_force_from=, amended_by=)` or
    `from_records(..., facts=)`). The s.124 facts used in tests come from S.I. 2026/310 art. 1(2) and its
    Schedule (£118,223 → £123,543 from 6 April 2026), read from the copied corpus.

---

## Milestones

### M1 — Claim check + segmenter + `check_text` (CPU, stdlib) ✅ ⛔
Plan §Key decisions 2–5, R2–R5, R8, R10.
- [x] Segmenter: `.` `;` `\n` / `:`+newline; abbreviations (s., ss., art., reg., para., sch., No., Ltd., v.,
      e.g., i.e., cf.), numbers, streaming "undecided" state for a trailing `.`.
- [x] Figures: money (`£68,400` = `£68400` = `£68.4k`), percentages, dates (→ ISO), durations (number words).
- [x] Citations → coordinate tails (`s124/1ZA/a`), sibling labels, "of" chains, relative refs resolved per window;
      parent cite grounds against a child coordinate.
- [x] Instrument titles (`… Act 1996`, `S.I. 2026/310`, `ERA 1996`): unnamed instrument → ungrounded (Marchwood).
- [x] Deontic classes vs aligned windows; qualifier binding (R2); value swap (R3); query grounding (R4).
- [x] `Premise.from_records` (R10), `from_provision` (temporal facts), `from_text`.
- [x] Golden tests (£68,400 / £85,000 / £123,543; shall→may; "s. 124" not split; "section 124" = "s.124";
      `QUALIFIER_DROPPED`; query figure grounded) and hypothesis fuzz.
- **Done when:** checks green ✅ · ⛔ API reviewed.

### M2 — NLI head + dev battery (`[nli]`)
- [ ] `legal_rag_verifier.nli.SentenceNLIVerifier` implementing `NLIScorer`: batched `[window, hypothesis]`,
      MPS/CUDA/CPU, MPS-synchronised timing, `id2label` read from the model config.
- [ ] Long windows split to fit 512 tokens (sub-windows keep their coordinate).
- [ ] Latency p50/p99 on M4 for `-small` and `-base` → `docs/measurements.md`.
- [ ] Dev detector battery (R1): ~150 rows from real provisions (router concept `dev` split, R11), classes:
      grounded paraphrase, connective, wrong figure, wrong citation, wrong instrument, modal shift, dropped
      qualifier, value swap, unsupported-but-plausible. Rows written independently of the checker's patterns.
- [ ] ⛔ **You review/correct the labels before any threshold is calibrated.**
- [ ] Calibrate on dev only: thresholds, `align_ratio`, neutral policy (R7), small vs base. Headline:
      false-rollback rate on grounded paraphrases, recall per class.

### M3 — Engine + HF backend
- [ ] `engine.InFlightGenerator(backend, verifier, max_rollbacks=2, max_total_rollbacks, refusal)`;
      `generate_verified(query, premise) -> Answer(text, trace)`.
- [ ] `Backend` protocol (`extend(committed, stop, max_new, constraint) -> Segment`); `Constraint` = `Ban` | `Allow`.
- [ ] `backends/hf.py`: `DynamicCache` aligned to the committed prefix; truncate on reject; logits mask.
- [ ] Invariant test (tiny-random Llama, CPU): rollback-then-extend logits == fresh prefill logits.
- [ ] Scripted fake backend: ban, allow-list, refusal, trace; injected £85,000 caught and removed.
- [ ] First step: confirm bnb 4-bit Llama 3.1 8B loads and decodes on MPS (fallback Qwen2.5-3B).
- [ ] `scripts/live_demo.py` on the real s.124 premise; prints the trace.

### M4 — SGLang backend + Modal L4 spike 🧑 (spend) — later session

### Later — sealed held-out battery + 2×2 grid (07 §5), CI/GitHub, release, vault corrections (⛔ each)
