# Phase 3 Plan — `legal-rag-verifier` 0.1.0, M1–M3 (Mac)

## Context

Vault doc 04 specifies Layer 4: a sentence-level verifier (deterministic claim check + DeBERTa-v3 NLI) that runs while the
generator decodes, removes a failed sentence from the KV cache and resumes. Nothing is built: the only running code is
`~/Code/in-flight-verification-case-study` (one injected failure, HF `DynamicCache` slicing, NLI only). Roadmap 10 §2
Phase 3 ends with the 2×2 grid (07 §5) and `legal-rag-verifier 0.1.0`; its main open risk is SGLang prefix-cache reuse
on resubmit (10 §3).

Review of 04 against the case study found gaps that this build must close, not copy:
- `.` splits "s. 124", "art. 6", "Ltd.", "£68.4k" mid-sentence (case study and 04 alike).
- Citation check compares raw strings ("section 124" ≠ "s.124"); the provision's own citation is metadata, usually absent from its text.
- Deontic check runs against the whole premise; a section containing both "shall" and "may" flags valid sentences.
- Premise truncated at 512 tokens; 04 §1's 50-word ColBERT spans exist nowhere in the pipeline.
- Greedy re-decode after rollback reproduces the rejected sentence (pasted note §2B): no steering is specified.
- 04 §7 claims SGLang reset "verified in isolation"; no such run exists.

Intended outcome: a package whose core can be trusted on its own (claim check), whose rollback is proven correct by an
invariant test, and whose engine is backend-agnostic so the same controller drives HF (Mac), SGLang (Modal L4) and the
closed-model continuation cell (4C).

## Key design decisions (proposed)

1. **Request-per-sentence, not abort-mid-stream.** Each decode call runs until a candidate boundary (stop strings),
   returns, and is verified. Accept → append to the committed prefix. Reject → don't append; the next call resubmits the
   committed prefix (prefix-cache hit). No abort race, no tokens decoded past the boundary, and one protocol covers
   HF (keep/truncate `DynamicCache`), SGLang/vLLM (RadixAttention / APC hit) and Gemini prefill continuation (cell 4C).
   ```
   class Backend(Protocol):
       def extend(self, committed: Tokens, *, stop: ..., max_new: int, constraint: Constraint | None) -> Segment
       # Constraint: Ban(step-1 token ids) | Allow(token trie of grounded sequences, lifted when the span closes)
       # Segment: tokens, text, finish_reason, prefix_cache_hit_tokens, latency_ns
   ```
2. **Legal-aware streaming segmenter** (stdlib): candidate boundary at `.` `;` `\n`/EOS, rejected when the `.` closes a
   known abbreviation (s., ss., art., reg., para., sch., no., Ltd., plc., v., e.g., i.e., cf.) or sits inside a number,
   or the next char isn't whitespace/EOS. A false stop just extends the same sentence (prefix-cache hit).
3. **Deterministic claim check, rebuilt** (stdlib, the trustworthy core):
   - Figures: £/€ amounts (`£68,400` = `£68400`), percentages, dates (several formats → ISO), durations ("three months" = "3 months"; number words → digits).
   - Citations normalised to a canonical token (`section 124(1ZA)(a)` / `s.124(1ZA)(a)` → `s124/1ZA/a`); grounded if in premise text **or** the premise's declared citations; a parent cite (`s.124`) grounds against a child coordinate.
   - Instrument titles (`… Act 1996`, `S.I. 2026/310`): an instrument not named by the premise is ungrounded (the Marchwood failure).
   - Deontic classes OBLIGATION / PROHIBITION / PERMISSION, compared against the **aligned premise window**, not the whole premise.
4. **Premise = small dataclass, plain data only** (no import of router/temporal): `Premise(passages, citations, facts)`,
   with `Premise.from_provision(text, coordinate, title, in_force_from, amended_by)` linearizing temporal metadata into
   declarative sentences (pasted note §1), so "Since 6 April 2026 the cap is £123,543" can be grounded.
5. **NLI over premise windows, SummaC-ZS style** (Laban et al. 2022): split premise into sentence windows, batch
   `[window, hypothesis]` pairs in one forward pass, take the best-entailed window; it also serves as the aligned window
   for the deontic check. Thresholds (entail > 0.70, contradict > 0.40 from 04) become calibrated parameters, recorded in the trace.
