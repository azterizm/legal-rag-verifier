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

## Detector fixes after M4, dev only (2026-10-06)

Dev battery, base + enrichment, default config; held-out sealed and not re-run; legal-rag-audit not re-run.

| Change | GP false rollback | All-pass false rollback | Failure recall | Precision |
|---|---:|---:|---:|---:|
| Before (stop 19, date filter) | 5.6 % | 5.7 % | 85.4 % | 93.3 % |
| + comma titles, label numbers ("item 7"), leading "Yes,"/"No," dropped before NLI | 5.6 % | 5.7 % | 85.4 % | 93.3 % |
| + citation-anchored NLI (tried, **not adopted**) | 5.6 % | 5.7 % | 83.8 % | 93.2 % |

- **The three small fixes change no dev row** (no dev sentence starts with "Yes"/"No" or has a comma title or a
  label number); they fix the cases seen live: on the M4 premise, "No, the limit … does not apply if the employee
  was dismissed for whistleblowing." went from contradiction 0.999 (rolled back) to 0.002 (emitted).
- **Citation-anchored NLI does not help on dev.** It judges a sentence that no candidate entails on the windows of
  the provision it cites. It fixes the M4 sentence ("According to section 124(1ZA) … the lower of £123,543 and
  52 … week's pay": contradiction 0.96 on the s.124(1A) exception → emitted), but fixes no dev false rollback and
  loses 2 of 15 wrong-citation catches (vdev-0143 "section 175(3)" for s.175(4)(a); vdev-0154 "section 214(5)"
  for s.214(3)): anchored to the wrongly cited subsection the sentence reads neutral, and its grounded citation
  then lets it through. Removed from the code; recorded here.
- Still open: a correct statement of a rule can be judged against its exception (M4); a real but wrong citation
  ground ("section 100" for whistleblowing; the premise does not say what s.100 covers) passes.

## Rollback round trip on the L4, profiled (2026-10-06)

`scripts/modal_m4.py::latency` + `scripts/m4_profile.py`: same image, GPU (NVIDIA L4), generator and 759-token
s.124 prompt as M4; median of 7 (HTTP GET: 20). Two servers in turn: bf16 weights (as M4) and online FP8 weights
(`--quantization fp8`; the L4 is Ada, native FP8). GPU time about 10 min. Raw: `results/m4-profile.json`.

| | bf16 | FP8 |
|---|---:|---:|
| HTTP + server round trip, no model work (`GET /get_model_info`) | 1.5 ms | 1.5 ms |
| **Warm one-token request = resubmit after a rollback** (759 cached, 1 new token) | **117 ms** | **69 ms** |
| Decode step (from 16 vs 64 new tokens) | 52.9 ms (18.9 tok/s) | 30.3 ms (33.0 tok/s) |
| First token minus one decode step | 64 ms | 38 ms |
| Masked one-token request (allow / ban) | 125 / 124 ms | 75 / 75 ms |
| Cold one-token request (cache flushed, 759-token prefill) | 270 ms | 170 ms |

Findings:
- **The warm round trip is model work, not overhead.** HTTP and scheduling are 1.5 ms. A decode step is the
  L4's memory-bandwidth floor (7.6 B parameters × 2 bytes ≈ 15 GB per token at ≈ 300 GB/s ≈ 50 ms); the rest
  of the first token (64 ms) is the "extend" forward over the one uncached token, which SGLang runs without CUDA
  graphs (server log: `#cached-token: 759 … cuda graph: False`), while later tokens run graphed.
- **"< 30 ms abort/resubmit" (vault 04, 07 §5) is below one forward pass of a 7B model on an L4** in bf16
  (53 ms) and only reachable in FP8 for a decode step (30 ms), not for the resubmit (69 ms). The measured floor is
  what the grid can quote: **117 ms bf16 / 69 ms FP8**, against 270 / 170 ms for a full re-prefill of the prompt.
- **The server-side mask costs ≈ 7 ms per constrained token**; an allow-list over Qwen's per-digit figures
  (8 tokens for " £123,543") is ≈ 1 s in bf16, which the grid reports inside 4B's remediation latency.
- Not tried: graphing the extend path (an SGLang option, version-dependent), and whether FP8 changes Qwen's
  answers. The grid runs bf16 as specified unless you choose otherwise.

## 2x2 grid results (2026-10-07; method in `docs/GRID.md`)

103 router concept `test` prompts × 4 cells, one shared detector, at most 3 retries. Generators: Gemini
`gemini-3.8-flash-high` via the router (4A full retry, 4C continuation; verifier on the Apple M4) and Qwen 2.5
7B-Instruct bf16 on SGLang 0.5.21, one Modal L4 (4D full retry, 4B in-flight rollback; verifier on the L4).
Raw: `results/grid/{4A,4B,4C,4D}.jsonl`, `summary.json`, `judge.jsonl`, `report.json`.

| | 4A Gemini retry | 4C Gemini continuation | 4D Qwen retry | 4B Qwen in-flight |
|---|---:|---:|---:|---:|
| Blind sample labels (human; wording AI-assisted): correct (20 per cell) | 19 | 19 | 16 | 18 |
| Judge `gpt-oss-120b-medium`: correct (103) | 83 (80.6 %) | 91 (88.3 %) | 81 (78.6 %) | 75 (72.8 %) |
| Rule A pass (103) | 97.1 % | 97.1 % | 39.8 % | 45.6 % |
| Detector: clean first draft / remediated / unresolved | 63 / 31 / 9 | 61 / 30 / 12 | 53 / 20 / 30 | 55 / 29 / 19 |
| Visible tokens discarded per answer (mean) | 82 | 90 | 110 | 67 |
| Time to first released output (median) | 16.1 s | 11.6 s | 8.1 s | 3.8 s |
| Wall-clock per answer (median) | 16.1 s | 16.5 s | 8.1 s | 7.9 s |
| Verification time per answer (median) | 7.0 s (M4) | 5.8 s (M4) | 0.7 s (L4) | 0.6 s (L4) |
| Visible tokens / s (median) | 19.6 | 18.2 | 17.0 | 16.5 |

**No single scorer is reliable enough to be the headline.**
- Rule A agrees with the blind labels on Gemini (20/20 in 4A and 4C) but not on Qwen (4B 14/20, 4D 8/20):
  Qwen's answers mostly do not name the section, which rule A requires. Rule A measures a citing habit as much
  as correctness and is not used as a correctness figure.
- The judge agrees with the labels on 68/80 (85 %), **Cohen's κ 0.375** (4A 0.22, 4B −0.11, 4C 1.0, 4D 0.57):
  below what the pre-set rule needs for it to be the headline. Of the 12 disagreements, the judge is stricter on
  sub-section citations (it is right on FOIA s.12(3) vs s.12(4) and IA 1986 s.423(3) vs (2), which the labels
  passed), and misses what its prompt did not define: a refusal sentence in an answerable answer (2), a query
  naming a fictional Act (2: "Family Rights Act 1996", "Data Privacy Act 2018") and one figure-meaning error
  ("support of at least 50 %" for s.226's 50 % turnout rule).
- What holds across all three: Gemini cells ≥ Qwen cells on correctness; with the generator fixed,
  sentence-level remediation releases output sooner (4B 3.8 s vs 4D 8.1 s; 4C 11.6 s vs 4A 16.1 s) and, on the
  judge, is at least as correct for Gemini (4C 88 % vs 4A 81 %) but not for Qwen (4B 73 % vs 4D 79 %: 4B's
  refusals and released misses — see below).
- Gemini's completion tokens are about 80 % thinking; visible output is 18–20 tok/s, about Qwen's on the L4.

**Detector misses on released sentences (judge-flagged; refinement hypotheses, to be tested on dev only)**: 44
sentences the detector passed — dropped qualifier 23, wrong (sub-)citation 6, wrong figure 3, wrong instrument
2, other 10. Plus two systematic gaps the labels show: the detector never checks that a provision or Act named in
the *query* exists in the premise (probes answered as if real), and refusals on answerable prompts come from
false rollbacks exhausting 3 retries.

## Injection A/B (stop 27, 2026-10-07; method in `docs/GRID.md`)

A = 4B as run (allow-list, then ban). B = `4B-inject`: on a rollback, the windows the verifier aligned the rejected
sentence to are written into the KV cache as a user turn (`turn` format, chosen on 40 dev prompts), and the
sentence is regenerated. Same L4, Qwen 2.5 7B bf16, SGLang 0.5.21, 103 test prompts, auditor, and 3 retries.
**Parity:** 4B re-run on 10 test prompts in a fresh container gave 10/10 identical answers to the stored run.
Raw: `results/grid/4B-inject.jsonl`, `inject_ab.json`, `4B-parity.jsonl`, `dev/`.

| Per rollback point | A: 4B (allow/ban) | B: 4B-inject |
|---|---:|---:|
| Claim check rejected: first retry passed | 11/40 (28 %) | **26/31 (84 %)** |
| Claim check rejected: recovered / refused | 21 / 27 | 29 / 3 |
| NLI rejected: first retry passed | 11/27 (41 %) | **19/25 (76 %)** |
| NLI rejected: recovered / refused | 20 / 10 | 23 / 3 |
| Answers with a refusal sentence | 19 | 3 |
| Retries with a prefix-cache hit (prefix reused, only the source prefilled) | n/a | 56/56 |
| Tokens injected per injection (median) | n/a | 196 |
| Visible tokens discarded per answer (mean) | 67 | 33 |
| Time to first output / wall-clock (median) | 3.8 s / 7.9 s | 3.8 s / 6.5 s |

| Per answer (103) | A: 4B | B: 4B-inject | 4D (Qwen retry) |
|---|---:|---:|---:|
| Judge: correct | 75 (72.8 %) | **63 (61.2 %)** | 81 (78.6 %) |
| Judge: answerable / abstention correct | 67/92 · 8/11 | 59/92 · 4/11 | 71/92 · 10/11 |
| Judge: has an unsupported or contradicted sentence | 22 | **17** | 17 |
| Judge: does not answer the question | 13 | **24** | 6 |
| Rule A pass | 45.6 % | 37.9 % | 39.8 % |

**What the A/B shows.**
- **The mechanism works as designed.** Truncate, inject the flagged provision into the cache, regenerate: the
  prefix is reused on every retry, and the cheap model's retry passes the auditor 2.5–3× as often. Refusals
  almost disappear (37 → 6 points), and half as many tokens are thrown away.
- **Faithful to the chunk, often literally.** 21 of 50 recovered sentences are ≥ 80 % verbatim from the statute
  (5-word overlap), against 1 of 41 in A. 4 sentences are the injected heading copied back (`[Taxes Management Act
  1970, section 36(1A) (…)]`; 2 counted as recoveries). A and 4D have none. The `note` format did this more (6 in
  40 dev prompts).
- **It optimises against the auditor, not the question.** The auditor checks that a sentence is grounded, not
  that it answers the query. Given a provision, Qwen states *something true from it*, often a side limb: "(2)
  Subsection (1) does not exempt…" for "FOI request refused cost exceeds limit"; "Subsection (2) has effect subject
  to sections 832, 833A and 835" for "dividends only out of profits". Unsupported answers fall (22 → 17), but
  answers that miss the question nearly double (13 → 24). On the 47 prompts where A and B differ, the judge passes
  A on 29 and B on 16.
- **Abstention is lost.** On the fictional-provision probes, A's refusals were correct abstentions (8/11). B
  recovers instead of refusing, with a grounded but irrelevant sentence ("A penalty under this section is payable
  to the regulator…"): 4/11. The refusal was doing the abstaining, and injection removes it.
- Judge noise: of the 56 answers identical in A and B, the judge (temperature 0) gave the same verdict 49 times.
  About 12 % of single verdicts flip on re-ask, so a gap of a few answers is not a difference. 12 answers is
  beyond that; the off-topic count is consistent with the examples above.

**Verdict on the goal "inject the right statutory chunk → even a cheap model is more faithful to it":**
**holds**, measured at the auditor and by the judge's grounding labels. **Not yet production-ready as a whole**,
because faithfulness to the chunk is not faithfulness to the question: the loop needs a relevance signal (the
query restated in the injected turn, and/or a query-relevance check in the auditor) and an abstention rule (a
point that needs injection on a probe naming a provision absent from the premise should refuse). Both are design
changes to test on the dev split before a re-run.

**Same-state reading (stop 29, from the same traces, no new run).** A and B are identical up to the first rollback,
so all 48 answers with a rollback give a state both arms retried from. First retry passed **19/48 in A and 39/48 in
B** (both 18, only A 1, only B 21; exact McNemar p = 1.1e-5); B inserted a provision on 47 of the 48. After that
point, first drafts of the later sentences passed 35/65 in A and 31/41 in B (A's later sentences include the hedging
that follows a refusal). The states rebuild exactly from the traces with the generator's tokenizer (prompt, committed
text, inserted source, and B's prefix-cache hit). Raw: `results/grid/replay_states.json`; `inject_ab.json` now
carries both figures. The placement and attention replay on these states is specified in `docs/GRID.md` § Stop 29.

## Placement and attention replay (stop 29, 2026-10-07; method in `docs/GRID.md`)

The 47 states where A and B reached the same first rollback and B inserted a provision, replayed on the same L4,
Qwen 2.5 7B bf16, SGLang 0.5.21 and auditor; then an attention and likelihood replay in transformers 5.12.1
(eager attention, bf16) on the recorded tokens. Parity: 46/47 states re-decoded the recorded rejected draft
(uk-concept-0150 did not and is dropped). The replays reproduced the recorded retries on 43/44 (A) and 43/46 (B).
On 2 states A's own retry decoded nothing and the point was refused; R0 there is that recorded refusal.
Raw: `results/grid/replay/arms.jsonl`, `attention.jsonl`, `report.json` (`scripts/replay_report.py`).

| First retry, 46 states | Passed the auditor | Against R1 (only R1 / only the other; exact McNemar) |
|---|---:|---|
| R0: A's retry (allow-list or ban) | 18 | 22 / 1, p = 5.7e-6 |
| **R1: provision inserted at the cut point** | **39** | |
| R2: R1 with the cache emptied first | 39 | same pass or fail on all 46; same tokens on 44 |
| R3: the same provision text at the top, after the query | 17 | 24 / 2, p = 1.1e-5 |
| R4: R1's turn without the provision | 14 | 26 / 1, p = 4.2e-7 |

| Recorded tokens replayed, 46 states | With the inserted turn vs without | Exact sign test |
|---|---|---|
| log P of R1's regenerated sentence | higher in 46/46, median +40.2 nats | p = 2.8e-14 |
| log P of the rejected draft | lower in 45/46, median −32.4 nats | p = 1.3e-12 |
| Attention share on provision text, R1's sentence, all layers | higher in 46/46, median +0.065 | p = 2.8e-14 |
| Same, layers 0–8 / 9–18 / 19–27 | higher in 45 / 46 / 45, median +0.037 / +0.094 / +0.066 | |
| Same, the next sentence (18 states that have one) | higher in 18/18, median +0.044 | p = 7.6e-6 |
| log P of R1's sentence, inserted vs provision at the top | higher in 45/46, median +28.1 nats | p = 1.3e-12 |
| Attention share on provision text, inserted vs at the top | higher in 34/46, median +0.015 | p = 0.0016 |

Median attention share of R1's sentence by span: without the inserted turn, the windows that are later inserted
0.109 and the other windows 0.118; with it, the inserted copy 0.166, the original copy of the same windows 0.053
and the other windows 0.071; with the provision at the top, the top copy 0.128. All five primary comparisons hold
after Holm correction (largest adjusted p = 1.1e-5).

Other figures. One-token request on R1's input: 105 ms with the cache warm, 337 ms cold (median). The answer ended
right after the retry in 28/46 states for R1, against 17/44 for R0, 17/46 for R3 and 12/46 for R4. First drafts of
the 2 follow-on sentences passed R0 25/39, R1 19/26, R3 24/39, R4 28/51 (small samples).

**Replay fidelity is below the 95 % bar set in the method**: the transformers replay's top token equals the
recorded token at 92.0 % of rejected-draft positions, 94.3 % of regenerated-sentence positions and 91.8 % of
next-sentence positions. It does not vary with context length (102 to 14,164 tokens). The likely source is the two
bf16 kernel paths (SGLang/FlashInfer vs transformers eager); this is not verified. The attention and likelihood
results therefore carry this caveat. Each effect above points the same way in 45 or 46 of 46 states.

**What the replay shows.**
- **Position, not presence.** The provisions were in the system prompt all along. The same provision text placed
  at the top (R3) does no better than A's decode-level retry (17 vs 18). Placed at the cut point (R1) it passes 39.
- **Content, not the turn break.** R1's turn without the provision (R4) passes 14.
- **The cache is a cost saving, not a quality change.** Emptying it first (R2) changes the pass on no state and
  the tokens on 2 (bf16 numerics); it triples the time of the first request.
- **Insertion moves probability and attention toward the provision.** The regenerated sentence becomes more likely
  in every state and the rejected draft less likely in 45 of 46. Attention to provision text rises in every state;
  the inserted copy takes the most, and attention to the original copy halves. The shift persists in the next
  sentence. Attention describes where the model looked; the likelihood figures carry the causal reading.
- **Insertion also ends answers early** (28/46 vs 17/44), in line with stop 27's shorter, more often off-topic
  answers.

## Injection v2 (stop 30, 2026-10-07 and 2026-10-08; method in `docs/GRID.md`)

v2 changes two things against 4B-inject (v1): the inserted turn restates the question in positive wording, and
legal-rag-router 0.1.0 runs before generation and answers the queries it refuses with its own message.

**Dev pilot** (first 40 dev prompts, v1 `dev/4B-inject-turn` against v2, same judge). Judged to address the question
35 vs 32; judged correct 26 vs 24; first retry passed 81 % of rollback points. The pre-set rule passed, so the test
run went ahead. Raw: `results/grid/dev/4B-inject-v2.jsonl`, `dev/judge.jsonl`.

**Gate.** The router refused exactly the 11 abstention probes on test and nothing on dev (0/112). All 215 statuses
match the battery's expected labels. Raw: `batteries/grid/routes-{dev,test}.json`.

**Test** (103 prompts; judged 103/103, the last 8 on 2026-10-08 after a router 503). Judge counts:

| | v2 | 4B | 4B-inject (v1) | 4D |
|---|---|---|---|---|
| Correct, all 103 | 67 | 75 | 63 | 81 |
| Correct, 92 answerable | 67 | 67 | 59 | 71 |
| Correct, 11 abstention probes | 0 | 8 | 4 | 10 |
| Answerable, not addressing the question | 12 | 5 | 16 | 2 |
| Answerable, with an unsupported or contradicted sentence | 13 | 20 | 16 | 17 |

Per rollback point (`scripts/grid_inject.py`). v2 has fewer points because the 11 probes never reach generation.

| | v2 | 4B | 4B-inject (v1) |
|---|---|---|---|
| Rollback points | 49 | 78 | 58 |
| First retry passed, claim check | 20/22 (91 %) | 11/40 (28 %) | 26/31 (84 %) |
| First retry passed, NLI | 19/27 (70 %) | 11/27 (41 %) | 19/25 (76 %) |
| Points ending in a refusal | 4 | 37 | 6 |
| Inserted retries with a prefix-cache hit | 53/53 | — | 56/56 |
| Answers ending right after an inserted recovery | 19/36 | — | 27/44 |
| Time to first output, median | 3.15 s | 3.84 s | 3.75 s |
| Wall time, median | 6.24 s | 7.89 s | 6.45 s |
| Tokens discarded, mean | 29.4 | 66.7 | 33.4 |

**Pre-set reading.** It needed at least 75/103 correct and 8/11 correct abstentions. v2 scored 67 and 0, so it
fails as written. The verdict stands and injection work stops for 0.1.0. The judge rated all 11 router refusals
incorrect as unsupported claims about the named Act or section; its prompt accepts only claims the provisions
support. It marked 7 of the 11 as abstaining. Re-judging them with an amended prompt would be a post hoc change
to the protocol and was not done (decision 2026-10-08).

**What v2 shows.** On the answerable prompts v2 matches 4B on correct answers (67 vs 67) and is 8 above v1. It has
fewer answers with an unsupported sentence than 4B (13 vs 20). Answers that miss the question fall from 16 to 12
against v1 but stay above 4B's 5. Each of these gaps is under the judge's noise of about 10 answers. Restating the
question recovers part of the relevance loss, not all of it. The claim-check retry pass rises to 91 %, the cache
is hit on every inserted retry, and time to first output is the lowest of the three in-flight cells. The router
gate selects the right 11 queries; the judge protocol, not the gate, decides the abstention score.

## Rollbacks and retries labelled (stop 36, 2026-10-08; method in `docs/GRID.md`)

The 46 stop 29 states, labelled blind per sentence. The labeller is Claude Opus 5.5 at effort xhigh, run by you
outside this repository on the sheet only. These are model labels, not human labels. Raw:
`results/grid/rollback/labels.csv`, `report.json` (`scripts/rollback_review.py report`).

| Per arm, 46 states | X rejected draft | R0 decode steering | R1 inserted at the cut | R3 at the top | R4 turn, no provision |
|---|---|---|---|---|---|
| Supported | 21 | 17 | 33 | 27 | 26 |
| Unsupported or contradicted | 18 | 26 | 9 | 8 | 14 |
| No claim | 7 | 1 | 4 | 8 | 6 |
| No text (refused or empty) | 0 | 2 | 0 | 3 | 0 |
| Does not read on (fragment, pasted text, repeat) | 1 | 1 | 28 | 0 | 1 |
| Off the question | 1 | 1 | 17 | 2 | 1 |
| Good (supported, on the question, reads on) | 21 | 17 | 11 | 26 | 26 |
| Accepted by the auditor | 0 | 18 | 39 | 17 | 14 |
| Accepted but not good | — | 8 | 30 | 5 | 6 |
| Accepted and unsupported or contradicted | — | 8 | 5 | 3 | 6 |

**Readings, set before labelling.**
- P1 fails. 18 of 46 rejected drafts are real errors (39 %, Wilson 95 % 26 to 54 %), against the 80 % bar and the
  89 % rollback precision on the sealed battery. By what rejected the draft: the claim check 10 of 27, NLI 8 of 19.
  7 rejected drafts make no claim: 6 are correct refusals of a provision that does not exist, 1 a wrong refusal.
- P2 fails. Good retries: R1 11, R0 17 (only R1 6, only R0 12; exact McNemar p = 0.24). Secondary, Holm-corrected:
  R3 26 and R4 26 both beat R1 (p = 0.003 each).
- P3. Supported but off the question: R1 9, every other arm 0 or 1.

**Descriptive, not set before labelling.** On grounding alone R1 leads: supported 33 against R0 17 (only R1 19,
only R0 3; p = 0.0009), R3 27 (p = 0.21) and R4 26 (p = 0.19). R1 retries are rarely wrong (9 of 46), but 28 of
them do not read on: the model pastes the inserted provision, often with its label, or starts mid-clause. The
auditor accepts that text because it is the provision. Of the 39 R1 retries the auditor accepted, 30 are not good
and 5 are wrong.

**What this shows.** On live statute output most rejections were not errors, so most of the work the loop did
was unneeded. Inserting the provision makes the retry grounded, as the auditor measured, but not usable: it
copies the provision instead of continuing the answer. A retry with no provision (R4) or with the provision at
the top (R3) was good more than twice as often. The auditor's pass rate overstated the mechanism's benefit; that
is the gap stop 36 was set up to measure. The labels come from one model and one run; the software battery
(stop 37) checks the same questions by hand.

## Software battery, graded by you (stop 37, 2026-10-08; method in `docs/GRID.md`)

40 software questions with verbatim documentation as the premise (`batteries/software/`), Qwen 2.5 7B on one L4,
the same auditor as the statute runs. You graded 103 texts blind, without AI help. Raw: `results/software/`,
`results/software/review/grades.csv`, `report.json` (`scripts/software_review.py report`).

**Run.** 12 of 40 answers rolled back (21 points in 4B, 23 in 4B-inject-v2); all 12 gave a shared state. Every
inserted retry hit the prefix cache (14 of 14). Median time to first output 1.68 s (4B) and 1.71 s (v2); median
wall time 3.9 s for both. 4B wrote the refusal sentence at 11 points in 6 answers, v2 at 10 points in 6 answers.

| Part A, 12 shared states | Rejected draft | 4B retry (steering) | v2 retry (inserted) |
|---|---|---|---|
| Correct | 11 | 10 | 9 |
| Answers the question | 12 | 12 | 9 |
| Reads well | 10 | 10 | 9 |
| Good (all three) | 9 | 8 | 7 |
| Accepted by the auditor | — | 6 | 5 |
| Accepted but not correct | — | 0 | 2 |

| Part B, 40 questions | Plain answer | 4B final | v2 final |
|---|---|---|---|
| Correct | 32 | 32 | 30 |
| Answers the question | 40 | 37 | 40 |
| Good (correct and answers) | 32 | 29 | 30 |

**Readings, set before the run.**
- S1 fails. 1 of 12 rejected drafts was wrong (8 %, Wilson 95 % 1 to 35 %), against the 80 % bar.
- S2 fails. Good retries: v2 7, 4B 8 (only v2 1, only 4B 2; exact McNemar p = 1.0).
- S3 fails. Good answers against plain: 4B 29 against 32 (loop better on 0, worse on 3; Holm p = 0.5); v2 30
  against 32 (better on 1, worse on 3; Holm p = 0.63).

**Where the loop changed the outcome.** 8 plain answers were wrong. The auditor flagged 4 of them after the fact
(4D), and the in-flight loop rolled back on 3. The loop fixed 1 (sw-37) in both cells. 5 wrong plain answers had
no rollback. 9 rollbacks fell on questions whose plain answer was correct. Where the loop made an answer worse,
the cause was the refusal sentence replacing correct content, repeated up to three times (sw-05, sw-19, and sw-31,
where v2 also pasted an unrelated line of the documentation), or a new error in a retry (sw-06, sw-11, sw-35).

**What this shows.** In a domain you can judge, the auditor's rejections were almost all wrong, and it missed most
of the wrong answers. The rollback mechanism ran as designed: cache reuse on every inserted retry and no added
latency to speak of. But because the decisions to roll back were mostly false, the loop could only lose: its
answers were no better than one plain generation and slightly worse. This agrees with stop 36 on the statute set
(18 of 46 rejections real, by model labels). 12 states and 40 questions show only large effects, and the S1 gap is
large.

## The question in the entailment check (stop 40, 2026-10-08; method in `docs/GRID.md`)

The auditor re-run offline on texts already labelled: 34 software texts (your grades) and 212 statute texts (Claude
Opus 5.5's labels). Only the entailment model's input changed. V0 is as run and reproduced every recorded verdict.
V1 puts the question before the sentence, V2 also adds the previous sentence, V3 puts the question before every
source chunk. Raw: `results/nli_context/`.

| Set | Variant | False rollbacks | Errors caught |
|---|---|---|---|
| Software (28 right, 6 wrong) | V0 | 19 | 4 |
| | V1 | 18 | 6 |
| | V2 | 14 | 5 |
| | V3 | 17 | 3 |
| Statutes (116 right, 73 wrong) | V0 | 56 | 51 |
| | V1 | 51 | 47 |
| | V2 | 48 | 43 |
| | V3 | 39 | 41 |

No variant met the bar set before scoring (halve false rollbacks and keep 90 % of catches, on both sets). Each one
made the entailment model more lenient and let right and wrong text through in about the same ratio. With V3, words
from the question started to count as evidence. About half the false rollbacks on statutes come from the claim check,
which these variants do not touch.

## Derived facts for the entailment check (stop 41, 2026-10-09; method in `docs/GRID.md`)

Gemini 3.8 flash high read each of the 40 software sources once and wrote the facts that follow from them. Code kept
a fact only when its quotes were verbatim and its figures held: 227 of 231 kept, 54 derived. The facts were added
as extra entailment candidates (S), and in a diagnostic arm also given to the claim check (S-claims). The audit ran
on one Modal L4. Raw: `results/normalise/`.

| Level | Arm | False rollbacks | Errors caught | Accuracy |
|---|---|---|---|---|
| Part A, 34 sentences (28 right, 6 wrong) | V0 | 19 | 4 | 38 % |
| | S | 13 | 4 | 56 % |
| | Claim check only | 1 | 2 | 85 % |
| | No auditor | 0 | 0 | 82 % |
| Part B, 40 answers (32 right, 8 wrong) | V0 | 9 | 4 | 68 % |
| | S | 9 | 3 | 65 % |
| | Claim check only | 1 | 1 | 80 % |
| | No auditor | 0 | 0 | 80 % |

S-claims matched S on every count. S missed the bar set before scoring (Part A at most 9 false rollbacks). The
facts fixed the ddof case and 6 other Part A sentences. They broke 4 right texts that V0 passed, by giving the
entailment model a closely related candidate to misread as a contradiction. Of the 23 false rollback sentences left,
20 had a fact on the judged passage, often one that says the same thing. Entailment time per sentence: 93 ms V0,
87 ms S.


## A reasoning LLM as the auditor's judge (stop 42, 2026-10-09; method in `docs/GRID.md`)

The entailment check's model was replaced by a judge that reads the clause, the auditor's candidate passages and
the answer so far, and says supported, contradicted or not stated. Judges: Gemini 3.8 flash high through the
router, and Qwen3.8-27B-FP8 on one Modal H100 at low and xhigh effort. Replace lets the judge decide every clause.
Strict also rolls back every not-stated sentence. Appeal keeps V0 and lifts an entailment-only rollback the judge
supports. MiniCheck and ModernBERT-large NLI ran as single-pass controls, with thresholds from the dev battery.
Raw: `results/auditor_judge/`.

| Arm | Part A false rollbacks | Part A caught | Part A accuracy | Part B false rollbacks | Part B caught | Part B accuracy |
|---|---|---|---|---|---|---|
| V0 | 19 | 4 | 38 % | 9 | 4 | 68 % |
| Claim check only | 1 | 2 | 85 % | 1 | 1 | 80 % |
| MiniCheck | 9 | 2 | 62 % | 5 | 4 | 78 % |
| ModernBERT-large | 4 | 4 | 82 % | 3 | 3 | 80 % |
| Gemini, Replace | 5 | 5 | 82 % | 2 | 5 | 88 % |
| Qwen low, Replace strict | 1 | 5 | 94 % | 1 | 4 | 88 % |
| Qwen xhigh, Replace strict | 3 | 5 | 88 % | 3 | 6 | 88 % |

Part A has 28 right and 6 wrong sentences, Part B 32 right and 8 wrong answers. These three judge arms pass the
bar set before scoring on both levels. No Appeal arm and no control does. On statutes (Claude's labels) no arm
passes, because the claim check gives half the false rollbacks. The judges raise accuracy there from 59 % (V0) to
64 to 68 %. Latency per clause: Gemini p50 4.3 s, p95 12.5 s; Qwen low one at a time p50 2.6 s, p95 10.0 s;
Qwen xhigh one at a time p50 4.0 s, p95 87.5 s. Replace adds 8.5 to 34 s per Part B answer, Appeal 1.4 to 9 s.

## A distilled judge and the fresh test (stops 43 to 47, 2026-10-09 and 2026-10-10; method in `docs/GRID.md`)

Aim: a judge that answers without thinking, close to a frontier teacher, within 2 s p95 per clause.

Teacher check on the stop 42 sets (stop 44), Replace strict accuracy:

| Arm | Part A | Part B | Statutes |
|---|---|---|---|
| Gemini per clause | 82.4 % | 82.5 % | 68.3 % |
| Opus 4.6 batched | 94 % | 85 % | not run in full |
| Opus 5.5 batched | 88 % | 80 % | not run |
| Qwen 27B thinking off, untrained | 94 % | 80 % | 67 % |
| K2 Horizon 7B low effort, untrained | 88.2 % | 80.0 % | 66.7 % |

Batched teacher calls agreed with per-clause calls on 92.8 % of clauses but lost 2 texts on Part A, so teachers
ran per clause. Opus 4.6 hit the router limit after 167 calls. Gemini alone labelled the training data.

Training data (stop 45): 472 sources disjoint from every test set, 1,416 questions, 2,832 answers by Qwen 2.5 7B,
4,433 clauses labelled by Gemini. Train 4,018, validation 415. Opus 5.5 agreed with Gemini on 410 of 500 audited
labels.

Student (stop 46): K2 Horizon 7B, LoRA rank 16, one epoch, 34 min on an H100. Validation agreement with Gemini
89.2 %. On the dev sets it scored 76.5 % on Part A and 80.0 % on Part B, against Gemini's 82.4 % and 82.5 %.
Latency one at a time on an L40S: p50 1.2 s, p95 1.7 s. Untrained K2 at low effort: p50 1.5 s, p95 3.9 s.

Fresh test (stop 47): 80 new questions, 160 answers (with the source and closed-book), 360 sentences graded by you:
210 yes, 148 no, 2 unsure. Scored once. Each cell is false rollbacks / wrong sentences caught, then accuracy.

| Arm | Software | Statutes | Total |
|---|---|---|---|
| No auditor | 0 / 0, 68.8 % | 0 / 0, 49.5 % | 0 / 0, 58.7 % |
| Claim check only | 7 / 5, 67.6 % | 9 / 30, 60.6 % | 16 / 35, 64.0 % |
| V0 | 22 / 18, 66.5 % | 20 / 60, 70.7 % | 42 / 78, 68.7 % |
| Gemini, Replace | 12 / 21, 74.1 % | 18 / 62, 72.9 % | 30 / 83, 73.5 % |
| Qwen 27B thinking off, untrained, Replace | 10 / 22, 75.9 % | 11 / 56, 73.4 % | 21 / 78, 74.6 % |
| K2 low, untrained, Replace | 9 / 20, 75.3 % | 10 / 51, 71.3 % | 19 / 71, 73.2 % |
| Qwen 27B low, Replace strict | 16 / 48, 87.6 % | 19 / 89, 86.7 % | 35 / 137, 87.2 % |
| K2 student, Replace strict | 24 / 50, 84.1 % | 28 / 90, 82.4 % | 52 / 140, 83.2 % |

The student meets the distillation reading: it is above Gemini on both domains and its p95 is 1.7 s. It is 4.0
points below Qwen 27B low. Only the two untrained Replace arms pass the stop 40 bar, on software and in total. No
arm passes it on statutes.

Added after the run, not pre-registered. Every judge under both placements, total:

| Judge | Replace | Replace strict |
|---|---|---|
| Gemini | 30 / 83, 73.5 % | 62 / 146, 82.1 % |
| Qwen 27B low | 26 / 86, 75.4 % | 35 / 137, 87.2 % |
| Qwen 27B thinking off, untrained | 21 / 78, 74.6 % | 26 / 132, 88.3 % |
| K2 low, untrained | 19 / 71, 73.2 % | 22 / 119, 85.8 % |
| K2 student | 28 / 78, 72.6 % | 52 / 140, 83.2 % |

Strict adds 9 to 14 points for every judge, because most wrong sentences are not stated in the source. Under the
same placement the student matches Gemini (83.2 % against 82.1 %) and is 2.6 points below the untrained K2, with
more than twice its false rollbacks. On answers written with the source (141 right, 22 wrong) no auditor scores
86.5 % and the best arm 88.3 %. On closed-book answers (69 right, 126 wrong) no auditor scores 35.4 % and the
strict arms 83 to 89 %. The claim check rolls back 12 right sentences before any judge, 3 of them list numbers
split off by the segmenter. One prompt with the whole sheet agreed with your grades on 329 of 360 sentences
(Gemini) and 349 of 360 (Opus 5.5); the same Gemini model as the per-clause judge scores 82.1 %.

Spend: Modal $6.46 of $55, Opus 5.5 $7.67 of $40. Raw: `results/distill/`, `results/fresh/`.

## An awareness signal for the auditor (stop 48, 2026-10-10; method in `docs/GRID.md`)

Aim: read from the model itself whether it was using its input, and use that to catch wrong sentences
(generator) or wrong labels (judge). Two measures: the share of attention on the input, and how much the input
raises the likelihood of the text. Measured on the 358 graded fresh sentences. Candidate and threshold are chosen
on half of the questions and scored on the other half.

| Direction | Model | Best candidate on the other half (AUROC) | Gate (0.65 each, 0.70 mean) |
|---|---|---|---|
| Generator | Qwen 2.5 7B | 0.58 and 0.56, within the same kind of answer | Failed |
| Judge | K2 Horizon 7B, low effort | 0.53 and 0.62 | Failed |
| Judge | Qwen3.8 27B, thinking off (bf16) | 0.43 and 0.42 | Failed |

The retry loop (stop 49) did not run. As an auditor the generator signal scores 68.7 % alone and 71.5 % after the
claim check, against 68.7 % for V0 and 83 to 88 % for the strict judges of stop 47. On answers written with the
source its best threshold rolls back nothing.

Why it fails for the judges: 28 of K2's 37 wrong labels and 15 of Qwen's 29 are supported on a wrong sentence, and
those attend to the passages as much as right supported labels do. The signal tracks the label and the length of
the passages. On software, where passages are short, it separates (0.74 to 0.80 on 10 to 16 wrong labels). A second
sample of the same prompt turns as many labels wrong as right (K2 9 and 11, Qwen 4 and 4).

Why it fails for the generator: over all sentences the likelihood measure scores 0.82, but that mostly tells a
closed-book answer from one written with the source. Within one kind of answer it scores 0.67.

Caveats: the fresh test was already used after stop 47. The transformers replay matches the recorded token at
88 % of positions. Qwen 27B ran from bf16 weights, not the FP8 weights of stop 47. Spend: $3.79, Modal $10.25 of
$55. Raw: `results/awareness/`.

## Gemini 3.1 Pro as a per-clause judge (stop 50, 2026-10-10; method in `docs/GRID.md`)

Aim: test one more teacher candidate on data already held. `gemini-3.1-pro-low` labelled the 323 fresh clauses,
the 280 stop 42 clauses and the 500 training clauses Opus 5.5 audited, with the stop 42 prompt unchanged.

Fresh test, 358 graded sentences, Replace strict (false rollbacks / caught, accuracy):

| Judge | Total | With source | Closed-book |
|---|---|---|---|
| Gemini 3.1 Pro low | 35 / 142, 88.5 % | 15 / 20, 89.6 % | 20 / 122, 87.7 % |
| Qwen 27B thinking off, untrained | 26 / 132, 88.3 % | 12 / 13, 87.1 % | 14 / 119, 89.2 % |
| Qwen 27B low | 35 / 137, 87.2 % | 14 / 17, 88.3 % | 21 / 120, 86.2 % |
| K2 low, untrained | 22 / 119, 85.8 % | 10 / 12, 87.7 % | 12 / 107, 84.1 % |
| K2 student | 52 / 140, 83.2 % | 25 / 17, 81.6 % | 27 / 123, 84.6 % |
| Gemini 3.8 Flash high | 62 / 146, 82.1 % | 29 / 21, 81.6 % | 33 / 125, 82.6 % |

Pro beats Flash: only Pro is right on 29 sentences and only Flash on 6 (sign test p = 0.0001). Pro is not told
apart from the untrained Qwen 27B (14 against 13) or the untrained K2 (28 against 18, p = 0.18).

Stop 42 sets, Replace strict: Pro 94.1 % on Part A, 77.5 % on Part B and 67.7 % on statutes, against Flash's
82.4 %, 82.5 % and 68.3 %. These sets are small (34 and 40 texts for Part A and B).

On the 500 audited training clauses Pro agrees with Opus 5.5 on 90.4 % and with Flash on 90.2 %; Flash and Opus
5.5 agree on 82.0 %. Where those two differ, Pro sides with each about half the time (44 and 43 of 90). Not stated
labels: Flash 202, Pro 159, Opus 5.5 121.

Cost at list prices: $0.0098 per clause, $10.81 for 1,103 calls. Time through the router: p50 5.4 to 6.1 s per
clause. Caveats: the fresh test has been used since stop 47; Opus 5.5 has no per-clause labels on it. Raw:
`results/teacher_pro/`.

## Opus 5.5 as a per-clause judge (stop 51, 2026-10-10; method in `docs/GRID.md`)

Aim: fill the row missing from stop 50. `claude-opus-5-5(high)` labelled the 323 fresh clauses with the stop 42
prompt unchanged.

Fresh test, 358 graded sentences, Replace strict (false rollbacks / caught, accuracy):

| Judge | Total | With source | Closed-book |
|---|---|---|---|
| Opus 5.5 high | 23 / 132, 89.1 % | 12 / 19, 90.8 % | 11 / 113, 87.7 % |
| Gemini 3.1 Pro low | 35 / 142, 88.5 % | 15 / 20, 89.6 % | 20 / 122, 87.7 % |
| Qwen 27B thinking off, untrained | 26 / 132, 88.3 % | 12 / 13, 87.1 % | 14 / 119, 89.2 % |
| K2 low, untrained | 22 / 119, 85.8 % | 10 / 12, 87.7 % | 12 / 107, 84.1 % |
| Gemini 3.8 Flash high | 62 / 146, 82.1 % | 29 / 21, 81.6 % | 33 / 125, 82.6 % |

Opus 5.5 is not told apart from Pro (15 against 13 sentences), the untrained Qwen 27B (19 against 16) or the
untrained K2 (23 against 11, p = 0.058). It beats Flash (40 against 15, p = 0.001) and the K2 student (37 against
16, p = 0.005). No judge tested per clause is above the untrained Qwen 27B.

Added after the run: the claim check rolls back the same 12 right sentences before every judge, half of Opus
5.5's 23 false rollbacks. At least one of the three best judges is right on 94.1 % of sentences; their majority
label scores 90.2 %. The per-clause prompt tops out near 89 to 90 % on this test whatever the model.

Cost: $3.90 for 323 calls, $0.0121 per clause. Time through the router: p50 3.0 s, p95 6.9 s. Caveat: the fresh
test has been used since stop 47. Raw: `results/teacher_opus/`.

## The claim check behind an LLM judge, and the judge's view (stops 52 and 53, 2026-10-11; method in `docs/GRID.md`)

Aim: remove the 12 right sentences the claim check rolled back before every judge, and test a judge prompt that
holds the question and the source as written. Three judges only; K2 is dropped.

The 12: 3 list numbers split off by the segmenter (fixed in `src/`), 4 figures worded differently from the source,
5 that need reasoning. No pattern was added for the last two groups. Instead the judge was asked.

Fresh test, 354 graded sentences after the list fix, Replace strict (false rollbacks / caught, accuracy):

| Judge | List fix | Figures to the judge |
|---|---|---|
| Opus 5.5 high | 19 / 132, 90.1 % | 11 / 132, 92.4 % |
| Gemini 3.1 Pro low | 31 / 142, 89.5 % | 25 / 142, 91.2 % |
| Qwen 27B thinking off, untrained | 22 / 132, 89.3 % | 14 / 132, 91.5 % |

Each judge catches all 29 wrong sentences the claim check holds and passes 6 to 8 of the 9 right ones (gains of
6 to 8 sentences, none lost, p = 0.008 to 0.031). Turning the claim check off entirely gives the same verdicts.
The three judges are not told apart.

Qwen 27B with the question and the source as written scores 91.8 % and, with your grading rule added, 92.1 %,
against 91.5 % for the stop 42 prompt. Neither is a gain (15 against 14 and 13 against 11 sentences).

Caveats: the arms were designed after reading this test's failures, and the test has been used since stop 47. A
clean figure needs a new graded set. Spend: Opus 5.5 $0.66, Pro $0.34, Modal $0.48. Raw: `results/fresh_arms/`.

## Where the judges fail, and notes on applying the labels (stop 54, 2026-10-11; method in `docs/GRID.md`)

The judges' own errors on the 317 fresh sentences that reach them (strict, as stops 47 to 51 scored them):

| Judge | Right sentences rolled back | Wrong sentences passed |
|---|---|---|
| Opus 5.5 high | 11 | 16 |
| Gemini 3.1 Pro low | 23 | 6 |
| Gemini 3.8 Flash high | 50 | 2 |
| Qwen 27B thinking off, untrained | 14 | 16 |

Only 10 sentences are wrong for all three frontier judges. Three patterns: not stated for a small gap the source
leaves (Gemini's main failure, 42 of Flash's labels), contradicted for a dropped qualifier (most of Opus 5.5's
false rollbacks), and supported on a wrong sentence, often a hedged one (16 for Opus 5.5 and for Qwen 27B). The
judges read the passages correctly and differ from the hand grades on where supported ends.

Two notes were added to the stop 42 prompt for Qwen 27B: common background and an obvious name count as support,
and a dropped qualifier is not a contradiction. 354 sentences, Replace strict:

| Prompt | List fix | Figures to the judge |
|---|---|---|
| Stop 42 prompt | 22 / 132, 89.3 % | 14 / 132, 91.5 % |
| With the two notes | 15 / 133, 91.5 % | 8 / 133, 93.5 % |

Both are gains (8 sentences gained and 0 lost, p = 0.008; 8 and 1, p = 0.039). A third note on hedged sentences
added nothing. Caveat: the notes were written from this test's errors and scored on it; the figure needs a new
graded set. Spend: Modal $0.49. Raw: `results/fresh_arms/`.

## Qwen 27B at 4 bits (stop 55, 2026-10-11; method in `docs/GRID.md`)

Aim: see whether a 4-bit Qwen 27B loses accuracy against the official FP8 weights, on the same prompts.

| | FP8, official | AutoRound 4-bit | AMD AWQ 4-bit |
|---|---|---|---|
| Stop 42 prompt, figures to the judge | 14 / 132, 91.5 % | 14 / 135, 92.4 % | not served |
| Two notes, figures to the judge | 8 / 133, 93.5 % | 8 / 130, 92.7 % | not served |
| Same label as FP8 | | 92.8 % and 95.3 % | |
| Time per clause, one at a time, L40S | 3.5 s p50, 4.8 s p95 | 1.8 s p50, 2.8 s p95 | |
| Weights on the GPU | about 31 GB | 18.1 GB | |

AutoRound is not told apart from FP8 (9 against 6 and 3 against 6 sentences) and is about twice as fast. It does
not start on a 24 GB L4. SGLang 0.5.21 cannot load the AMD weights. Spend: $1.61. Raw:
`results/fresh_arms/quant.json`.

## The second fresh test (stop 56, 2026-10-11; method in `docs/GRID.md`)

Aim: confirm on unseen sentences the 93.5 % that three changes gave on the first fresh test. 40 sources drawn by
seed, questions by Gemini Flash, 151 graded sentences (84 right, 67 wrong). Judges labelled before the grades.

| Configuration | False rollbacks / caught | Accuracy |
|---|---|---|
| Qwen 27B FP8, two notes, figures to the judge (as tuned) | 8 / 60 | 90.1 % |
| Qwen 27B FP8, stop 47 configuration | 12 / 63 | 89.4 % |
| Qwen 27B FP8, stop 42 prompt, figures to the judge | 9 / 62 | 90.7 % |
| Opus 5.5, as tuned | 5 / 60 | 92.1 % |
| Gemini 3.1 Pro, as tuned | 10 / 63 | 90.7 % |
| Qwen 27B AutoRound 4-bit, as tuned | 8 / 59 | 89.4 % |
| No auditor | | 55.6 % |

The tuned configuration is not better than the stop 47 one (4 sentences gained, 3 lost, p = 1.0). The level that
holds is about 90 %: 89.4 % here and 89.3 % on the first test for the same untrained judge. The two notes do not
help. Sending figures to the judge frees all 6 right sentences the claim check held and loses 1 wrong one of 16.
No judge is told apart from another, and the 4-bit model matches FP8 (same label on 148 of 153 clauses).

On answers written with the source every judge is below no auditor in this test (88.9 % against 94.4 %): 4 wrong
sentences in 72, of which the judge catches 1 while rolling back 5 right ones. Raw: `results/fresh2_arms/`.

## Qwen 27B as generator and judge (stop 57, 2026-10-11; method in `docs/GRID.md`)

Aim: one model for both roles. Qwen 27B AutoRound 4-bit answered the 40 questions of the second fresh test and
judged its own sentences. Graded by Opus 5.5 and Gemini 3.1 Pro where they agree (checked on the hand-graded set:
97.8 % of what they settle carries the hand grade), and by hand for the 9 sentences they left open.

| | Qwen 27B 4-bit | Qwen 2.5 7B |
|---|---|---|
| Sentences | 114 | 151 |
| Wrong, with the source | 0 of 49 | 1 of 72 |
| Wrong, closed-book | 36 of 65, 55 % | 63 of 79, 80 % |
| No auditor | 68.4 % | 57.6 % |
| Qwen 27B 4-bit judge, strict | 18 / 35, 83.3 % | 10 / 61, 91.4 % |

The judge catches 35 of the 36 wrong sentences in its own answers, and Pro catches no error it passes: no sign
of a self-judging limit. Its accuracy is lower on its own text because it rolls back 18 right sentences, 16 of
them honest refusals in closed-book answers. Without refusal sentences it scores 96.8 % (2 false rollbacks, 31
of 32 caught). Requiring Pro to agree changes no verdict on its own text. Raw: `results/fresh2-q27_arms/`.

## A refusal rule on the judge's side (stop 58, 2026-10-11; method in `docs/GRID.md`)

Aim: stop the strict judge rolling back a sentence in which the generator declines, with one paragraph in the
prompt and no pattern in `src/`. Qwen 27B 4-bit as the judge.

| | Stop 42 prompt | With the paragraph |
|---|---|---|
| Right refusals passed, of 16 (its own answers) | 0 | 3 |
| Its own answers, 114 sentences | 18 / 35, 83.3 % | 16 / 35, 85.1 % |
| The 7B's answers, 151 sentences, hand grades | 10 / 61, 89.4 % | 5 / 62, 93.4 % |

The paragraph does not fix refusals. The judge passes a bare refusal but reads a refusal with a reason ("it
depends on the jurisdiction") as contradicted, because it has the source and the source states the answer. That
is specific to closed-book answers. On the 7B's answers the paragraph gains 6 sentences and loses none
(p = 0.031), half of them fragments with no claim; this was the harm check, so the gain is exploratory. Raw:
`results/fresh2-q27_arms/refusal.json`.

## DeBERTa (V0) on the second fresh test (stop 60, 2026-10-12; method in `docs/GRID.md`)

Aim: the first auditor against the LLM judge on a set nothing was tuned on. 151 sentences, hand grades.

| Auditor | False rollbacks / caught | Accuracy | With source |
|---|---|---|---|
| No auditor | | 55.6 % | 94.4 % |
| Claim check only | 6 / 16 | 62.3 % | 87.5 % |
| V0 (claim check and DeBERTa) | 27 / 31 | 58.3 % | 62.5 % |
| Qwen 27B FP8, stop 47 configuration | 12 / 63 | 89.4 % | 84.7 % |
| Qwen 27B 4-bit, figures to the judge | 10 / 61 | 89.4 % | 87.5 % |

The judge is right on 51 sentences where V0 is wrong, and V0 on 4 where the judge is wrong (p = 2e-11). V0 is
barely above no auditor here and below the claim check alone: DeBERTa rolls back 23 of 68 right sentences in
answers written with the source and catches none of the 4 wrong ones. Raw: `results/fresh2_arms/v0.json`.

## The judge inside the loop (stop 59, 2026-10-12; method in `docs/GRID.md`)

Aim: run the architecture, not replay it. Qwen 27B AutoRound 4-bit is generator and judge on one SGLang server
(one L40S). The engine generates a sentence, the judge checks it, and it is committed or rolled back and retried.
40 questions, two arms. Graded by Opus 5.5 and Gemini 3.1 Pro, 3 open sentences by hand.

| | Source in the prompt | From memory, source inserted on rollback |
|---|---|---|
| Sentences | 49 | 50 |
| Committed at the first try | 48 | 15 |
| Committed after a retry | 1 | 32 |
| Replaced by the refusal | 0 | 3 |
| Graded wrong | 0 | 3, all refusals |
| Same model without a loop | 0 of 49 wrong | 36 of 65 wrong |
| Seconds per answer, p50 and p95 | 3.2 and 11.8 | 5.2 and 13.6 |
| Seconds per judge call, p50 | 1.7 | 1.7 |

80 answers, no error. On a retry the server reuses the committed prefix (at least 98 % of the prompt per decode
call with the source in the prompt). The judge takes about 60 % of the time. With the source in the prompt the
loop changes almost nothing: 39 of 40 answers have no rollback. Starting from memory it cuts 47 drafts, inserts
the source 39 times, and 31 of the 32 sentences it then commits are right; no wrong statement of fact reaches a
final answer. Raw: `results/fresh2-live_arms/live.json`.

## A judge reply without the reason (stop 61, 2026-10-12; method in `docs/GRID.md`)

Aim: cut the judge's time, which is about 60 % of the loop's. The judge is asked for a label and a passage number
only. Qwen 27B 4-bit, both fresh tests, hand grades.

| | With a reason | Without a reason |
|---|---|---|
| First test, 354 sentences | 14 / 135, 92.4 % | 7 / 133, 93.8 % |
| Second test, 151 sentences | 10 / 61, 89.4 % | 8 / 60, 90.1 % |
| Time per clause, p50 and p95 | 1.64 s and 2.81 s | 0.54 s and 1.25 s |
| Tokens written | 61 | 19 |

Accuracy is not lower on either test and the two are not told apart. The call takes a third of the time. Raw:
`results/fresh_arms/short.json`, `results/fresh2_arms/short.json`.

## Two smaller judges, untrained (stop 62, 2026-10-12; method in `docs/GRID.md`)

Aim: a judge near the Qwen 27B's accuracy at a lower time per call. Short reply, strict, figures to the judge,
hand grades.

| Judge | First test | Second test | Time per call, p50 | Weights |
|---|---|---|---|---|
| Qwen 27B 4-bit | 93.8 % | 90.1 % | 0.54 s | 18 GB |
| Gemma 4 E4B, untrained | 86.4 % | 85.4 % | 0.41 s | 16 GB |
| MiniCPM5-1B, untrained | 48.0 % | 51.0 % | 0.07 s | 2 GB |
| V0 (DeBERTa) | 68.7 % | 58.3 % | 0.09 s | under 1 GB |

Gemma 4 E4B is 5 to 7 points under the 27B and well above DeBERTa. MiniCPM5-1B is below no auditor: it labels
almost every clause not stated. Neither is near the 27B untrained. Raw: `results/fresh_arms/small.json`,
`results/fresh2_arms/small.json`.

## A 1B judge trained on the Qwen 27B's labels (stop 63, 2026-10-12; method in `docs/GRID.md`)

Aim: near the Qwen 27B's accuracy at a much lower time per call. Qwen 27B 4-bit labelled 4,433 training clauses
with the short reply; MiniCPM5-1B was trained on 4,018 of them (LoRA rank 16, one epoch, 30 minutes on an H100).

| Judge | First test | Second test | Time per call, p50 |
|---|---|---|---|
| Qwen 27B 4-bit (the teacher) | 93.8 % | 90.1 % | 0.54 s |
| MiniCPM5-1B, trained | 85.3 % | 80.1 % | 0.06 s |
| MiniCPM5-1B, untrained | 48.0 % | 51.0 % | 0.07 s |
| Gemma 4 E4B, untrained | 86.4 % | 85.4 % | 0.41 s |
| V0 (DeBERTa) | 68.7 % | 58.3 % | 0.09 s |

Training lifts the 1B by 37 and 29 points and it agrees with its teacher on 84 % of held-out clauses. It stays 8.5
and 10 points under the 27B, and 17 to 22 points above DeBERTa, at about a ninth of the 27B's time per call.
Raw: `results/fresh_arms/small.json`, `results/fresh2_arms/small.json`,
`results/distill/students/validation.json`.

## The loop with the short judge reply (stop 65, 2026-10-12; method in `docs/GRID.md`)

Aim: the configuration that stands, run live once. As stop 59 (Qwen 27B AutoRound 4-bit as generator and judge,
one SGLang server, one L40S, 40 questions, two arms), with the judge's short reply of stop 61.

| | Source in the prompt | From memory, source inserted on rollback |
|---|---|---|
| Sentences | 49 | 50 |
| Committed at the first try | 48 | 15 |
| Committed after a retry | 1 | 32 |
| Replaced by the refusal | 0 | 3 |
| Graded wrong | 0 | 3, all refusals |
| Seconds per answer, p50 and p95 | 1.9 and 6.9 (stop 59: 3.2 and 11.8) | 3.1 and 7.2 (stop 59: 5.2 and 13.6) |
| Seconds per judge call, p50 | 0.56 (stop 59: 1.7) | 0.56 (stop 59: 1.7) |
| Judge's share of the time | 35 % (stop 59: 58 %) | 38 % (stop 59: 61 %) |

80 answers, no error. The loop behaves as in stop 59 and takes 59 % of the time per answer. 97 of 99 sentences
repeat stop 59's and keep their grades; the 2 new ones were graded right by both graders. Raw:
`results/fresh2-short-live_arms/live.json`.

## The 1B judge trained on more data (stop 64, 2026-10-12; method in `docs/GRID.md`)

Aim: see how far more training data takes the 1B judge. A second pool of 1,400 sources gave 14,134 more clauses,
labelled by Qwen 27B 4-bit. MiniCPM5-1B was trained from the base on 18,152 clauses for two epochs (30 minutes on
an H100).

| Judge | First test | Second test | Time per call, p50 |
|---|---|---|---|
| Qwen 27B 4-bit (the teacher) | 93.8 % | 90.1 % | 0.54 s |
| MiniCPM5-1B, trained on 18,152 clauses | 89.0 % | 82.1 % | 0.06 s |
| MiniCPM5-1B, trained on 4,018 clauses | 85.3 % | 80.1 % | 0.06 s |
| 1B first, 27B only when the 1B rolls back | 91.0 % (27B on 40 %) | 85.4 % (27B on 46 %) | |
| V0 (DeBERTa) | 68.7 % | 58.3 % | 0.09 s |

4.5 times the data gave 3.7 and 2.0 points. The 1B stays 4.8 and 8.0 points under its teacher, so neither it
alone nor the two-step judge meets the limit of 3 points on both tests. It agrees with the teacher on 86.7 % of
held-out clauses (83.9 % before). Raw: `results/fresh_arms/small.json`, `results/fresh2_arms/small.json`,
`results/distill/students/validation.json`.


## Two hosted decision APIs as the judge (stop 66, 2026-10-13; method in `docs/GRID.md`)

Aim: compare the current judge with two hosted APIs that return a typed answer with probabilities and no text.
Each clause of the short-reply arm was sent once to each, with the same text and the same two questions (label
and deciding passage). The label is the returned choice, no threshold. Same replay, placement and grades.

| Judge | First test | Second test | Seconds per call |
|---|---|---|---|
| Qwen 27B 4-bit | 93.8 % | 90.1 % | 0.54 s (next to its server) |
| Jev 1.13 (OpenRouter) | 90.7 % | 88.1 % | 0.64 to 0.72 s (over the network) |
| OpenAI Decisions (gpt-6-luna) | 89.0 % | 86.8 % | 0.23 to 0.25 s (over the network) |
| MiniCPM5-1B, trained on 18,152 clauses | 89.0 % | 82.1 % | 0.06 s |

Jev is 3.1 and 2.0 points under the 27B, OpenAI 4.8 and 3.3. Neither meets the limit of 3 points on both tests.
The 27B is ahead on the first test (p = 0.013 and 0.005); the second does not show a difference. A threshold
chosen on the first test changes nothing on the second. Cost is $0.07 and $0.13 per 1,000 calls. Raw:
`results/fresh_arms/decisions.json`, `results/fresh2_arms/decisions.json`.

## Retries after a real error, and the KV cache edit (stop 67, 2026-10-14; method in `docs/GRID.md`)

Qwen 2.5 7B retried 95 closed-book sentences that were wrong and that the Qwen 27B judge rolled back, six ways
from the same state. Graded by Opus 5.5 and Gemini 3.8 Flash, open items by hand.

| Retry | Good | Wrong | Same error | Empty |
|---|---|---|---|---|
| Ban the first token (default) | 10 | 71 | 33 | 2 |
| Source as a user turn (current inject) | 19 | 16 | 5 | 0 |
| Passage as plain tokens at the cut | 40 | 25 | 9 | 19 |
| Passage KV spliced at the cut | 26 | 16 | 3 | 25 |
| Same KV far from the cut | 34 | 54 | 24 | 0 |
| Spliced KV, attention times 4 | 15 | 29 | 4 | 17 |

Plain tokens beat the user turn on good retries (33 against 12, Holm p = 0.015). The spliced KV does not beat the
turn (p = 0.60). Nearness cuts wrong retries (42 against 4) and makes the rejected sentence less likely (86 of 95)
but does not add good ones. More attention on the passage makes retries worse. With the source, 11 states only.

## The plain-text passage in the live loop, three generators (stop 68, 2026-10-14; method in `docs/GRID.md`)

Closed-book, 240 questions per generator (120 fresh, 120 new). Answers that hold at least one sentence graded
wrong, and wrong sentences among those graded. The engine's refusal is counted apart.

| Generator | No loop | Loop, source as a turn | Loop, plain-text passage |
|---|---|---|---|
| Qwen 27B | 132 answers, 52.6 % | 23 answers, 7.6 %, refusal 4 % | 25 answers, 11.2 %, refusal 30 % |
| Qwen 2.5 7B | 198 answers, 73.4 % | 28 answers, 5.9 %, refusal 7 % | 32 answers, 11.7 %, refusal 19 % |
| MiniCPM5-1B | 92 answers, 28.5 % | 53 answers, 10.1 %, refusal 16 % | 21 answers, 9.1 %, refusal 48 % |

The turn loop cuts wrong answers for every generator (p < 0.001 against no loop). The plain-text passage is
better for none: not told apart for the two Qwen models, and for the 1B fewer wrong answers bought with 48 %
refusals.

## The judge re-asked, and a second judge, on the loop's committed sentences (stop 69, 2026-10-15; method in `docs/GRID.md`)

On 1,630 sentences the turn loop committed in stop 68 (136 graded wrong), asking the 27B judge again with two
more seeds and keeping a sentence only if every sample says supported drops 26 wrong and 32 right sentences. Opus
5.5 as a second judge drops 50 wrong and 15 right on the 1,113 sentences it labelled, but Opus 5.5 also graded most
of them; on the sentences you graded it drops 4 wrong and 7 right. Neither check is shown to help.

## The live loop with the source in the prompt (stop 70, 2026-10-15; method in `docs/GRID.md`)

240 questions per generator, source in the prompt. Answers holding at least one sentence graded wrong.

| Generator | No loop | Loop, ban retry | Loop, source as a turn |
|---|---|---|---|
| Qwen 2.5 7B | 25, 9.3 % of sentences | 16, 4.9 %, refusal 5 % | 13, 3.7 %, refusal 4 % |
| MiniCPM5-1B | 116, 41.3 % | 49, 15.9 %, refusal 28 % | 46, 12.2 %, refusal 16 % |

The turn loop is better than no loop for the 7B (Holm p = 0.045) with fewer refusals than 5 % and more right
statements. For the 1B the loops remove most wrong answers but refuse too often to pass the fixed reading.
Stop 68's 1B figures were corrected the same day after a judge fault: plain 37 and turn 53 answers with a wrong
sentence, not told apart.

## The 7B loop against two frontier models (stop 71, 2026-10-16; method in `docs/GRID.md`)

240 questions, source in the prompt. Answers holding at least one sentence graded wrong. Frontier models through
the router, temperature 0; a checked arm drops the sentences the other model's verifier rolls back.

| Arm | Wrong answers | Wrong sentences | Empty answers | Seconds, p50 |
|---|---|---|---|---|
| Qwen 2.5 7B, turn loop, 27B judge (stop 70) | 13 | 3.7 % | 0, refusal 3.8 % | 1.7 |
| Gemini 3.8 Flash | 3 | 0.7 % | 1 | 4.4 |
| Claude Opus 4.6 | 8 | 1.9 % | 0 | 3.1 |
| Flash, Opus 4.6 checking | 1 | 0.2 % | 6 | 8.7 |
| Opus 4.6, Flash checking | 2 | 0.5 % | 14 | 9.0 |

The loop is not near any frontier arm by the fixed margin (upper end of the paired interval at most 4 points):
the upper ends are 5.4 to 7.9 points. Against Opus 4.6 the difference is 2.1 points (-0.8 to 5.4). The loop is
the fastest arm. Opus 5.5 graded; it was softer on Opus 4.6's sentences, and those it left unsure were graded by
hand.
