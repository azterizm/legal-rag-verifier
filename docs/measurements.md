# Measurements

Every figure here is **Measured** on the machine named, in-process (`time.perf_counter_ns`, device-synchronised).
Local Mac runs are for development only; no Mac figure is published as a rate (plan decision 4). L4 figures come
from M4.

## M2 — NLI latency (2026-10-05)

Machine: Apple M4 (macOS 26.6.2), Python 3.12.11, torch 2.14.1, transformers 5.18.0, fp32.
Script: `scripts/nli_latency.py --n 200` (20 warm-up calls); raw output `results/nli_latency.json`.
Premise: ERA 1996 s.124 as in force (6 subsection windows, 1 temporal fact, 2 joined cross-references
= 9 candidates; padded length 152 tokens). Timing covers tokenisation, forward pass and softmax.

| Model (revision) | Device | Pairs per sentence | p50 ms | p99 ms |
|---|---|---|---:|---:|
| nli-deberta-v3-small (`fa28048`) | MPS | 1 | 17.95 | 21.25 |
| nli-deberta-v3-small | MPS | 9 | 134.72 | 145.98 |
| nli-deberta-v3-small | MPS | `check_sentence` (claim check + 9 pairs) | 140.51 | 160.36 |
| nli-deberta-v3-small | CPU | 1 | 19.58 | 20.14 |
| nli-deberta-v3-small | CPU | 9 | 144.54 | 157.91 |
| nli-deberta-v3-base (`6c749ce`) | MPS | 1 | 25.68 | 27.94 |
| nli-deberta-v3-base | MPS | 9 | 271.82 | 298.76 |
| nli-deberta-v3-base | MPS | `check_sentence` | 271.70 | 297.17 |
| nli-deberta-v3-base | CPU | 1 | 39.06 | 41.47 |
| nli-deberta-v3-base | CPU | 9 | 298.20 | 319.32 |

Findings:
- **Latency is linear in the number of pairs on the M4**, on MPS and CPU alike (small, MPS forward pass only:
  1 pair 21 ms, 3 pairs 52 ms, 9 pairs 141 ms; tokenisation 0.8 ms; fp16 on MPS 131 ms for 9 pairs). The
  encoder is compute-bound here, so batching does not hide the window count. On this machine the per-sentence
  cost is set by how many premise candidates are scored, not by the 512-token limit.
- One pair on MPS is within vault 04's 30 ms target for both models; a whole premise is not (135 ms small,
  272 ms base). 04's target is stated for the L4 at batch 1; the per-sentence figure that matters is the full
  premise batch, measured on the L4 in M4.