6. **Two-sided steering after rollback, all at decode level, nothing written into the context.**
   - **Positive side = the premise already in the KV cache** (prompt prefix, untouched, 100% prefix reuse), **plus a
     grounded allow-list at the divergence point**: when the claim check rejects a figure / citation / modal, resume at the
     token where that claim starts and constrain the claim span to the premise's values of the same type (e.g. £ amounts
     in the premise → `£68,400` or `£123,543`; modal class of the aligned window → `shall`/`must`). Candidate token
     sequences come from tokenizing `committed_text + candidate` and taking the suffix (handles Llama's ≤3-digit chunks and
     Qwen's per-digit split). Constraint lifts once the span closes. The rejected value is excluded by construction.
   - **Negative side = ban**: used where there is no allow-list (NLI failure, or no same-type value in the premise):
     restart the sentence, ban its rejected first token for that step. Bans accumulate per position.
   - Two rollbacks on one point → fixed principled refusal sentence, then continue.
   - `steering="allow"|"ban"` is a parameter; the trace records which path recovered each rollback, so ban-only vs
     allow-list recovery is **measured** on the same prompts rather than assumed (M3 live run; grid later).
   - **Rejected:** writing negative text into the context ("do not say £85,000") — negation mispriming (Kassner &
     Schütze 2020, already in the case study's Act 2), new tokens break prefix reuse, and it leaks into the answer.
     Also rejected: re-injecting the chunk as hidden tokens near the decode position — the premise is already in
     cache, a hidden span makes "what the model conditioned on" differ from what the user sees, and cell 4C can't do it.
   - Disclosure for the grid: the allow-list is a self-hosted-only capability (closed APIs expose no logits), so it is
     part of what 4B/4D vs 4A/4C measures, and is stated as such.
7. **Trace per sentence:** text, verdict, reason, ungrounded claims, NLI probs + window index, claim/NLI latency (ns),
   tokens discarded, rollbacks, prefix-cache hit tokens, backend, model revision, thresholds. Canonical JSON.

8. **Refinements from the pre-build council (3 Oct)** — disclosed before work starts:
   - **R1 Detector accuracy is measured, not assumed.** The plan had no measurement of the detector itself, which
     every grid cell shares (07 §5) and the case study disclaims. Add a hand-labelled detector battery on real
     legislation text: `(premise, sentence, expected verdict, failure class)`. Classes: grounded paraphrase, connective
     prose, wrong figure, wrong citation, wrong instrument, modal shift, dropped qualifier, value swap (right-type figure
     from the wrong place), unsupported-but-plausible. Rows are written independently of the checker's patterns (router
     rule). Split dev / held-out: thresholds calibrated on dev only; held-out sealed before it is run.
     The headline is the **false-rollback rate on grounded paraphrases** (it decides how 4B reads) beside recall per class.
   - **R2 Dropped-qualifier check** (deterministic, figure-scoped). The most realistic s.124 error is
     "The cap is £123,543" — figure grounded, NLI likely passes on overlap, but the source says *the lower of* £123,543
     and 52 weeks' pay. If the aligned window binds a figure with a qualifier (`the lower of`, `whichever is`,
     `not exceeding`, `subject to`, `unless`, `except`, `save`) and the sentence states the figure without one →
     `QUALIFIER_DROPPED` (rollback via the NLI path). 07 §5's retry prompt already names "missed qualification Y".
   - **R3 Figures bind to the aligned window, not the whole premise.** Without this the allow-list turns a detectable
     error (ungrounded figure) into an undetectable one (right figure type, wrong provision). Figures, modals and
     qualifiers are checked against the top-2 aligned windows; allow-list candidates come from those windows only.
   - **R4 The query is a grounding source.** "My salary is £40,000…" must not be flagged; query figures are grounded
     and labelled `grounded_by=query` in the trace.
   - **R5 Post-hoc API = the shared detector.** `Verifier.check_text(premise, text) -> [SentenceVerdict]` is the same
     detector used post-hoc by cells 4A/4D; the in-flight engine calls the same function per sentence.
   - **R6 Bounded cost.** `max_total_rollbacks` per answer (besides 2 per point) so latency is bounded; refusal text fixed.
   - **R7 Neutral policy is a parameter**, not a hidden default: a neutral sentence with no checkable claim is emitted
     (connective) or rolled back (strict). Chosen by the dev split's false-rollback/recall trade-off.
   - **R8 English only in 0.1.0** (deontic, qualifiers, number words); Spanish (deberá/podrá) follows the router's Stage C.
   - **R9 Real statute text** for the live run and batteries, never a paraphrase. Data plan (your call, 3 Oct):
     - Copy `~/Code/legal-rag-router/uk_scrap_data/` (1.1 GB raw XML) into this repo, git-ignored, read-only, never
       published — same rule as the router. Spanish data waits for the Spanish release (R8).
     - Also copy the router's normalised provision records `data/uk/` (3.9 GB, git-ignored; built from that scrape by
       the router's ingest): they already hold the provision tree with `text` / `text_after` per node, so no XML parser
       is rewritten here. 61 GB free on disk.
     - Copy the router's sealed prompt batteries (`batteries/uk/*.jsonl`, `batteries/concept/uk.jsonl`) into
       `batteries/router/`, unchanged, with the source seal id (`battery-2026-09-29-v2`) and each file's SHA-256 recorded.
     - `data/MANIFEST.json` (OGL v3.0 attribution) lands now because the first source does; committed battery rows carry
       only the short excerpts they need, each with its coordinate and `source_url`.
   - **R10 Premise windows follow the provision tree, not sentence splitting.** Found in the data: s.124(1ZA) is a stem
     "the lower of—", children "(a) £123,543, and" / "(b) 52 multiplied by a week's pay", and some nodes have a
     `text_after` tail ("…shall not exceed the amount specified in subsection (1ZA)"). A sentence splitter would separate
     the qualifier from the figure and blind R2. `Premise.from_records(nodes)` assembles each subsection (stem + children
     + tail) into one declarative window, drops repealed text (dot runs), and declares the coordinates as citations.
   - **R11 Prompt sets come from the router's concept battery** (265 natural-language queries, 13 areas, each with gold
     coordinates). Query + gold coordinate → assembled premise = one generation prompt, which is exactly the grid's input
     shape (07 §5: same fixed chunks for every cell). Verifier dev work uses the router's `dev` split (112) and the
     held-out battery uses its `test` split (153), so no prompt crosses splits. `us_law` rows (50) are skipped (no US data).
     Citation-form batteries (collision, misroute…) supply queries that name a provision, for the citation and
     wrong-instrument detector classes.

