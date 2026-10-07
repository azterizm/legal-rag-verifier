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
| Last updated | 2026-10-06 |
| Current stage | Phase 3, Mac session (M1–M3) |
| Current milestone | M1 ✅ · M2 ✅ · M3 ✅ · M4 ✅ (SGLang + Modal L4 spike) |
| Next step | Your call: adjudication, judge v2, detector refinement on dev (stop 25) |
| Waiting on you | Label provenance; adjudicate 12 judge/label disagreements or not; refinement go. Vault 02 |
| Blocked | Nothing |

### Stop log
Newest first. One line per stop: what was finished, and where to resume.

- 2026-10-07 (25): **Labels in, judge run (412 calls), results written; ⛔ next steps.** Labels: 72/80 correct.
  Judge vs labels 85 %, κ 0.375 → not the headline (rule set before the run); rule A fails Qwen on citing habit.
  Results side by side in `docs/measurements.md`. 44 judge-flagged detector misses + 2 systematic gaps (query
  names a fictional provision/Act; refusals from false rollbacks) are refinement hypotheses for dev.

- 2026-10-07 (24): **Grid cells run: 4 × 103 answers; rule A scored; ⛔ your blind labels.** Modal L4 ≈ 1.5 h
  (4B + 4D); router: 4A + 4C on `gemini-3.8-flash-high` (one 503 and one interrupted session, resumed, no
  duplicates). Rule A: 4A 97.1 %, 4C 97.1 %, 4B 45.6 %, 4D 39.8 %; Qwen's misses are mostly answers that never
  name the section (4B 46, 4D 51), which rule A requires, so rule A partly measures a citing habit (the judge
  and your labels separate it). Gemini's completion tokens are ~80 % thinking: visible ≈ 18–20 tok/s, about
  Qwen-on-L4's 17. Blind sheet: `results/grid/review_sheet.md` → label `results/grid/review_labels.csv`.

- 2026-10-06 (23): **Paid grid run started (your go).** 9 enrichment calls; smoke 2 prompts/cell OK (Modal class
  parameter fix: no postponed annotations in the Modal app; Gemini usage now kept per call, since its completion
  tokens include thinking). **Independent judge decided (yours): `gpt-oss-120b-medium` via the router**, after
  rule A and your blind labels, blind to cell, raw statute text only; validity vs your labels (κ) before it is
  the headline; its sentence labels feed detector refinement on dev only. `scripts/grid_judge.py` written, not run.

- 2026-10-06 (22): **Grid decided and built, not run; ⛔ paid run.** Your choices: 103 concept `test` prompts,
  router `gemini-3.8-flash-high` for 4A/4C, rule A + a blind hand sample of 80 for scoring, bf16 Qwen.
  `docs/GRID.md` fixes the method before the run. Harness: `scripts/grid_prompts.py`, `grid_cells.py` (full
  retry, continuation, 4B record; offline tests), `grid_gemini.py` (router, local verifier), `grid_qwen.py` +
  `modal_m4.py::grid` (one SGLang server, chunked, resumable), `grid_score.py` (rule A, summary, blind sheet,
  agreement). Waiting on your go for the paid run.

- 2026-10-06 (21): **Retries, detector fixes, latency profile (your go: "retry max 3 times", steps 1–3).**
  - Engine: each point gets at most 3 retries (`max_rollbacks=3`), allow when a same-type repair exists, ban
    otherwise; the allow→ban special case is gone (it falls out of the rule). After the third failed retry the
    refusal is committed and the answer continues. Vault 05 still passes `max_rollbacks=2` (correction pending).
  - Detector, dev unchanged (5.6 / 5.7 / 85.4 / 93.3): comma titles, label numbers ("item 7"), a leading
    "Yes,"/"No," is not judged by NLI (fixes the M4 Q2 false rollback). Citation-anchored NLI tried and **not
    adopted**: no dev false rollback fixed, 2 wrong-citation catches lost. legal-rag-audit not re-run (you stopped it).
  - L4 profile (~10 min GPU): warm resubmit 117 ms bf16 / 69 ms FP8 = one non-graphed extend forward; decode
    52.9 / 30.3 ms per token; HTTP 1.5 ms; mask +7 ms. "< 30 ms" is below one forward pass of a 7B on an L4.
  - Roadmap M2 boxes ticked (done earlier).