- The claim check adds ~6 ms p50 on top of NLI here (`check_sentence` − 9 pairs, small/MPS). (The claim-only
  path is measured in M2's battery run.)

Facts found while measuring (no figures):
- `cross-encoder/nli-deberta-v3-small` was **not** cached (config and tokenizer only, no weights) although the
  plan said both were; its weights were downloaded from the public hub on 2026-10-05 (revision `fa28048`).
- Both checkpoints label **0 = contradiction, 1 = entailment, 2 = neutral**. Vault 04 §2's code hard-codes
  `entailment_idx = 2` (neutral) — a vault correction for later (⛔ with your go). This package reads
  `id2label` from the model config.

## M2 — Detector on the dev battery (2026-10-05)

Battery: `batteries/verifier/dev.jsonl` (271 rows, sha256 `3f524a8809a8…`), labels reviewed. Dev split only; the held-out
split has not been run. Script: `scripts/run_battery.py` (raw per-row verdicts in `results/raw/`, summaries in
`results/dev-*.json`). Thresholds at the defaults (entail 0.70, contradict 0.40, align_ratio 0.5, connective).

### First run, then claim-check fixes found on dev

| Detector | GP false rollback | All-pass false rollback | Failure recall | Rollback precision |
|---|---:|---:|---:|---:|
| claim check only (first run) | 10.4 % | 13.5 % | 60.0 % | 80.4 % |
| claim check only (after fixes) | **2.4 %** | 2.1 % | 56.9 % | **96.1 %** |
| + small (after fixes) | 18.4 % | 20.6 % | 83.1 % | 78.8 % |
| + base (after fixes) | 13.6 % | 16.3 % | 86.2 % | 83.0 % |

Fixes (each with a regression test; held-out untouched): a statutory "shall not … unless" licenses "must";
parentheticals no longer hide a modal; numbers written as words or ordinals in the premise ground digits;
a figure is a dropped qualifier only if no occurrence's qualifier is kept, and "generally"/"normally" mark a
condition; a figure from a dated version (fact window) is not a value swap; a citation or Act the sentence says
does not exist is not a claim; "I cannot" is not a prohibition.

### Per class (after fixes; rolled back / rows)

| Class | claim only | + small | + base |
|---|---:|---:|---:|
| grounded_paraphrase (EMIT) | 3/125 | 23/125 | 17/125 |
| connective (EMIT) | 0/10 | 0/10 | 0/10 |
| premise_correction (EMIT) | 0/6 | 6/6 | 6/6 |
| wrong_figure | 22/24 | 23/24 | 23/24 |
| wrong_citation | 11/15 | 13/15 | 14/15 |
| wrong_instrument | 16/16 | 16/16 | 16/16 |
| modal_shift | 8/17 | 13/17 | 15/17 |
| dropped_qualifier | 1/9 | 4/9 | 4/9 |
| value_swap | 2/8 | 3/8 | 4/8 |
| version_swap | 4/8 | 8/8 | 8/8 |
| unsupported_plausible | 10/33 | 28/33 | 28/33 |

### Threshold sweep (dev; 150 configurations per model)

Entail ∈ {0.5…0.9}, contradict ∈ {0.3…0.7}, neutral ∈ {connective, strict}, align_ratio ∈ {0.3, 0.5, 0.7}.
**The thresholds barely move the result:** base's probabilities are saturated near 0 or 1, so entail 0.7–0.8
with any contradict threshold gives the same verdicts (GP 13.6 %, recall 86.2 %); `align_ratio` has no effect
when the NLI head ranks windows; `strict` buys +3 pp recall for +4 pp all-pass false rollback. Base dominates
small at every setting (better on both axes), at twice the latency (272 vs 135 ms per sentence on the M4).

### Policy, not thresholds (offline, from the same raw results)

| Detector | Policy for a sentence the NLI head finds neutral | GP FR | All-pass FR | Recall | Precision |
|---|---|---:|---:|---:|---:|
| base | roll back (current) | 13.6 % | 16.3 % | 86.2 % | 83.0 % |
| base | **emit if a figure/citation claim is grounded (P2)** | **8.8 %** | 12.1 % | 83.1 % | 86.4 % |
| base | always emit; only contradiction rolls back (P1) | 8.0 % | 11.3 % | 79.2 % | 86.6 % |
| small | P2 | 12.8 % | 15.6 % | 82.3 % | 82.9 % |

### What remains (not threshold-fixable)

- **NLI on legal drafting:** base gives contradiction 1.00 to correct paraphrases of double-negative drafting
  (Prescription Act 1832 s.2 "No claim … shall be defeated … by showing only …") and is neutral on
  domain synonyms ("articles" vs "articles of association") and on a dated version's figure when the date sits
  in a separate fact window.
- **Premise corrections** ("There is no Family Rights Act 1996; …") pass the claim check now but every one is
  rolled back by NLI (6/6): a denial is not entailed by the provision.
- Derived figures (five weeks = one week × 5 years; "22 and 40" from "not below 22 / 41") remain ungrounded.

## Accuracy plan — step 1 (deterministic) and step 2 (enrichment), dev only (2026-10-06)

Each change behind a switch (`Verifier(features=…)`), measured alone, all-on and all-but-one
(`scripts/ablate_battery.py`; `results/ablate-*.json`). Base NLI, default thresholds.

| Switch | Effect with base | Kept |
|---|---|---|
| `clauses` (judge each clause; drop clauses that deny an Act/section) | all-pass FR 16.3 → 12.8 %, recall = | yes |
| `p2` (NLI-neutral sentence emits if a figure/citation is grounded) | GP FR 13.6 → 8.8 %, recall −3 pp | yes |
| `as_at` (dated figure must be the version in force; `VERSION_MISMATCH`) | +0.7 pp recall, no cost (claim-only: +3.1 pp) | yes |
| `limb_check` (figure must sit in the list item the wording matches) | +0.7 pp recall, no cost | yes |
| `scope` ("any/only/always…" must be in the source) | +3 pp recall, GP FR → 17.6 % | no |
| `substantive` (content sentences need entailment without figures) | +3 pp recall, +0.8 pp GP FR | optional |
| `limbs`, `defined_terms`, `deontic_judged` | no gain | no |

Enrichment layer (`enrichment/gemini-3.8-flash-high/`, 73 units for the dev premises, 73 router calls,
prompt sha256 in each file): elements 776/781 verified (99.4 %), thresholds 114/160 (71 %).

| Detector (base) | GP FR | All-pass FR | Recall | Precision |
|---|---:|---:|---:|---:|
| before step 1 | 13.6 % | 16.3 % | 86.2 % | 83.0 % |
| + P2 only (proposal of stop 8) | 8.8 % | 12.1 % | 83.1 % | 86.4 % |
| K = clauses + p2 + as_at + limb_check | 8.8 % | 8.5 % | 84.6 % | 90.2 % |
| **K + elements** | **7.2 %** | **7.1 %** | 85.4 % | **91.7 %** |
| K + elements + thresholds + substantive | 8.8 % | 8.5 % | 87.7 % | 90.5 % |
| claim check only + K | 2.4 % | 2.1 % | 62.3 % | 96.4 % |

- `thresholds` (binding figures by the model-written "what") hurts precision even without NLI (GP FR
  2.4 → 4.0 %): not kept. `elements` alone helps only with K (it supports entailment once clauses are split).
- Per class, K + elements vs before: premise_correction rolled back 6/6 → 1/6, grounded_paraphrase 17 → 9 of
  125, value_swap caught 4 → 5 of 8; other classes unchanged.
- **Cost:** elements raise NLI candidates per sentence from a median of 7 (max 38) to 16 (max 130), so NLI time
  roughly doubles (≈ 550 ms per sentence on the M4 for base, from 272 ms). A two-stage scorer (elements only for
  the top windows) is the obvious mitigation; not built.
- **All of this is fitted on dev.** The held-out split (concept `test` rows + the anchor/probe draft, same
  pipeline, enrichment built the same way, sealed) is the only figure to quote.

## Defaults confirmed on dev, and an MPS fix (2026-10-06)

- With the step 1 + 2 set baked in as the default (`results/dev-default-{none,base}.json`): claim check only
  2.4 % / 2.1 % / 62.3 % / 96.4 % and base 7.2 % / 7.1 % / 85.4 % / 91.7 % (GP FR / all-pass FR / recall /
  precision), identical per class to the ablation. Enrichment layer `gemini-3.8-flash-high@edb8ccbbc4fc4862`
  (190 units: dev 73 + held-out 117; elements 2,029/2,047 verified, thresholds 312/475).
- **MPS graph compilation:** the first default run took > 2 h because every new input shape (batch size ×
  padded length) made MPS compile a new graph. `nli.py` now scores in fixed batches of 16 pairs padded to a
  multiple of 64 tokens (scores unchanged): 271 sentences in 651 s, ≈ 2.4 s per sentence with base + elements on
  the M4. That is far above the 30 ms target and is dominated by the number of candidates (median 16, max 130);
  a two-stage scorer and the L4 measurement (M4) are the next steps for latency.

## Held-out — sealed `heldout-2026-10-06`, run once per detector (2026-10-06)

Seal `batteries/verifier/seals/heldout-2026-10-06.json` (committed in `a4d9726` before the run): 346 rows over 102
premises, battery sha256 `1df51b99…`, verifier commit `138943b`, enrichment layer
`gemini-3.8-flash-high@edb8ccbbc4fc4862`. Results: `results/heldout-2026-10-06-{none,base}.json`.
**These are the figures to quote** (Apple M4, base = `nli-deberta-v3-base@6c749ce`, default config).

| Detector | GP false rollback | All-pass false rollback | Failure recall | Rollback precision |
|---|---:|---:|---:|---:|
| claim check only | 5.0 % (9/179) | 5.2 % (10/191) | 53.6 % (83/155) | 89.3 % |
| **claim check + base NLI + enrichment** | **7.3 % (13/179)** | **7.9 % (15/191)** | **80.0 % (124/155)** | **89.2 %** |
| (dev, same config, for comparison) | 7.2 % | 7.1 % | 85.4 % | 91.7 % |

Per class (base): wrong_figure 36/37, wrong_instrument 14/15, wrong_citation 7/9, version_swap 8/8,
value_swap 9/11, modal_shift 15/16, unsupported_plausible 29/41, dropped_qualifier 6/18; false rollbacks:
grounded_paraphrase 13/179, premise_correction 2/5, connective 0/7.

By source (base): concept `test` rows (312) — all-pass FR 5.8 %, recall 78.4 %, precision 91.6 %; anchor and probe
rows (34) — all-pass FR 27.8 % (5/18), recall 93.8 % (15/16), precision 75.0 % (small n).

Reading: the false-rollback rate held from dev to held-out (7.2 → 7.3 %); recall fell 5.4 pp and precision 2.5 pp,
the expected dev-to-held-out shrink. Weakest classes: dropped_qualifier (6/18 caught) and unsupported_plausible
(29/41). Wall time 666 s for 346 sentences (≈ 1.9 s each on the M4); latency remains the open problem (L4, M4).

## Real answers from legal-rag-audit live runs, anonymised (2026-10-06)

Source: the audit's own captured answers and its own per-answer outcomes (`point_in_time`, `abstention`), read
only; nothing was run on the audit side. Two third-party targets, anonymised as **System A** (44 answers) and
**System B** (11 answers with a captured answer); product names in answers replaced, run/chat ids, tool names,
timestamps, citations and raw payloads dropped. The anonymised answers stay local and git-ignored
(`external/audit_live/`); only counts are committed (`results/audit-live-*.json`, `scripts/score_audit_live.py`).
48 answers scored (era-124 has no dated text here: 7 skipped). Premise: the dated version in force on the date
asked ("version") or every version plus the current text ("timeline"); fictional-instrument answers against an
empty premise (no source exists).

| Detector / premise | Audit FAILs flagged | Correct abstentions passed | In-force-figure sentences emitted | Superseded-figure sentences flagged | Share of sentences rolled back in correct answers |
|---|---:|---:|---:|---:|---:|
| claim check / version | 3 / 3 | 28 / 28 | 18 / 38 | 5 / 5 | 37.9 % |
| claim check / timeline | 3 / 3 | 28 / 28 | 20 / 38 | 5 / 5 | 37.2 % |
| base + enrichment / version | 3 / 3 | 28 / 28 | 13 / 38 | 5 / 5 | 50.0 % |
| base + enrichment / timeline | 3 / 3 | 28 / 28 | 4 / 38 | 5 / 5 | 55.4 % |

Findings (not tuned after the sealed run; recorded for the next iteration):
- **Every audit failure is caught** (two fabricated figures for a fictional Act, one superseded figure), and no
  correct abstention is flagged, including those that name the fictional Act to deny it.
- **Real answers carry open-world context** (amendment history, amending S.I.s, other sections, other years'
  figures). At sentence granularity one unsupported detail rolls back a correct sentence: about half the correct
  dated-figure sentences are rolled back. This matters most for post-hoc checking of closed models (4A/4C); the
  in-flight engine generates against the premise only.
- **NLI is harmful on dated material.** With every version in the premise, the NLI judges a correct historical
  figure against the current text and calls it a contradiction (4 / 38 emitted). The deterministic "as at" check
  handles the figure correctly; the principled fix is to restrict NLI candidates to the windows in force on the
  date asked. Proposed, not applied.
- Small defects seen: an instrument title containing a comma is truncated ("Companies, Partnerships and Groups …
  Regulations 2015"); "item 7" in a quoted schedule counts as a bare number.

## M3 live run: engine + HF backend on the Mac (2026-10-06, development only)

Generator `unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit@f15c379f` on MPS (bnb 4-bit, fp16; loads only with serial
weight loading, `HF_DEACTIVATE_ASYNC_LOAD=1`), verifier = defaults with `nli-deberta-v3-base`, premise = ERA 1996
s.124 fixture + the S.I. 2026/310 fact window (713 prompt tokens). `scripts/live_demo.py`; traces in
`results/live-demo-{allow,ban}[-injected].json`. Greedy, so both steering modes see the same first draft.

**Rollback invariant.** Tiny Llama, CPU fp32: logits after rollback vs fresh prefill differ by at most 4.5e-8
(not bit-identical: one-token re-feed vs full prefill), argmax and greedy continuation identical (test).
Llama 8B, MPS 4-bit fp16: argmax equal, max |Δlogit| 0.10; each call reuses all of the committed prefix except
the last token (`prefix_cache_hit_tokens = committed − 1`).

| Run | Answer | Rollbacks | Outcome |
|---|---|---:|---|
| Q1 cap, allow / ban | "…the lower of £123,543 and 52 multiplied by a week's pay… set in section 124(1ZA)…" | 0 | correct, both modes |
| Q2 whistleblowing, allow / ban | "The limit… does not apply… section 124(1A)… by virtue of section 100." | 1 | see below |
| Q1 + injected "£85,000" sentence, **allow** | refusal | 2 | figure forced to £123,543 (tokens ` £` `123` `,` `543`), then QUALIFIER_DROPPED → refusal |
| Q1 + injected "£85,000" sentence, **ban** | "Under the Employment Rights Act 1996, … the lower of £123,543 and 52 … week's pay…" | 1 | recovered, correct |

Decode ≈ 2 tok/s (bnb 4-bit on MPS); claim check 1–3 ms and NLI (base) 0.7–2.1 s per answer.

Findings:
- **Allow vs ban, first measurement.** The allow-list repairs the figure but keeps the sentence frame, so the
  qualifier the figure needs ("the lower of … and 52 weeks' pay") is still missing; the verifier catches that and
  the second rollback is the refusal. Ban restarts the sentence and the model writes the full rule. One prompt
  only; the grid measures this properly. Option (not applied): after an allow retry fails on a different
  reason, fall back to ban before refusing.
- **NLI false rollback on a correct "No, …"**: "No, the limit … does not apply if the employee was dismissed for
  whistleblowing." scored contradiction 1.0 (correct per s.124(1A)); the ban on "No" gave the same claim
  without the "No", emitted as CONNECTIVE. A negation/polarity weakness of the NLI head, as on the batteries.
- **Undetected omission**: the model quoted s.124(1A) but stopped the list at "section 100" (the whistleblowing
  ground is s.103A). Every claim in the sentence is grounded; truncating a list is outside the claim check.

## Date-filtered NLI candidates (2026-10-06, dev only; held-out sealed and not re-run)

With a date asked about (the sentence's own date, else the query's) and dated versions in the premise, NLI only
judges against the versions in force on it (undated windows and facts stay).

| Dev, base + enrichment | GP false rollback | all-pass false rollback | recall | precision |
|---|---:|---:|---:|---:|
| before | 7.2 % | 7.1 % | 85.4 % | 91.7 % |
| date filter | **5.6 %** | **5.7 %** | 85.4 % | **93.3 %** |

Two rows change (vdev-0239, vdev-0247: NLI_CONTRADICTION → GROUNDED); nothing else moves.

legal-rag-audit live answers (anonymised, base + enrichment), before → after:

| Premise | In-force-figure sentences emitted | Superseded flagged | Rolled-back share in correct answers | FAILs flagged | Abstentions passed |
|---|---:|---:|---:|---:|---:|
| version | 13 → 13 / 38 | 5 / 5 | 50.0 → 50.0 % | 3 / 3 | 28 / 28 |
| timeline | 4 → **13** / 38 | 5 / 5 | 55.4 → **45.1** % | 3 / 3 | 28 / 28 |

The version premise holds one version, so nothing changes there; on the timeline premise the filter removes the
"historical figure judged against the current text" failure noted above.

## M4 spike: SGLang + Qwen 2.5 7B on one Modal L4 (2026-10-06)

`scripts/modal_m4.py::main` (image `lmsysorg/sglang:v0.5.21`, Python 3.12.3, `--mem-fraction-static 0.70`,
`--enable-custom-logit-processor`), generator `Qwen/Qwen2.5-7B-Instruct@a09a3545`, verifier = defaults with
`nli-deberta-v3-base@6c749ce3` on the same GPU, premise = the s.124 fixture + S.I. 2026/310 fact (759 prompt
tokens). Same queries and injected failure as the Mac run. GPU time about 5 min (server up 14:10–14:14 UTC).
Trace: `results/m4-sglang.json`.

**Prefix cache (roadmap 10 §3 risk 1).** After every rollback the resubmitted committed prefix is served from
RadixAttention: each warm resubmit of the 759-token prompt reports `cached_tokens = 758` (5/5), and every decode
call in every run reports `cached_tokens = len(committed) − 1`. One-token round trip on the prompt, median of 5:
**cold 212 ms** (cache flushed) vs **warm 122 ms** (prefix cached). The warm figure is mostly per-request
overhead (HTTP, scheduling, one decode step), not prefill; vault 04's `< 30 ms` target is **not met** in this
setup and is not claimed. Profiling the request path is a follow-up.

| Run | Answer | Rollbacks | Outcome |
|---|---|---:|---|
| Q1 cap, allow / ban | "…the lower of £123,543 and 52 multiplied by a week's pay… set by section 124(1ZA)…" | 0 | correct (decode 3.6–3.8 s) |
| Q2 whistleblowing, allow / ban | "…does not apply… regarded as unfair dismissal under section 100… excluded… by section 124(1A)" | 1 | NLI false rollback on the correct "No, …"; the emitted answer names s.100 for whistleblowing (s.103A is right) |
| Q1 + injected £85,000, allow | refusal, then hedged prose | 3 | £85,000 → allow forced £123,543 (` £` `1` `2` `3` `,` `5` `4` `3`: 8 masked one-token requests) → QUALIFIER_DROPPED → ban retry (new fallback) wrote the full correct rule → **NLI_CONTRADICTION 0.96** → refusal |
| Q1 + injected £85,000, ban | refusal, then hedged prose | 2 | £85,000 → ban retry wrote the full correct rule → NLI_CONTRADICTION 0.96 → refusal |

Findings:
- **The mechanism works on a production server, across tokenizers.** Llama (≤ 3-digit chunks, Mac) and Qwen
  (per digit, SGLang) take the same engine path; the constraint mask runs server-side; no rollback re-prefills
  the committed prefix.
- **The NLI head is now the main source of error, not the claim check.** The fully correct sentence "According
  to section 124(1ZA) …, the maximum compensatory award … is the lower of £123,543 and 52 multiplied by a week's
  pay…" was judged on window s.124(1A) (the exception) with contradiction 0.96, because no window entailed it
  above 0.70; without "According to section 124(1ZA)" the same claim scored contradiction 0.03 and was emitted.
  Proposed, not applied: when a sentence cites a provision in the premise, judge NLI on that provision's window
  (and the windows it joins) rather than on the most related window anywhere.
- **Negation false rollback reproduces on Qwen** ("No, the limit … does not apply…", contradiction 1.0).
- **Wrong-ground citation passes**: "section 100" is in s.124(1A), so it is grounded, though it is the wrong
  ground for whistleblowing. Binding a citation to the claim it supports is outside the claim check.
- **After a refusal the model hedges** with grounded but unhelpful prose; a refusal that ends the answer, or a
  stronger refusal prompt, is a design choice for the grid.