Not applicable from the pasted note: §3 role-based metadata filtering — the router binds from the query itself, so the
query entity already overrides user context.

## Repo & conventions (mirror `legal-rag-router`)

`~/Code/legal-rag-verifier`: uv, hatchling, `requires-python >=3.11`, src layout, `py.typed`, AGPL-3.0-only, ruff
(router's rule set), mypy --strict, pytest + hypothesis, coverage on `src/`. `CLAUDE.md` + `docs/PLAN.md` (this plan) +
`docs/ROADMAP.md` (§S status, stop log, ⛔ halts). Local commits only, one per milestone; no remote/push/PyPI/paid calls/vault
edits without a go. Core wheel: zero runtime deps; extras `[nli]` (torch, transformers), `[hf]`, `[sglang]`.
Module names match vault 05's imports: `legal_rag_verifier.nli.SentenceNLIVerifier`, `legal_rag_verifier.engine.InFlightGenerator.generate_verified`.

Reuse from the case study: `truncate_kv_cache` / `get_kv_seq_len` (`02_in_flight_kv_rollback.py:196-238`), MPS-synchronised
NLI timing (`audit_sentence_nli`, same file :174), dynamic `id2label` handling.

## Milestones (first shippable layer first)

- **M1 — Claim check + segmenter + `check_text`** (CPU, stdlib; R2–R5, R8). Golden tests (£68,400 / £85,000 / £123,543;
  shall→may; "s. 124" not split; "section 124" = "s.124"; "The cap is £123,543" → `QUALIFIER_DROPPED`; query figure
  grounded), hypothesis fuzz (never raises, idempotent normalisation). ⛔ review API.
- **M2 — NLI head + dev battery** (`[nli]`): windowed premise, batched, MPS/CUDA/CPU; latency p50/p99 on M4; dev split
  of the detector battery (R1) used to pick small vs base and the thresholds; results in `docs/measurements.md`.
  Held-out split written and sealed later, before the grid.
- **M3 — Engine + HF backend**: request-per-sentence controller, steering, refusal, trace. **Invariant test** on cached
  `hf-internal-testing/tiny-random-LlamaForCausalLM` (CPU, CI-safe): logits after rollback-and-continue == logits from a
  fresh prefill of the same committed prefix (the honest "0 cache corruption" evidence). Port of the case study's injected
  failure as a test. Live run on Mac with the cached Llama 3.1 8B 4-bit on the real s.124 text.
- **M4 — SGLang backend + Modal L4 spike** 🧑 (spend): prefix-cache hit tokens recorded per rollback; retires 10 §3 risk 1.
- Later (not today): sealed battery + 2×2 grid (07 §5), CI/GitHub, release, vault corrections to 04 §1/§2/§7 (⛔ with your go).

## Verification

`uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest` at each milestone; M2 latency script;
M3 invariant test + live Mac run printing the trace; M4 Modal run printing prefix-cache hits.

## Decisions taken 3 Oct 2026

1. **Scope today: M1–M3 on the Mac.** $0. M4 (SGLang + Modal L4) is a later session.
2. **Engine: request-per-sentence** (decision 1 above). Vault 04 §3 wording updated later, with your go.
3. **Steering: deterministic, decode-level, two-sided** (decision 6 above): grounded allow-list at the divergence point
   for claim failures, ban for NLI failures; refusal after 2 rollbacks on one point. Revised 3 Oct after your
   positive/negative question.
4. **Dev generator: cached `unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit` on MPS; Qwen 2.5 7B on Modal (M4).**
   Two families exercise the backend-agnostic claim (Llama-3 chunks numbers into ≤3-digit tokens, Qwen splits per digit,
   so divergence-point bans are tested under both). First step of M3: confirm bnb 4-bit loads and decodes on MPS;
   fallback `Qwen/Qwen2.5-3B-Instruct` if not. Model id is a parameter (`GEN_MODEL_ID`), never hard-wired.
   Local runs are for development only; no local rate is published.
5. **NLI model:** `cross-encoder/nli-deberta-v3-small` per 04, with `-base` measured beside it in M2 (both cached);
   chosen by calibration result + latency, recorded in `docs/measurements.md`.
6. **Detector battery: I draft ~150 dev rows from real provisions; you review/correct labels before any threshold is
   calibrated** (⛔ halt in M2). Held-out split drafted the same way later and sealed before it runs.
8. **Backends: one engine, thin adapters, not two approaches.** All logic (segmenter, detector, steering decisions,
   rollback caps, trace) lives in the controller; a backend implements only `extend()`. HF (M3) holds the cache itself:
   test oracle for the rollback invariant, CPU CI, Mac dev. SGLang (M4) holds the cache server-side: proves the
   mechanism on a production serving engine and retires roadmap risk 1. Gemini (grid, 4A/4C) is a third adapter later.
7. **Data:** copy `uk_scrap_data/` + the router's normalised `data/uk/` (git-ignored) and its sealed prompt batteries
   into this repo (R9–R11). Copying happens as the first step of M1's setup.

## M3 detail (engine)

- `engine.InFlightGenerator(backend, verifier, max_rollbacks=2, refusal=...)`; `generate_verified(query, premise) -> Answer(text, trace)`.
- Loop: `backend.extend(committed, stop=boundary_stops, max_new=…, constraint=…)` → segmenter confirms a
  boundary (else extend same sentence) → `check_text` on the sentence (claim check → NLI) → commit, or rollback with
  allow-list / ban → refusal after 2 per point or `max_total_rollbacks`.
- `backends/hf.py`: keeps a `DynamicCache` aligned to `committed`; extend = incremental decode from the cached prefix;
  reject = truncate to committed length (case study `truncate_kv_cache`); `prefix_cache_hit_tokens` = reused length.
  Greedy decoding. `Backend.extend` takes a `Constraint` (ban set for step 1, or a token trie of allowed sequences)
  applied as a logits mask; HF via a `LogitsProcessor`, SGLang later via its regex-constrained decoding on a short
  span request, then a plain continuation (prefix-cache hit).
- Test: injected `£85,000` → allow-list resumes at the figure and emits a premise figure; ban-only path recorded for
  comparison on the same prompt.
- Tests: invariant (tiny-random Llama, CPU): rollback-then-extend logits == fresh-prefill logits on the same prefix
  (exact on CPU fp32; argmax + tolerance on MPS 4-bit); scripted fake backend for controller logic (ban, refusal, trace);
  injected £85,000 sentence caught and removed; segmenter false-stop path reuses the cache.
- Live: `scripts/live_demo.py` on the ERA 1996 s.124 premise (linearized with in-force date and amending SI), prints trace.