- 2026-10-06 (20): **M4 done (your go).** SGLang 0.5.21 + Qwen 2.5 7B on one Modal L4, same engine. Every
  resubmit after a rollback is a RadixAttention hit (`cached_tokens = committed − 1`); one-token round trip
  cold 212 ms vs warm 122 ms (the < 30 ms target is not met: per-request overhead). Injected £85,000 caught in
  both modes; the allow→ban fallback ran as designed, but NLI then rolled back the fully correct rule
  (contradiction 0.96 on the s.124(1A) exception window) → refusal. Proposed: citation-anchored NLI. Fixed on
  the way: `modal run` needs `::main` once two entrypoints exist; a `check` entrypoint prints the probe.

- 2026-10-06 (19): **Date filter, allow→ban fallback, SGLang client, vault 05 (your go).**
  - NLI candidates are restricted to the versions in force on the date asked (sentence or query date) when the
    premise holds dated versions. Dev, base + enrichment: GP false rollback 7.2 → 5.6 %, all-pass 7.1 → 5.7 %,
    recall 85.4 % unchanged, precision 91.7 → 93.3 %. legal-rag-audit (timeline premise): correct in-force
    sentences kept 4/38 → 13/38. Held-out not re-run (sealed, run once).
  - Engine: a failed allow retry gets one ban retry before the refusal (the live s.124 case).
  - `backends/sglang.py`: stdlib HTTP client on `/generate`; `cached_tokens` recorded as the prefix-cache hit;
    constraints one token per request through a server-side mask (`--enable-custom-logit-processor`); tested
    offline against a fake server. `scripts/modal_m4.py` + `scripts/m4_spike.py` written, **not run**.
  - Vault 05: `InFlightGenerator(SGLangBackend.connect(…), Verifier(SentenceNLIVerifier(base)))` and
    `generate_verified(query, Premise.from_provision(…))`; the instrument title's source is open (vault 02).
  - Auto mode blocked two steps this stop; you granted them.

- 2026-10-06 (18): **M3 done: engine + HF backend.** `engine.InFlightGenerator` (request-per-sentence, allow /
  ban steering, refusal after 2 per point, canonical trace), `Backend` protocol (plus the backend's tokenizer:
  `chat`/`encode`/`decode`, needed for allow-list tokens), `backends/hf.py` (`DynamicCache` crop + re-feed of the
  last token). Llama 3.1 8B bnb 4-bit runs on MPS with serial weight loading (transformers 5.18's threaded
  loader segfaults on MPS). Segmenter: "s. " mid-stream is now undecided until the next token. An empty retry
  after a rollback is refused, not silently dropped. Live run in `docs/measurements.md`: injected £85,000
  caught both ways; ban recovered, allow fixed the figure but hit QUALIFIER_DROPPED and refused.

- 2026-10-06 (17): **legal-rag-audit live answers benchmarked, anonymised (your go).** Read-only; nothing run on
  the audit side. Targets → System A / System B; ids, tool names, timestamps, raw payloads dropped; answers kept
  local and git-ignored, extraction script (which names targets) kept outside the repo. All 3 audit FAILs caught,
  28/28 correct abstentions passed; correct dated answers heavily over-flagged (open-world context; NLI wrong on
  dated versions). Details in `docs/measurements.md`. Empty-premise guard added (NLI skipped, test).

- 2026-10-06 (16): **Held-out sealed and run (your go, "all good. proceed").** Seal `heldout-2026-10-06`
  committed before the run (`a4d9726`); run-once guard per detector. Held-out, base + enrichment: GP false rollback
  7.3 %, all-pass 7.9 %, recall 80.0 %, precision 89.2 %; claim check only 5.0 % / 5.2 % / 53.6 % / 89.3 %.
  `docs/measurements.md` has per class and by source. Step 3 done; accuracy plan closed.

- 2026-10-06 (15): **Dev confirmed with defaults (7.2 / 7.1 / 85.4 / 91.7); MPS shape fix; M2 committed.**
  Held-out enrichment finished (57 more calls; 190 total). Waiting on your held-out label review, then seal and
  run once.

- 2026-10-06 (14): **Router key:** you removed the old key file (the held-out enrichment stopped at 60/117 units)
  and supplied the key again; it is stored in this repo's `.router_key` (git-ignored, mode 600) and
  `scripts/enrich_premises.py` reads it from there. Enrichment resumed from the cache.

- 2026-10-06 (13): **Held-out drafted (346 rows, 102 premises), seal tooling written; ⛔ label review.**
  - 312 concept rows from 91 `test` queries + 34 anchor/probe rows; no provision, query or sentence shared with
    dev; all excerpts verified verbatim. Enrichment for the held-out premises (117 units) generated with the
    same pipeline and model (step 3, approved). `batteries/verifier/seal.py` + a sealed-and-run-once guard in
    `scripts/run_battery.py`.

- 2026-10-06 (12): **Defaults baked in (your go); step 3 started. Split leak found and contained.**
  - Default verifier = clause-split NLI (denials dropped), P2 (`VerifierConfig.neutral_with_grounded_claim`,
    default "emit", in the trace), "as at" check (`VERSION_MISMATCH`), list-item binding, enrichment elements
    as NLI candidates (`enrichment.load` / `attach`; `Premise.enrichment` names the layer; `NLIResult.candidate`
    says what a sentence was judged on). Experimental switches and `scripts/ablate_battery.py` removed (results
    kept in `results/ablate-*.json`). Fixed while baking: "before 6 April 2026" now means the day before.
  - **Split leak (R11):** the router's concept `test` split contains the rag-security-probes queries
    (uk-concept-0204…0215). Six of them (CHIM-001/002, OOB-001, FAB-001/002/003 = 0210, 0211, 0213, 0204, 0205,
    0206) were used for **dev** rows at stop 6 and shaped the clause/denial changes. They are treated as seen:
    kept in dev, **excluded from held-out**. The five probe prompts already in the held-out draft (0208, 0209,
    0212, 0214, 0215) are genuinely test-split. Held-out concept rows are drafted from the other 91 test queries.

- 2026-10-06 (11): **Steps 1 and 2 measured on dev; halted for the default configuration (⛔ API).**
  - Step 1 ablation and step 2 layer (73 router calls to `gemini-3.8-flash-high`, chat endpoint only; elements
    99.4 % verified, thresholds 71 %). Best on dev: base + clauses + p2 + as_at + limb_check + elements —
    GP false rollback 13.6 → 7.2 %, all-pass 16.3 → 7.1 %, precision 83 → 92 %, recall 86.2 → 85.4 %.
    `thresholds`, `scope`, `limbs`, `defined_terms`, `deontic_judged` not kept. NLI cost ≈ 2× (more candidates).
  - Tests: 143 pass (new `tests/test_accuracy_features.py`). Nothing committed yet (one commit per milestone).

- 2026-10-06 (10): **Enrichment model: `gemini-3.8-flash-high` (your call)**, via the router's
  `/v1/chat/completions` only. You told me not to call any other router endpoint ("ask what you need, don't
  explore/discover") after I listed `/v1/models` once to check the router was up; no other call was made. Noted
  risk (yours to accept, accepted): Gemini is the grid's closed model (cells 4A/4C), so a Gemini-written premise
  layer could favour Gemini-phrased answers; the trace records the layer's model and version.

- 2026-10-06 (9): **Accuracy plan approved (your go, "all good. step 2: use router/frontier model").**
  - Step 1 (deterministic, dev only, each change measured on its own): limb-split NLI premises + limb check,
    clause-split hypotheses (denials dropped), an "as at" check for dated versions with a new reason code
    `VERSION_MISMATCH` (API addition approved), modals checked against the judged window, narrower connective
    rule, scope check, defined-term links.
  - Step 2: an offline enrichment layer (elements + thresholds per provision, quote-audited, approach copied
    from `~/Code/ephemeral-dynamic-llms/cloud/reason.py`, no dependency on that repo), generated with a
    frontier model through the router — **paid calls approved for this purpose**. Step 3: held-out from the
    concept `test` split, identical pipeline, sealed, run once.
  - P2 and the base model decision are folded into step 1's measurements.

- 2026-10-05 (8): **Dev battery run; calibration done; halted on a policy/API decision (⛔).**
  - First run, then seven claim-check fixes found on dev rows (each with a test; 136 tests pass): claim-only GP
    false rollback 10.4 % → 2.4 %, precision 80 % → 96 %. Details and tables in `docs/measurements.md`.
  - Threshold sweep (150 configs × 2 models): thresholds barely matter (saturated probabilities); base beats
    small everywhere. The lever is the policy for NLI-neutral sentences: P2 (emit when a figure/citation claim
    is grounded) takes base from 13.6 % to 8.8 % GP false rollback for −3 pp recall. Needs a config field.
  - Unsolved and stated: NLI fails on double-negative drafting and domain synonyms; premise corrections 6/6
    rolled back by NLI; derived figures ungrounded.

- 2026-10-05 (7): **New dev rows and held-out draft approved (your go, "proceed").** Running the dev battery.

- 2026-10-05 (6): **Extra sources built in; halted for review of the new rows (⛔).**
  - **No fetch:** you supplied the dated versions in `anchors_xml/` (git-ignored, like `data/`). Checked each:
    identifier, figure and in-force range match the anchor (£464/£538, £450/£508, £25.9m/£36m). The
    `*_base.xml` files are HTML pages of the current text; used only to cross-check that the corpus agrees
    (£751; £27m/£54m). ca-382's two versions were copied from legal-rag-audit's own cache (2008-04-06 and
    2021-04-06 texts, in force on both anchor dates). Current-text dates from the corpus: ss.186/227 £751 since
    6 April 2026 (S.I. 2026/310); ss.382/465 since 6 April 2025 (S.I. 2024/1303).
  - **Dropped-qualifier (your go):** two rows relabelled to `grounded_paraphrase` (PEA s.5 "four weeks", EqA
    Sch. 1 "12 months"); checker changed so a dropped minimum is not `QUALIFIER_DROPPED` (caps, comparatives,
    conditions still are). Test added.
  - **New rows:** dev +38 (anchors era-227/era-186: 16 incl. 8 `version_swap`; Mode C CHIM-001/002, OOB-001: 12;
    Mode A FAB-001–003: 10) → 271. Held-out draft 34 (ca-465, ca-382, CHIM-003, DEVOLV-001, REPEAL-001,
    FAB-005/006), not run, not sealed. Two new classes: `version_swap` (ROLLBACK), `premise_correction` (EMIT).
  - **Found in rag-security-probes:** FAB-002's worked abstention cites HA 1996 s.81 for a commercial tenant;
    s.81(4)(a) excludes business tenancies. Not changed there; labelled ROLLBACK here. The repo has no LICENSE
    file (same owner; attribution added to `NOTICE`).
  - Builder generalised (`premises.py`, `clml.py`, `anchors.toml`); `scripts/run_battery.py` uses the same
    premises. 128 tests pass; ruff, format, mypy clean.

- 2026-10-05 (5): **Your calls:** the dev/held-out split by provision is approved (era-227, era-186 → dev;
  ca-382, ca-465 → held-out; Mode C/Mode A halved by class); legal-rag-audit's live-run responses are **skipped**
  ("we do not reference / worry about these for now") — remind you when we benchmark. Before any fetch you asked
  how and what: proposed below (6 URLs via the router's fair-use `Fetcher`); waiting for your go. Dropped-qualifier:
  you asked for a suggestion; proposed below; waiting.

- 2026-10-05 (4): **Dev labels approved (your go, "all good. keep them").** You asked about two more sources:
  `~/Code/rag-security-probes` (Mode A fictional instruments, Mode C chimeric/out-of-bounds/devolution/repealed
  probes, `schemas/claim_shapes.json`) and `~/Code/legal-rag-audit` (point-in-time anchors, the `propose`
  command, live-run responses). Not considered before; reviewed now.
  - **Bug found via Mode C and fixed:** query grounding (R4) accepted any claim kind, so a sentence repeating a
    false premise from the query ("Section 86 of the Family Rights Act 1996", "section 342 ERA 1996") was
    grounded by the query. Now only figures are (R4 as written). Regression test added; 127 tests pass.
  - Proposal and open decisions: see the reply of this stop (version-swap class from anchors; Mode C/Mode A rows
    for wrong-instrument/citation; dev/held-out split by provision; dropped-qualifier labels vs the audit's
    defects 23/29; live responses not used without your call).

- 2026-10-05 (3): **M2 built up to the label review; halted (⛔).** Uncommitted (one commit per milestone).
  - **NLI head** `legal_rag_verifier.nli.SentenceNLIVerifier` (`[nli]` extra, torch 2.14.1, transformers
    5.18.0): batched, cuda/mps/cpu, labels from `id2label`, chunking to the 512-token budget, `model_id` =
    name@commit. Tests skip without torch or weights.
  - **Latency** (`docs/measurements.md`, Apple M4): one pair 18 ms (small, MPS) / 26 ms (base); a full s.124
    premise (9 candidates) 135 ms / 272 ms p50. The forward pass is linear in the number of pairs on the M4, so
    the per-sentence cost is set by how many candidates are scored. L4 figures come in M4.
  - **Found:** `nli-deberta-v3-small` was not cached (no weights; the plan said it was). Downloaded from the
    public hub (free), revision `fa28048`. Both checkpoints use 0 = contradiction, 1 = entailment, 2 = neutral;
    **vault 04 §2 hard-codes `entailment_idx = 2` (neutral)**, a vault correction for later (⛔ with your go).
  - **NLI judging rule (design, before any battery run):** a sentence entailed by any candidate (above the
    threshold) is judged on it; otherwise on its most related candidate (lowest P(neutral)). Taking the max
    contradiction over all windows rolled back correct statements of exceptions (s.124(3) "may be exceeded"
    contradicts s.124(1)). Windows are scored with their heading, plus joined candidates for in-premise
    cross-references ((1)+(1ZA)), because base could not link (1ZA) to "compensatory award" on its own.
    An entailed sentence with no figures is now `GROUNDED`, not `CONNECTIVE`. No names changed.
  - **Premise fixes found while reading real provisions:** inserted subsection labels such as `(A1)` (TULRCA
    s.188) now split windows; a section's own stem no longer swallows its subsections (LRA 2002 Sch. 6 was
    duplicated); regnal-year Acts (`uk/ukpga/Vict/24-25/100`) now load (filed under the calendar year) and their
    coordinate tails are right (`s20`, not `100/s20`). Tests added for each.
  - **Router data quirks (not fixed here; for the router's ingest):** MCA 1973 s.1 has lost its subsection
    records (all text in one node, labels missing); UCTA 1977 s.11 has OCR "lt" for "It"; TULRCA s.188(1) reads
    "the employer The employer shall consult" (amendment text merged).
  - **Dev battery** (`batteries/verifier/`, see its README): 233 hand-written rows (the plan said ~150) over 56
    real premises from the router's concept `dev` split, 9 classes, 119 EMIT / 114 ROLLBACK, each with a verbatim
    excerpt, coordinate and `source_url`. Most of the extra rows are grounded paraphrases (109), which carry the
    headline false-rollback rate. **The verifier has not been run on them.** I can trim to ~150 if you prefer.
  - `scripts/run_battery.py` (scoring + dev-only threshold sweep with cached NLI scores) is written and unit-tested
    on synthetic outcomes only. 126 tests pass; ruff, format and mypy --strict clean.

- 2026-10-05 (2): **M1 API approved (your go, "all good"),** including the reason codes, `GroundedBy`,
  `align_ratio=0.5` and the module layout in `docs/API.md` §5. M2 started.

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
- **Done when:** checks green ✅ · ⛔ API reviewed ✅ (2026-10-05).

### M2 — NLI head + dev battery (`[nli]`) ✅
- [x] `legal_rag_verifier.nli.SentenceNLIVerifier` implementing `NLIScorer`: batched `[window, hypothesis]`,
      MPS/CUDA/CPU, MPS-synchronised timing, `id2label` read from the model config.
- [x] Long windows split to fit 512 tokens (chunks scored per window; most related chunk kept).
- [x] Latency p50/p99 on M4 for `-small` and `-base` → `docs/measurements.md`.
- [x] Dev detector battery (R1): 233 rows from real provisions (router concept `dev` split, R11), 9 classes.
      Rows written independently of the checker's patterns; verifier not run on them.
- [x] ⛔ **You review/correct the labels before any threshold is calibrated.** (done before calibration)
- [x] Calibrate on dev only: thresholds, `align_ratio`, neutral policy (R7), small vs base. Headline:
      false-rollback rate on grounded paraphrases, recall per class.

### M3 — Engine + HF backend
- [x] `engine.InFlightGenerator(backend, verifier, max_rollbacks, max_total_rollbacks, refusal)`;
      `generate_verified(query, premise) -> Answer(text, trace)`.
- [x] `Backend` protocol (`extend(committed, stop, max_new, constraint) -> Segment`, plus the backend's
      tokenizer: `chat`, `encode`, `decode`); `Constraint` = `Ban` | `Allow`.
- [x] `backends/hf.py`: `DynamicCache` aligned to the committed prefix; truncate on reject; logits mask.
- [x] Invariant test (tiny-random Llama, CPU fp32): rollback-then-extend logits equal a fresh prefill within
      1e-7 (not bit-identical: one-token re-feed vs full prefill), argmax and greedy continuation identical.
- [x] Scripted fake backend: ban, allow-list, refusal, trace; injected £85,000 caught and removed.
- [x] First step: bnb 4-bit Llama 3.1 8B loads and decodes on MPS (needs serial weight loading).
- [x] `scripts/live_demo.py` on the real s.124 premise; prints the trace.

### M4 — SGLang backend + Modal L4 spike 🧑 (spend)
- [x] `backends/sglang.py` (stdlib HTTP client, server-side mask for constraints), offline tests vs a fake server.
- [x] `scripts/modal_m4.py` (`lmsysorg/sglang:v0.5.21`, Qwen 2.5 7B, L4, 30-min cap) + `scripts/m4_spike.py`.
- [x] Your go (2026-10-06). CPU probe (Python 3.12.3, sglang 0.5.21, mask processor imports), CPU weight
      download, one L4 run (~5 min GPU): s.124 queries + injected £85,000 both ways, round trip warm vs cold.
- [x] Prefix-cache hit recorded on every rollback (`cached_tokens = committed − 1`): roadmap 10 §3 risk 1 retired.

### Later — sealed held-out battery + 2×2 grid (07 §5), CI/GitHub, release, vault corrections (⛔ each)
