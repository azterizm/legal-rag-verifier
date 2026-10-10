# 2x2 grid: method, fixed before the run (vault 07 §5)

Written 2026-10-06, before any grid generation. Changes after the run are listed at the end, with reasons.

## Cells

| | Post-hoc full retry | Sentence-level remediation |
|---|---|---|
| **Gemini** `gemini-3.8-flash-high` (router `localhost:8317`, temperature 0) | **4A** | **4C** continuation |
| **Qwen 2.5 7B-Instruct** `@a09a3545`, bf16, SGLang 0.5.21, one NVIDIA L4 (Modal), greedy | **4D** | **4B** in-flight rollback |

- **Same input everywhere**: `engine.SYSTEM_PROMPT` with the premise rendered by `render_premise`, then the
  query as the user turn. Qwen answers are capped at 512 new tokens; Gemini is sent no token cap (the router
  call carries model, messages and temperature only).
- **Same detector everywhere**: `Verifier` defaults (claim check + `nli-deberta-v3-base`), premise enrichment
  attached (`gemini-3.8-flash-high@edb8ccbb`). It runs on the L4 for 4B/4D and on the Apple M4 (MPS) for 4A/4C,
  so verification time is reported apart from generation time.
- **Same retry budget everywhere: at most 3 retries** (your rule, 2026-10-06).
  - 4A / 4D: the whole answer is checked post-hoc; on any rolled-back sentence the conversation continues with
    *"Previous response hallucinated X or missed qualification Y. Regenerate."* (X = the rejected claims, or
    the rejected sentence when the NLI head rejected it; Y = dropped qualifiers). Still failing after the third
    retry → released as **unresolved**. Greedy decoding means "regenerated from scratch" with no message would
    repeat itself, so 4D uses the same message as 4A: 4A vs 4D isolates the generator.
  - 4B: `InFlightGenerator` defaults (allow-list steering, then ban; 3 retries per point; refusal after that).
  - 4C: sentences are checked in order; the verified prefix is kept and the model is asked to continue after it,
    with the rejected sentence named. The prefix is given as the model's own previous (assistant) turn plus a
    user turn *"Continue your answer from exactly where it stops…"*; assistant prefill proper is not relied on
    (the router's support for it is not documented). 3 retries per point, then the refusal sentence.
  - Disclosure: 4B steers decoding (allow-list / ban); a closed API exposes no logits, so 4A/4C/4D steer only
    through text. That difference is part of what the grid measures.
- The SGLang prefix cache is flushed before every answer.

## Prompts

`batteries/grid/test.jsonl`: the router concept battery's `test` split, UK only — **103 prompts** (vault 07
says 500; this set is what exists, and the detector was never tuned on it). 91 answerable, 11 abstention
probes (fictional instruments or provisions; 1 with an empty premise), 1 bounded. Premise = the gold
provisions from the copied corpus. 9 gold provisions lacked enrichment and get it first (same pipeline).

## Scoring (rule A, `scripts/grid_score.py`)

Per final answer, with the claim check only (no NLI), against the prompt's own premise:
- **Answerable prompt — PASS** iff (1) it cites a gold provision (that section or a part of it: the exact
  section number), (2) no figure, date, citation or Act name in it is ungrounded, and (3) it contains no
  refusal sentence.
- **Abstention prompt — PASS** iff it abstains (says the provisions do not answer, or is the refusal sentence)
  and (2) holds.
- Not independent: (2) is the detector's own claim check, which 4B and 4C enforce by construction. (1) and (3)
  are independent of it. **Blind hand sample**: 20 final answers per cell (80, seed 20261006), shuffled, cell
  hidden; you label each correct / incorrect against the provisions; agreement of rule A with your labels is
  reported per cell.

## Independent judge (added 2026-10-06, before scoring; your decision)

Rule A's grounding test is the detector's own claim check, so the in-flight cells pass it by construction. A
separate model therefore judges every final answer: **`gpt-oss-120b-medium` via the router** (`/v1/chat/completions`; no other model or endpoint is called).
- **Order**: rule A on all answers → your blind labels on the 80-answer sample → the judge on all 412 answers.
- **Blind**: the judge sees the query, the provisions (statute text only, without the LLM-written enrichment
  layer) and one answer, in random order across cells; never the
  cell, the generator, the detector's verdicts or the other answers. Temperature 0, one fixed prompt.
- **Output** (JSON): an answer-level verdict (correct / incorrect; for abstention prompts, whether abstaining
  was right) and per-sentence labels (supported / unsupported / contradicted / not a claim) with an error type
  (wrong figure, wrong citation, wrong instrument, dropped qualifier, fabricated, incomplete).
- **Validity**: judge vs your 80 labels (agreement and Cohen's κ, per cell) is reported before any judge-based
  cell result is quoted. If agreement is poor, the judge's results are reported as such and not as the headline.
- **Headline correctness per cell = the judge's answer-level verdict**, beside rule A and your sample.
- **Refinement**: the judge's sentence labels against the detector's verdicts give the detector's misses and
  false rollbacks on real generated prose. These are hypotheses only: any detector change is made and
  calibrated on the dev split, never tuned on the grid prompts (which would contaminate the grid).

## Reported per cell

Rule-A pass rate; first-pass clean / resolved after remediation / unresolved (4A/4D: still failing after 3
retries; 4B/4C: at least one refusal); retries histogram; refusals; tokens generated and discarded; wall-clock,
time to first released output (4A/4D: the whole checked answer; 4B/4C: the first verified sentence),
generation time, verification time, decode tokens/s (Gemini: completion tokens over call latency, which
includes time to first token and any thinking); calls per answer. Raw: `results/grid/<cell>.jsonl`;
summary: `results/grid/summary.json`.

Not measured: time to first token (no streaming); token cost in money (router billing is not visible here; the
L4 is priced from Modal's hourly rate and the measured wall time).

## Changes after the run

- 2026-10-07: Gemini's raw `completion_tokens` include thinking; visible tokens (completion − reasoning, from
  each call's `usage`) are reported beside them. No change to the cells, prompts or scoring.
- 2026-10-07: the judge's agreement with the blind labels is κ 0.375, so by the rule above it is **not** the
  headline; rule A, the labels and the judge are reported side by side (`docs/measurements.md`).

## Stop 27: the injection A/B (method fixed 2026-10-07, before the test run)

**Question.** When the auditor rolls back a sentence, does writing the provision it was checked against into
the KV cache, then regenerating, make a cheap model recover more often than decode-level steering does? This is
the half of the architecture goal the grid did not test (plan decision 6 had nothing written into the context).

- **Arms.** A = 4B as run (allow-list, then ban). B = `4B-inject`: the same engine with `steering="inject"`. On a
  rollback the windows the verifier aligned the rejected sentence to (at most 2, each once per answer, cut at 800
  tokens) are written into the context at the rollback point, and the sentence is regenerated from its start with
  no constraint. The prefix up to the rollback point is reused from the cache; only the source is prefilled. The
  source never enters the answer text; the trace records the windows and token count. With no new window to
  inject, the retry is a ban, as in A. Everything else is the same: Modal L4, Qwen 2.5 7B `@a09a3545` bf16,
  SGLang 0.5.21, the 103 test prompts, the auditor (claim check + DeBERTa-v3-base, enrichment attached), 3 retries
  per point, 8 per answer, cache flushed before every answer.
- **Format, chosen on the dev split.** Two ways to write the source: `note` (plain text in the answer stream:
  `(Source: …)`) and `turn` (a user turn in Qwen's chat format with the source and the 4C continue line, then a
  new assistant turn). Both run on the first 40 dev prompts; the one with more recovered points (tie: fewer
  refusals) is used on test. The test prompts are not used for this choice.
- **Parity.** 4B is re-run on the first 10 test prompts in a fresh container; its answers are compared with the
  stored 4B answers, so A and B are known to come from the same environment.
- **Primary measure.** Per rollback point, grouped by what rejected the first draft (claim check or NLI alone):
  first-retry pass rate, points recovered, points refused. Baseline from A: claim check 11/40 first retries
  passed (28 %), 21 recovered, 27 refused; NLI 11/27 (41 %), 20 recovered, 10 refused.
- **Holds if** B's claim-check first-retry pass rate is clearly above 28 % and its refusals are fewer than A's.
  Points differ between arms (generation diverges after the first rollback), so these are rates, and 40-odd
  points per group is a small sample: a difference of a few points is reported as no difference.
- **Secondary.** Rule A, the judge's verdict on every B answer (same blind protocol), time to first output, wall
  time, tokens injected, and the prefix-cache hit on every injected retry.
- Script: `scripts/grid_inject.py`; raw: `results/grid/4B-inject.jsonl`, `results/grid/dev/`.
- **Pilot result (dev, 40 prompts) and the format chosen: `turn`.** `note`: 21 rollback points, 17 recovered,
  4 refused; `turn`: 15, 13, 2. Every injected retry hit the prefix cache in both (23/23, 18/18). By the
  rule as written (more recovered points) `note` would win, but 5 of its 17 recoveries are the source's own
  heading copied back as an answer "sentence" (`[Employment Rights Act 1996, section 23(2) (…)]`, 6 such
  sentences in all): the plain-text format leaks the source into the answer, which the mode must never do.
  Without them `note` recovers 12/21, `turn` 13/15. The rule should have been a rate over genuine sentences;
  `turn` is used on test. Decided on dev data only, before any test answer existed.
- 2026-10-07 (after the A/B run): the judge re-judged 56 answers that are identical in 4B and 4B-inject and gave
  the same verdict on 49 (temperature 0 is not deterministic on the router). This is reported with the A/B as judge
  noise. The A/B's success rule was met on the primary measure, but the judge shows a loss in answer relevance.
  Both are reported (`docs/measurements.md` § Injection A/B).

## Stop 29: where the provision goes, and what it does to attention (method fixed 2026-10-07, before any run)

**Questions.** (1) Does inserting the provision at the cut point help because of its position, its content, or
the cache? (2) Does the inserted provision draw more of the model's attention, and does it make the rejected
sentence less likely and the regenerated one more likely? The stop 27 A/B left both open: the provisions were
already in the system prompt, and attention was not read.

**States.** A (4B) and B (4B-inject) run the same engine until the first rollback, so in every answer with a
rollback both reach the first rollback point with the same committed text and the same rejected draft (48 answers,
none diverged; `scripts/replay_states.py`). Already measured on these states, from the stop 27 traces: first retry
passed 19/48 in A and 39/48 in B (both 18, only A 1, only B 21; exact McNemar p = 1.1e-5). B inserted a provision on
47 of the 48; the new arms use those 47. The states are rebuilt from the traces with the generator's tokenizer and
checked against them: prompt length 48/48, committed text round trip 48/48, inserted source length 47/47, and the
prefix-cache hit of B's retry equals prompt + committed answer on all 46 retries checkable that way.

**Arms** (same container, model, auditor and decoding as stop 27; one first retry per state, then 2 follow-on
sentences decoded with no rollback and each audited):

| Arm | From the shared state | Isolates |
|---|---|---|
| R0 | A's recorded retry replayed (its allow-list or ban, as recorded) | the stop 27 control |
| R1 | B's retry: provision inserted at the cut point as a user turn, cache warm | the mechanism |
| R2 | R1's exact tokens, cache flushed first | the cache: same output expected, time differs |
| R3 | the same provision text placed at the top, after the query in the user turn; the committed answer re-prefilled after it | position |
| R4 | R1's turn with no provision (the turn break and the continue line only) | content |

- **Parity first.** For each state the first draft is decoded again and compared with the recorded rejected draft;
  a state that differs is dropped and counted. R0 and R1 are compared with the recorded retries.
- **Primary measure.** First-retry pass by the auditor, paired per state, exact McNemar: R1 against R3 (position),
  R1 against R4 (content). R2 against R1: identical text on every state, and the time of the first decode call.
- **Secondary.** First-draft pass of the 2 follow-on sentences per arm (rates; small sample).

**Attention and likelihood** (Hugging Face transformers, eager attention, bf16, same revision, on the L4; the
recorded tokens are fed in, nothing is generated). Per state, with S = R1's regenerated sentence, X = the rejected
draft, N = the follow-on sentence after S:

| Measure | Compared |
|---|---|
| Share of attention from S's tokens to provision text: the original windows in the system prompt, the inserted copy, and the other windows | S after the inserted turn against S with no inserted turn; S with the provision at the top (R3) |
| log P(S) | with against without the inserted turn |
| log P(X) | with against without the inserted turn |
| The same attention share for N | with against without the inserted turn |

- Attention share = attention weight to the span over all attention except to the first token (which takes
  attention whatever it holds), averaged over heads and over the sentence's tokens; reported for all layers (primary)
  and for layers 0–8, 9–18 and 19–27.
- Tests: two-sided exact sign test over states. The five primary comparisons (R1–R3, R1–R4, attention share on
  provision text, log P(S), log P(X)) are Holm-corrected at 0.05.
- **Replay fidelity.** How often the model's top token at each fed position equals the recorded token is reported;
  below 95 % the attention results carry that caveat.
- Attention weights describe where the model looked, not why it wrote what it wrote. The likelihood measures carry
  the causal claim; attention is supporting evidence.

**Reading the outcomes.** R1 > R3: inserting at the cut point beats the same text at the top. R1 ≈ R3: repeating
the provision is what helps, and insertion at the cut point is the way to do it that reuses the cache. R1 > R4: the
provision's content does the work, not the turn break. R2 = R1 in text: the cache is a cost saving, not a quality
change. Higher share on provision text, higher log P(S) and lower log P(X) with the inserted turn: "more attention,
and the unsupported sentence becomes less likely" is measured. Attention up but likelihoods unchanged: attention is
not offered as the explanation. With 47 states only large effects show; a difference of a few states is reported
as none. Nothing here changes the engine or the auditor, and no choice is made on these test states.

- Scripts: `scripts/replay_states.py` (states, local checks), the replay and attention runs (to be written);
  raw: `results/grid/replay_states.json`, later `results/grid/replay/`.
- 2026-10-07 (stop 29, after the run): the harness first left out the 2 states where A's retry decoded nothing
  (a filter on A's recorded retry); they were run separately, with R0 recorded as that refusal, so all 47 states
  are covered as specified. Parity held on 46/47. Replay fidelity was 92 to 94 %, below the 95 % bar, so the
  attention results carry that caveat (`docs/measurements.md`). The raw SGLang output (`replay/sglang.jsonl`) holds
  the prompt token ids, which encode statute text from `data/`; it is git-ignored and `replay/arms.jsonl` is kept
  without them. A report bug that merged two span medians under one name was fixed before the write-up.

## Stop 30: injection v2 (method fixed 2026-10-07, before any run)

**Question.** Stop 27 showed the inserted provision makes the retry faithful to the provision but not to the
question (judge 63/103 correct against 75 for 4B; off-topic answers 13 → 24; abstention 8/11 → 4/11). Do two
changes, neither of which adds a rejection reason to the auditor, recover the question while keeping the gain?

- **Change 1, the inserted turn.** Positive wording only, with the question restated and no reference to the
  rejected sentence: user turn `The provision relevant to the question "{query}":\n{source}\n\nContinue your
  answer to the question from exactly where it stops.`, then a new assistant turn. (v1: `The provision for your
  next point:\n{source}\n\nContinue your answer from exactly where it stops, without repeating any of it.`) The
  engine's `inject_template` gains an optional `{query}` placeholder for this.
- **Change 2, the abstention gate.** The released `legal-rag-router` 0.1.0 runs on every query before generation
  (`scripts/grid_routes.py`, its own index, snapshot 2026-09-28). A query it refuses (`next_action = REFUSE`) is
  answered with the router's message and never reaches generation; every other status goes to generation with the
  prompt's premise as before. Its statuses were recorded before this run: test 11/103 refused (exactly the 11
  abstention probes), dev 0/112; all 215 equal the battery's expected labels. The gate is deterministic, so on
  these prompts it decides abstention by construction; the result is reported with and without the 11 probes.
- Everything else is 4B-inject as run: L4, Qwen 2.5 7B bf16, SGLang 0.5.21, the auditor, 3 retries per point,
  8 per answer, at most 2 windows per injection cut at 800 tokens, cache flushed per answer. Cell `4B-inject-v2`.

**Dev pilot first** (the first 40 dev prompts, as in stop 27). Run v2 and judge v1 (`dev/4B-inject-turn`) and
v2 with the same judge and prompt (80 calls). The test run goes ahead only if on dev v2 has at least as many
answers judged to address the question and judged correct as v1, and its first retry passes at least 70 % of
rollback points. 40 prompts is a sanity check, not a test of significance. If it fails, stop 30 ends there and
is reported; the wording is not tuned further.

**Test** (103 prompts, then the judge on the 103 v2 answers, same blind protocol). Reported against 4B, 4B-inject
and 4D: judge correct (all, answerable, abstention), answers judged not to address the question, answers with an
unsupported sentence, first-retry pass and refusals per rollback point, answers ending right after an inserted
retry, time to first output and wall time. **Reading, set before the run:** if v2 is judged correct on at least
75 of 103 (72 %) and abstains correctly on at least 8 of 11, the verdict becomes "the full loop holds end to end";
otherwise the verdict stands as written and injection work stops for 0.1.0. Judge noise (49/56 repeat agreement)
means a gap under about 10 answers is not a difference.

**Changes after the run.** None to the method. The router returned 503 on the last 8 test answers; they were judged
on 2026-10-08 with the same judge and prompt. The judge rejects every router refusal as an unsupported claim, so
the abstention part of the reading cannot be met under this protocol. The protocol was not amended after the run;
the reading is reported as written (`docs/measurements.md` § Injection v2).

## Stop 36: human check of rollbacks and retries (method fixed 2026-10-08, before any label or test judge call)

**Question.** The auditor both rejects a sentence and accepts its retry, so "the retry passed the auditor" does
not show the retry is right. Are the rejected sentences real errors, and are the retries with the provision
inserted correct and on the question more often than the other retries from the same state? No change to the
engine, the auditor or any earlier result follows from this stop; it only measures.

**Core set (labelled by you, all of it).** The 46 parity states of stop 29 (`results/grid/replay/arms.jsonl`).
Per state: the rejected draft X and the first retries R0 (decode steering, as recorded), R1 (provision inserted at
the cut), R3 (provision at the top) and R4 (turn without the provision); 230 sentences, 217 after removing exact
duplicates within a state. R2 is left out: it tests the cache, not quality (same pass or fail as R1 on all 46,
same tokens on 44). Empty or refused retries (3 in R3, 2 in R0) are not labelled and count as failed retries.
The answer so far is the committed text of the state (`scripts/replay_states.py`).

**Labels**, identical for you and the judges, per sentence read after the answer so far:
- `grounding`: `supported` (every claim, with its figures, citations, Act names, conditions and qualifiers, is
  stated in or follows directly from the provisions), `unsupported` (a claim the provisions do not make, including
  a rule stated without a condition the provisions attach to it), `contradicted` (the provisions say otherwise) or
  `no_claim` (no legal claim: a heading, a connective, a refusal). A sentence cut off part way is labelled on the
  claims it does make.
- `on_question`: yes if the sentence helps answer the question asked; no for true law the question did not ask
  about.
- `reads_on`: yes if it is a complete sentence that continues the answer so far without repeating it; no for a
  fragment, a repeat or a copied heading.
- Derived: a rejected draft is a **real error** if `unsupported` or `contradicted`. A retry is **good** if
  `supported`, `on_question` and `reads_on`.

**Blinding.** One sheet, grouped by state so each provision is read once; states in a seeded random order
(seed 20261008); each state's sentences shuffled and lettered. The sheet shows the question, the provisions
(statute text, without enrichment), the answer so far and the sentences; never the arm, which sentence was
rejected, or any auditor verdict. The key is a separate git-ignored file; its SHA-256 is recorded here before
labelling starts. You label without AI help on the decisions. A sentence copied from the statute can give away
its arm; each sentence is labelled on its own, not against the others.

**Order.** (1) This method, committed. (2) The judge prompt is tried on dev rollback points only (format and
plain misreads), then frozen; its SHA-256 is recorded here. (3) The sheet is built; the key hash is recorded.
(4) Your labels are committed. (5) Only then do the judges see any test item. (6) The report.

**Readings, set now.**
- **P1, the auditor's precision on live output:** share of the 46 X that are real errors, with a Wilson 95 %
  interval. The rollbacks read as mostly right if the share is at least 80 % (the sealed battery gave 89 %).
- **P2, inserting the provision gives better retries:** good-retry rate, R1 against R0, paired per state, exact
  McNemar. Holds if R1 > R0 with p < 0.05. Secondary, Holm-corrected: R1 against R3 (position) and R1 against R4
  (content).
- **P3, faithful but off the question:** per arm, the share of retries that are `supported` but not `on_question`;
  R1 against R0 reported with no threshold.
- **Auditor misses on retries:** per arm, retries the auditor accepted that are not good.
- 46 states show only large effects; a gap of a few states is reported as none.

**Judges and the extended set.** `gpt-oss-120b-medium` and `gemini-3.8-flash-high` via the router, no other model
or endpoint. One sentence-level prompt, temperature 0, at most 3 asks for valid JSON. Each judge sees the question,
the provisions (statute text only), the answer so far and one sentence; never the arm, the cell or a verdict. All
sentences are Qwen output, so neither judge grades its own text. Each judge labels the 217 core sentences; per
judge, Cohen's kappa against your labels on real error (X) and on good retry (retries) is reported first.
- **Extended set:** every rejected draft and every released sentence in the test traces of 4B, 4B-inject and
  4B-inject-v2, exact duplicates (same question, answer so far and sentence) labelled once. It gives P1 on every
  rollback and a first figure for auditor misses on released sentences.
- A judge's extended results are used only if its kappa is at least 0.6 on both. Otherwise they are reported as
  indicative. No judge output changes a rule, prompt, threshold or detector setting (plan R1).

- Script: `scripts/rollback_review.py` (`build`, `pilot`, `judge`, `report`); outputs under
  `results/grid/rollback/`. Router calls on test, and every Gemini call, need your go.

**Before labelling (2026-10-08).**
- Core count at build: 230 sentences, 225 with text, **212 to label** after exact duplicates within a state are
  merged (the 217 above counted the 5 empty retries). In 10 items a retry repeated another sentence of its state,
  in 8 of them the rejected draft; one label covers each.
- Extended set at build: 588 items (223 rejected drafts, 365 released sentences).
- Dev pilot of the judge prompt: 12 dev rollback items (first rejected draft and first retry, seeded sample of
  `dev/4B-inject-turn` and `dev/4B-inject-v2`), both judges. Every reply parsed on the first ask. The judges agreed
  on `grounding` for 6 of 12; gpt-oss was the more lenient and passed a sentence that repeated the one before it.
  One rule was ambiguous ("a fragment" under both `no_claim` and `reads_on`) and split the judges on a sentence cut
  off part way; it now reads: a sentence cut off part way is labelled on the claims it does make. The pilot was
  re-run once with that text. No other change. On the re-run every reply again parsed on the first ask, the judges
  agreed on `grounding` for 9 of 12, `on_question` 11 and `reads_on` 11, and both labelled the cut-off sentence the
  same way. The change touched one item, so most of the rise from 6 to 9 is run-to-run variation at temperature 0.
  gpt-oss again passed the repeated sentence as reading on. Raw: `results/grid/rollback/pilot*.jsonl` (the first
  run's files end in `.prompt-71e5e694.jsonl`).
- Frozen judge prompt SHA-256 (`PROMPT_SHA` in `scripts/rollback_review.py`):
  `1f7dad48752a21cd3ac41c5730ee8fdf16196576219c583bd489ffae61cecb0f`.
- Key SHA-256 (`results/grid/rollback/key.json`, git-ignored, rebuilt identically by `build`):
  `235b96bdcaeee15cb74d72789695ca988c16e9d2eccd4474c6795272657c6bca`.

**Change before labelling (2026-10-08, your decision).** You did not label the core sheet: the statute text is
outside your domain. You gave the blind sheet to an external frontier AI system to label in your place. Its name,
version and settings are recorded when its labels arrive, and its labels are appended as received; the rest of
this method stands. So the core labels are model labels, not human labels. P1 to P3 are read on them as written,
and the kappa rule for gpt-oss and Gemini measures agreement with that system, not with a person. Human labels
move to a software battery in your domain (stop 37), which also measures how far model labels can stand in for
yours.

**Labels received (2026-10-08).** Labeller: Claude Opus 5.5 at effort xhigh, run by you outside this repository.
It was given `sheet.md` only, not the key (your confirmation). 212 of 212 items labelled, every value valid.
Committed as `results/grid/rollback/labels.csv` before any judge saw a test item and before the key was read
against them.

**After labelling (2026-10-08).** `report` read the labels against the key once. P1 fails (18 of 46 real errors);
P2 fails (good retries R1 11, R0 17); R3 and R4 beat R1 (Holm p = 0.003). A grounding-only comparison was added
to the report after the readings and is marked as not set in advance. No rule, prompt or threshold changed. The
judges have not run on test; their run (router; Gemini is paid) waits for your go
(`docs/measurements.md` § Rollbacks and retries labelled).

## Stop 37: the loop on software questions, graded by you (method fixed 2026-10-08, before the run)

**Question.** In a domain you know, and graded by you: (1) are the sentences the auditor rejects real errors,
(2) is a retry with the documentation inserted better than a retry with decode steering, and (3) are the loop's
final answers better than a plain answer from the same model?

**Battery.** `batteries/software/test.jsonl`: 40 questions, 8 per area, premises quoted verbatim from public
documentation (`batteries/software/README.md`). Every question has its answer in the premise. Nothing is tuned on
it, and it does not change after this commit.

**Setup.** As stop 30 except the domain wording. L4, Qwen 2.5 7B Instruct bf16, SGLang 0.5.21, the same auditor
(claim check + `nli-deberta-v3-base`; no enrichment layer, which exists only for statutes), 3 retries per point,
8 per answer, cache flushed per answer. The prompts keep their structure, with legislation wording replaced:
- system: `You answer questions about software using only the documentation below. State figures, defaults,
  version numbers and names exactly as the documentation gives them. If the documentation does not answer the
  question, say so. Answer in a few plain sentences, without headings or lists.\n\nDocumentation:\n{premise}`;
- refusal: `I cannot state this point reliably from the documentation provided.`;
- inserted turn (v2): `The documentation relevant to the question "{query}":\n{source}\n\nContinue your answer to
  the question from exactly where it stops.`
- Cells: `4B` (decode steering), `4B-inject-v2` (documentation inserted at the cut, question restated) and `4D`
  (full retry). The **plain answer** is 4D's first draft, written before any check. 4B and 4B-inject-v2 decode
  the same tokens until their first rollback, so each answer with a rollback gives one shared state: the same
  answer so far and the same rejected draft, retried both ways. No router gate (every question is answerable).

**Your grading sheet** (blind; seed 20261008; key git-ignored, its SHA-256 recorded here before you grade):
- Part A, per shared state: the rejected draft and the two first retries, shuffled and lettered, under the question,
  the documentation and the answer so far. Three columns: `correct` (yes if every claim matches the documentation
  shown), `answers` (yes if it helps answer the question asked), `reads_well` (yes if it is a complete sentence that
  continues the answer; no for pasted labels, fragments or repeats).
- Part B, per question: the plain answer, 4B's final answer and 4B-inject-v2's final answer, shuffled and
  lettered. Two columns: `correct`, `answers`.
- You grade without AI help on the decisions. Your grades are committed before the key is read against them.

**Readings, set now.**
- **S1, rejections are real:** share of rejected drafts graded not `correct`, with a Wilson 95 % interval. Holds if
  at least 80 %.
- **S2, insertion gives better retries:** good retry = `correct`, `answers` and `reads_well`. 4B-inject-v2 against
  4B, paired per state, exact McNemar. Holds if v2 > 4B with p < 0.05.
- **S3, the loop gives better answers:** good answer = `correct` and `answers`. 4B against plain and 4B-inject-v2
  against plain, paired per question, exact McNemar, Holm-corrected. Each holds if the loop cell > plain at
  adjusted p < 0.05.
- Also reported: per cell, answers the auditor released with a sentence you graded wrong is not measurable from
  Part B alone, so Part B reports good answers only; Part A reports retries the auditor accepted that are not good.
- 40 questions show only large effects. If fewer than 10 shared states arise, S1 and S2 are reported as counts,
  not read.

**Model labels against yours.** After your grades are committed, you may give the same sheet (never the key) to
the external system used in stop 36 (Claude Opus 5.5, effort xhigh). Its agreement with you (Cohen's kappa per
column) is reported, as evidence for how far its stop 36 labels stand in for a person's.

- Run: `scripts/modal_m4.py::grid --split software` (Modal L4, paid; your go 2026-10-08). Outputs:
  `results/software/`. Sheet and report: `scripts/software_review.py`.

**Run and sheet (2026-10-08).** The run finished on one L4: 40 answers per cell, no errors. 4B rolled back in 12
answers (21 points); 4B-inject-v2 in the same 12 (23 points); every inserted retry hit the prefix cache (14 of 14).
All 12 answers with a rollback give a shared state, so S1 and S2 are read (at least 10). Sheet: 12 states,
34 texts in Part A; 40 questions, 69 texts in Part B (identical answers shown once: with no rollback, 4B and
4B-inject-v2 write the same answer, and the plain answer equals 4B's on 23 of 40). Key SHA-256
(`results/software/review/key.json`, git-ignored): `ce97382831ea59ff665f34be82f6e442e531e18b1212e7491741c3a0825aa463`.

**Grades received (2026-10-08).** Graded by you, without AI help on the decisions. 103 of 103 texts, every value
valid. Committed as `results/software/review/grades.csv` before the key was read against them. You did not give
the sheet to the external system, so no model-against-person agreement is reported for this stop.

**After grading (2026-10-08).** `report` read the grades against the key once. S1 fails (1 of 12 rejected drafts
wrong); S2 fails (good retries v2 7, 4B 8); S3 fails for both cells (good answers 4B 29, v2 30, plain 32). The
per-question breakdown of where the loop helped or hurt was added after the readings. No rule, prompt or threshold
changed (`docs/measurements.md` § Software battery, graded by you).

## Stop 40: the question in the entailment check, offline (method fixed 2026-10-08, before any scoring)

**Question.** The entailment model sees one sentence and one chunk of the source, never the question. Does giving
it the question cut the false rollbacks without letting real errors through? No generation and no paid call: the
auditor is re-run on sentences already labelled.

**Variants.** Only the entailment model's input changes; the claim check, thresholds and engine are unchanged. The
model is wrapped, not edited.
- V0: as run (the sentence alone against each chunk). Its verdicts are compared with the recorded ones first.
- V1: `Question: {query}\nAnswer: {sentence}` as the hypothesis.
- V2: `Question: {query}\nAnswer: {previous sentence} {sentence}` (the last sentence of the answer so far, if any).
- V3: `Question: {query}\n` in front of every source chunk (the question in the premise, not the hypothesis).

**Sets** (both now become development data: a variant chosen here needs a fresh blind test).
- Software: the 34 Part A texts of stop 37 (rejected drafts and first retries), your grades. Wrong = `correct` no.
- Statutes: the 212 core texts of stop 36, Claude Opus 5.5's labels, premise as run (with enrichment). Wrong =
  `unsupported` or `contradicted`; right = `supported`; `no_claim` reported apart.
- Each text is checked with the question and the answer so far of its state, as the engine checks it (CPU here;
  the runs used a GPU, so a few borderline scores may differ from the recorded verdicts).

**Measures, per set and variant.** Rollbacks of right texts (false rollbacks) and of wrong texts (caught), and
which check fired. **Reading, set now:** a variant is worth a fresh test if, on both sets, it at least halves V0's
false rollbacks and still catches at least 90 % of what V0 catches. Small sets show only large effects.

### Stop 40: results (2026-10-08)

Raw: `results/nli_context/` (`scripts/nli_context.py`). V0 gave the recorded verdict on every text (34 of 34
software, 212 of 212 statutes), so CPU scoring did not move any borderline case.

| Set | Variant | False rollbacks | Caught | False rollbacks, entailment only | Caught, entailment only |
|---|---|---|---|---|---|
| Software (28 right, 6 wrong) | V0 | 19 | 4 | 18 | 2 |
| | V1 | 18 | 6 | 17 | 4 |
| | V2 | 14 | 5 | 13 | 3 |
| | V3 | 17 | 3 | 16 | 1 |
| Statutes (116 right, 73 wrong) | V0 | 56 | 51 | 28 | 22 |
| | V1 | 51 | 47 | 21 | 20 |
| | V2 | 48 | 43 | 18 | 16 |
| | V3 | 39 | 41 | 12 | 14 |

**Reading.** No variant is worth a fresh test. None halves the false rollbacks on either set. V3 comes closest on
statutes (56 to 39) but catches 41 of V0's 51 (80 %, under the 90 % bar), and on software it catches fewer errors.

**What moved.** Each variant passes some right texts and some wrong ones in about the same ratio. The entailment
model became more lenient overall; it did not separate right from wrong any better. With V3, 10 wrong statute texts
now pass. In several, words from the question count as evidence (uk-concept-0046: the question says "bruising", the
answer adds "such as bruising" to the statute text). The claim check accounts for about half the false rollbacks on
statutes, and no change to the entailment input touches those.

## Stop 41: derived facts for the entailment check (method fixed 2026-10-09, before any scoring)

The entailment model rejects correct sentences it would need one step of reasoning to accept. In A01
the source says the divisor is N - ddof and that ddof is zero by default. The answer says the divisor
is N, and the model calls it a contradiction. Stop 40 showed that adding the question does not fix this.

This stop tests whether facts written in advance fix it. At ingestion a strong model reads each source
once and writes the facts that follow from it: defaults applied, definitions substituted, references
between passages joined, unit equivalences stated, arithmetic done. The entailment model then only has
to match a written fact. The approach is the teacher precompute of blind-counsel and blind-adapters.
This repo has its own code for it, with no dependency on either.

This is a viability check on the software battery of 40. The full run (statutes, then live) follows
only if it passes.

### Facts

`gemini-3.8-flash-high` through the router, one call per source, temperature 0, at most 3 asks for
valid JSON (`scripts/normalise_sources.py`). A source is the documentation passages of one battery
row. Only documentation text is sent. No question, answer or label is sent, and the scoring script
fails if any question or graded text appears in a stored prompt. Replies are cached by the source's
sha256. Each fact names its passage, gives verbatim quotes and an optional calculation.

Code drops a fact when:
1. a quote is not verbatim in the source or is under 8 characters (after `enrichment.normalise`);
2. a figure, date or citation in the fact is neither in its quotes nor the result of its calculation;
3. the calculation uses a number not in its quotes or anything other than + - * / and brackets.

This proves the anchoring and the arithmetic. It does not prove reasoning in words. A wrong fact of
that kind shows up as a wrong text getting through, which R2 lists.

The prompt is piloted on 3 statute dev provisions, not scored, then frozen. Its sha256 is recorded
here before the battery run.

### Arms

The entailment model, thresholds and engine are unchanged (`scripts/nli_normalised.py`).
- V0: today's auditor.
- S: each fact added to its passage as an enrichment element, so it is one more entailment candidate.
  It cannot override the claim check.
- S-claims, a diagnostic: as S, and each fact is also a FACT passage, so the claim check sees it.

### Texts and grades

No new labels. Both levels use your stop 37 grades.
- Part A: the 34 graded sentences (28 right, 6 wrong). V0 as recorded: 19 false rollbacks, 4 caught.
- Part B: the plain answer to each of the 40 questions (32 correct, 8 wrong), split into sentences
  with the engine's segmenter. Every sentence is audited. A correct answer with any rollback is a
  false rollback. A wrong answer with at least one rollback is caught. This is loose, since the
  flagged sentence may not be the wrong one.

The audit runs on one Modal L4 (`scripts/modal_normalise.py`). It receives the documentation, the
facts and the texts, never a grade. V0 is recomputed there and compared with the recorded Part A
verdicts. If the GPU moves a borderline score, the Modal V0 is the baseline and every difference is
listed. Scoring runs on the laptop from the committed output.

### Readings, set now

- R1: an arm is viable if, on both levels, it at most halves V0's false rollbacks and still catches at
  least 90 % of what V0 catches (the stop 40 bar). For Part A that is at most 9 false rollbacks and at
  least 4 caught. If S passes, the full run follows. At these sizes a pass is a signal, not proof.
- R2: each wrong text that passes with a derived fact as its best entailing candidate, with that fact.
- R3: the false rollbacks left in S, split into claim check, fact present on the judged passage but
  entailment still failed, and no fact on that passage.
- Also reported: facts proposed, kept and dropped by each rule, entailment time per sentence, and
  accuracy against the claim check alone and against no auditor.

### Stop 41: prompt frozen (2026-10-09, before the battery run)

The first pilot prompt mostly restated the text: 52 of 55 facts kept, none derived in a way that mattered. The
prompt was revised once to ask for derived facts by name (defaults, definitions, references, thresholds,
units, arithmetic), with two examples from neither battery, and to mark each fact as derived or not. Second
pilot: 60 of 62 facts kept, 13 derived, 2 dropped for a citation not in the quotes, no arithmetic. Frozen
prompt sha256 `10f6251f4b36fa018e4c2e686897db9c193f865a885978661ed392e964d8f96a`. Pilot calls: 6.

### Stop 41: results (2026-10-09)

Raw: `results/normalise/` (`audit.jsonl`, `report.json`). Gemini kept 227 of 231 facts, 54 of them derived. The
check dropped 4, all for a quote not in the source. The V0 recomputed on the L4 matched all 34 recorded Part A
verdicts.

| Level | Arm | False rollbacks | Caught | Accuracy |
|---|---|---|---|---|
| Part A, sentences (28 right, 6 wrong) | V0 | 19 | 4 | 38 % |
| | S | 13 | 4 | 56 % |
| | S-claims | 13 | 4 | 56 % |
| | Claim check only | 1 | 2 | 85 % |
| | No auditor | 0 | 0 | 82 % |
| Part B, answers (32 right, 8 wrong) | V0 | 9 | 4 | 68 % |
| | S | 9 | 3 | 65 % |
| | S-claims | 9 | 3 | 65 % |
| | Claim check only | 1 | 1 | 80 % |
| | No auditor | 0 | 0 | 80 % |

R1: no arm is viable. S cuts Part A false rollbacks from 19 to 13; the bar was 9. Part B does not move. The full
run does not follow.

The facts fix the case they were built for. All three A01 sentences now pass, and so does B37A, on the fact "By
default, the divisor used in numpy.std calculations is N". In Part A, 7 right sentences pass that V0 rolled back.

The facts also add rollbacks. When no candidate entails a sentence, the auditor judges it on its most related
candidate. A short fact is often the most related, and the entailment model can read it as a contradiction. Four
right texts that V0 passed are now rolled back (A09B, B15A, B24A, B32A). B32A says a table name is at most 63 bytes,
which is correct; the fact "the system uses no more than NAMEDATALEN-1 bytes" scored 0.76 contradiction. In Part B
three answers were fixed (B06A, B22C, B37A) and three were broken (B15A, B24A, B32A).

R2: no wrong text passes because of a fact that V0 caught. Every wrong text with a fact as its best entailing
candidate already passed under V0. The one catch lost in Part B (B38B) was a correct sentence that V0 had rolled
back. No fact was found to be wrong. In B35A the entailment model accepted "by default zero_grad sets gradients
to zero" from the fact "set_to_none defaults to True", which says the opposite.

R3: 23 false rollback sentences remain in S. The claim check gave 3. The other 20 had a fact on the judged passage
and entailment still failed. In several the fact says what the sentence says. A03C scored 0.003 entailment against
a fact that differs only by "The documentation explicitly states that". A05 and A11 are paraphrases scored neutral
or contradicted. A10 needs an inference no fact states (logits are unnormalised, so do not apply softmax first).

Entailment time per sentence on the L4: 93 ms V0, 87 ms S, 112 ms S-claims.

Not pre-registered, from the logged scores: using facts only to support, never as the candidate a sentence is judged
against, would give 12 false rollbacks and 4 caught on Part A, and 6 and 3 on Part B. That also misses the bar.

Reading: precomputed facts remove the reasoning gap where it is the cause. The larger cause is the entailment model
itself, which fails on paraphrases of text it is given. On both levels the claim check alone is more accurate than
any arm with the entailment check.

## Stop 42: a reasoning LLM as the auditor's judge (method fixed 2026-10-09, before any judge call)

DeBERTa reads a sentence and a passage in one pass. It cannot apply a default, follow a reference or do a sum.
Stops 40 and 41 changed its inputs and did not fix the false rollbacks. Its scores rank right against wrong
sentences at about chance (stop 41). Larger or legal-tuned single-pass models share that limit. This stop puts
a reasoning LLM in the entailment check and measures accuracy and latency. Two single-pass models run as
controls.

### The judge

One call per clause the auditor sends to its entailment check (`scripts/auditor_judge.py`). The prompt holds:
- the clause;
- the auditor's own candidates as numbered passages (windows, joined windows, enrichment elements);
- the answer so far, marked as context for references only, not evidence.

The question is not sent. The clause is supported only if a passage states it or it follows from the passages
by reasoning: a default applied, a definition substituted, a reference followed, units converted, arithmetic.
A true clause the passages do not establish is not stated. The reply is JSON with a label (supported,
contradicted, not_stated), the deciding passage and one sentence of reason. At most 3 asks for a valid reply.
No valid reply counts as not stated and is reported. Labels are cached by the prompt's sha256.

Judges:
- `gemini-3.8-flash-high` through the router, temperature 0, 4 calls at a time.
- `Qwen/Qwen3.8-27B-FP8` @017b9c7 on one Modal H100, SGLang v0.5.21, thinking on, the card's sampling
  (temperature 1.0, top_p 0.95, top_k 20), seed 0. Reasoning effort low and xhigh. The card offers low, medium
  and xhigh; there is no "high". Part A is run a second time at xhigh with seed 1.

The prompt is piloted on 5 dev battery texts per judge, not scored, then frozen. Its sha256 is recorded here
before the full run.

### Placements

Both come from the same labels.
- Replace: the judge is the entailment model. Supported is entailment 1 on its passage, contradicted is
  contradiction 1 there, not stated is neutral 1 on every candidate. The claim check, thresholds and engine are
  unchanged. A secondary row uses the strict policy, which rolls back every not-stated sentence.
- Appeal: V0's verdicts. A rollback whose reasons are all entailment reasons is lifted when the judge supports
  every clause of the sentence. Claim check rollbacks stand.

### Controls

In DeBERTa's place, scored with the verifier's own chunking at each model's length.
- `lytang/MiniCheck-DeBERTa-v3-Large` @2f2d01a, 512 tokens. Supported is entailment; it has no contradiction.
- `tasksource/ModernBERT-large-nli` @ca476cb, 2048 tokens (premise budget 1917). It tests whether whole
  provisions help.

Thresholds come from the dev battery: 25 configurations (entail 0.5 to 0.9, contradict 0.3 to 0.7, the rest as
run). The rule: the lowest pass-class false rollback rate among configurations with failure recall at least V0's
at 0.70 / 0.40. If none qualifies, the highest recall. Ties go to the configuration nearest 0.70 / 0.40. The
held-out battery stays sealed.

V0 and both controls score each (candidate, clause) pair once on a Modal L4 (10,376 pairs). The laptop replays
the verifier from those tables. The V0 replay must give the verdicts as run: Part A and statutes as recorded,
Part B as stop 41. Any difference is listed.

### Sets

| Set | Texts | Labels | Weight |
|---|---|---|---|
| Part A | 34 sentences (28 right, 6 wrong); 32 reach the entailment check | your stop 37 grades | primary |
| Part B | 40 plain answers, 87 sentences; 85 reach the entailment check | your stop 37 grades | primary |
| Statutes | 212 core texts of stop 36, premise as run; 172 reach the entailment check | Claude Opus 5.5 | secondary |

Part B scores answers: a right answer with any rollback is a false rollback, a wrong answer with any rollback is
caught. The statute labels are from an LLM, so an LLM judge scored on them is partly circular. In all, 280
unique prompts. No grade, label or recorded verdict is sent to Modal or the router.

### Readings, set now

- R1, primary: each judge and placement against V0 on Part A and Part B, at the stop 40 bar (false rollbacks at
  most half of V0's, caught at least 90 % of V0's). Accuracy beside claim check only and no auditor. If any
  judge and placement passes on both, the judge goes to a fresh test, then live. If none passes, the limit is
  not the scorer.
- R2: the same on statutes, reported apart.
- R3: latency per judged clause (p50, p95) and Qwen's generated tokens. Time added per Part B answer for each
  placement, clauses judged one after another. Gemini's time includes the network. Qwen's bulk run sends 16 at
  a time, so its single-stream latency comes from 20 Part A prompts re-run one at a time per effort.
- R4: the controls on the R1 bar. AUC of each entailment model's support score (per text, the lowest best
  entailment over its clauses) for right against wrong, with a 95 % bootstrap interval (2,000 resamples, seed
  42).
- R5: every wrong text a judge passes and every right text it rolls back under Replace, with its reasons. Not
  reclassified.
- R6: Qwen's agreement with itself on Part A at xhigh.

### Stop 42: prompt frozen (2026-10-09, before the full run)

Pilot on dev texts vdev-0001, 0002, 0003, 0006 and 0007, one clause each. Gemini and Qwen at both efforts gave
valid JSON on the first ask, 15 of 15. All three supported the first three and contradicted the last two
("must hear" against "may consider"; "never" against the late-claim exception). Gemini took 4 to 9 s per call.
Qwen low took 6 to 10 s and 315 to 665 tokens. Qwen xhigh took 3 to 86 s and 197 to 6,921 tokens. The prompt
is kept as written. Frozen prompt sha256 `72ce7d0514311749ccdd1d9f4430f5beea7d8757eeb9bd73be16fe9eae0e437b`.
Pilot calls: 5 Gemini, 10 Qwen.

### Stop 42: results (2026-10-09)

Raw: `results/auditor_judge/` (`labels/`, `scores/`, `report.json`, `r5.jsonl`). Gemini answered all 280 prompts
on the first ask. Qwen needed a second or third ask on 3 of 280 at low and none at xhigh. No prompt ended without
a label. The V0 replayed from the L4 table gave the verdict as run on every text: 34 of 34 on Part A, 87 of 87
on Part B, 212 of 212 on statutes.

Part A, 34 sentences (28 right, 6 wrong). Bar: at most 9 false rollbacks, at least 4 caught.

| Arm | False rollbacks | Caught | Accuracy | Bar |
|---|---|---|---|---|
| V0 | 19 | 4 | 38 % | |
| Claim check only | 1 | 2 | 85 % | |
| No auditor | 0 | 0 | 82 % | |
| MiniCheck | 9 | 2 | 62 % | no |
| ModernBERT-large | 4 | 4 | 82 % | yes |
| Gemini, Replace | 5 | 5 | 82 % | yes |
| Gemini, Replace strict | 6 | 6 | 82 % | yes |
| Gemini, Appeal | 5 | 4 | 79 % | yes |
| Qwen low, Replace | 1 | 5 | 94 % | yes |
| Qwen low, Replace strict | 1 | 5 | 94 % | yes |
| Qwen low, Appeal | 1 | 4 | 91 % | yes |
| Qwen xhigh, Replace | 2 | 5 | 91 % | yes |
| Qwen xhigh, Replace strict | 3 | 5 | 88 % | yes |
| Qwen xhigh, Appeal | 2 | 4 | 88 % | yes |

Part B, 40 answers (32 right, 8 wrong). Bar: at most 4 false rollbacks, at least 4 caught.

| Arm | False rollbacks | Caught | Accuracy | Bar |
|---|---|---|---|---|
| V0 | 9 | 4 | 68 % | |
| Claim check only | 1 | 1 | 80 % | |
| No auditor | 0 | 0 | 80 % | |
| MiniCheck | 5 | 4 | 78 % | no |
| ModernBERT-large | 3 | 3 | 80 % | no |
| Gemini, Replace | 2 | 5 | 88 % | yes |
| Gemini, Replace strict | 7 | 8 | 82 % | no |
| Gemini, Appeal | 3 | 2 | 78 % | no |
| Qwen low, Replace | 1 | 2 | 82 % | no |
| Qwen low, Replace strict | 1 | 4 | 88 % | yes |
| Qwen low, Appeal | 1 | 1 | 80 % | no |
| Qwen xhigh, Replace | 1 | 3 | 85 % | no |
| Qwen xhigh, Replace strict | 3 | 6 | 88 % | yes |
| Qwen xhigh, Appeal | 1 | 1 | 80 % | no |

R1: three arms pass on both levels: Gemini Replace, Qwen low Replace strict and Qwen xhigh Replace strict. By the
rule set before scoring, the judge goes to a fresh test, then live. Each passing arm is more accurate than the
claim check alone on both levels (Part A 82 to 94 % against 85 %, Part B 88 % against 80 %), except Gemini on
Part A (82 %). Appeal passes Part A but fails Part B everywhere: it can only lift V0's rollbacks, and on Part B
it lifts the ones that caught errors. Part A has 6 wrong texts and Part B 8, so one text moves a bar.

R2, statutes (116 right, 73 wrong; Claude's labels). No arm passes. The claim check gives 28 of V0's 56 false
rollbacks, and no judge touches those. Every judge arm is more accurate than V0 (59 %), claim check only (62 %) and
no auditor (61 %). The best are Gemini Replace strict (54 false rollbacks, 67 caught, 68 %) and Qwen xhigh Replace
strict (44, 56, 68 %). False rollbacks from the entailment check alone fall from 28 (V0) to 5 (Qwen low Replace)
and 11 (Gemini Replace).

R3, latency per judged clause:

| Judge | How run | p50 | p95 | Generated tokens, mean |
|---|---|---|---|---|
| Gemini | router, 4 at a time | 4.3 s | 12.5 s | not returned |
| Qwen low | one at a time, 20 Part A prompts | 2.6 s | 10.0 s | 301 |
| Qwen xhigh | one at a time, 20 Part A prompts | 4.0 s | 87.5 s | 1,482 |
| Qwen low | 16 at a time, all 280 | 7.8 s | 23.2 s | 526 |
| Qwen xhigh | 16 at a time, all 280 | 10.4 s | 132.9 s | 1,832 |

Time added per Part B answer, clauses judged one after another, from the bulk timings: Replace judges 85 of 87
sentences and adds 8.5 s on average with Gemini (p95 19.0 s), 11.3 s with Qwen low (29.5 s) and 33.7 s with Qwen
xhigh (187.3 s). Appeal judges 13 of 87 and adds 1.4 s, 2.2 s and 9.0 s. V0 takes about 0.1 s per sentence. The
Qwen bulk figures include queueing behind 15 other requests, so they overstate one-at-a-time latency. Statute
prompts are longer than the Part A prompts timed one at a time.

R4, controls. MiniCheck: no dev configuration reached V0's failure recall (0.854). The highest, at 0.80 / 0.40,
reached 0.746 with 9.9 % pass-class false rollbacks (V0 5.7 %). ModernBERT-large: 0.80 / 0.30 qualified, with
11.4 % false rollbacks. Neither passes on both levels. ModernBERT passes Part A and catches 3 of 8 on Part B. AUC
of the support score, right against wrong, with 95 % intervals:

| Model | Part A (28 / 4) | Part B (32 / 7) | Statutes (104 / 59) |
|---|---|---|---|
| V0 | 0.48 (0.13 to 0.84) | 0.72 (0.49 to 0.91) | 0.60 (0.51 to 0.69) |
| MiniCheck | 0.55 (0.14 to 0.97) | 0.77 (0.59 to 0.91) | 0.62 (0.53 to 0.71) |
| ModernBERT-large | 0.69 (0.28 to 0.96) | 0.81 (0.60 to 0.97) | 0.64 (0.55 to 0.72) |

ModernBERT ranks highest on every set, but the intervals overlap. The longer context does not close the gap on
these sets.

R5 lists 79 texts for Gemini, 77 for Qwen low and 78 for Qwen xhigh across the three sets (`r5.jsonl`). On Part A,
Qwen low's one false rollback is A12C, a claim check rollback the judge supported. Gemini rolled back A04A and
A04B as contradicted (the source says a counter can be reset to zero on restart) and A10A and A10B as not stated
(the source says the loss expects unnormalised logits and does not mention softmax). On Part B, every judge
supported every sentence of B01A, B27A and B38B, which are graded wrong. B38B and A04A both say "a Prometheus
counter cannot go down" and carry opposite grades. Not reclassified.

R6: Qwen xhigh gave the same label on 29 of 32 Part A prompts across two seeds.

Reading: a reasoning judge fixes most of the entailment check's false rollbacks on these sets, which DeBERTa,
MiniCheck and ModernBERT do not. Low effort did as well as xhigh at a fraction of the time. Its cost is seconds
per answer against about 0.1 s. The claim check's own false rollbacks remain, and on statutes they are half the
total.

## Stops 43 to 47: a fast student of a frontier teacher (method fixed 2026-10-09, before any run)

Stop 42 showed a reasoning judge fixes the entailment check, at seconds per clause. These stops test whether a
fine-tuned student that answers without thinking gets close to a frontier teacher at no more than 2 s p95 per
clause. Plan in brief:
- Stop 43: a fresh blind test, built and sealed before any training data exists.
- Stop 44: teacher check and untrained baselines on Part A, Part B and statutes.
- Stop 45: training data from sources disjoint from every test set, labelled by the teachers.
- Stop 46: K2 Horizon 7B fine-tuned. If it is more than 3 points below the teacher labels' accuracy on Part A
  or Part B, work halts for your review before Qwen3.8 27B is trained.
- Stop 47: the fresh test, run once.

Router models, one endpoint: `gemini-3.8-flash-high` and `claude-opus-4-6-thinking` (teachers), and
`claude-opus-5-5(high)` (teacher check and disagreements only, hard stop at $40 by a committed ledger). Modal has a
hard stop at $55 by a ledger of GPU time at list prices. Every paid step is resumable: results are written per
item as they arrive, reruns skip what is done, rate limits and server errors back off and retry, and items still
failing are recorded and retried on the next run. Each stop is pre-registered below before it runs.

### Stop 43: the fresh test

- Software: 40 new questions, 8 per area as in stop 37, on documentation pages not in
  `batteries/software/test.jsonl`. Passages quoted verbatim, with `source_url` and licence. Every question has
  its answer in the premise.
- Statutes: 40 new questions in plain words, about 3 per area of the grid battery, each on one UK provision from
  `data/` that is in no battery (grid dev and test, verifier dev and held-out). Premise as run: the provision with
  its enrichment layer, built by `enrich_premises.py` for the new provisions.
- The questions are written by Claude Opus 5.5 from the source text, chosen for the question and not for the
  auditor's patterns. Nothing is tuned on them.
- Answers: Qwen 2.5 7B Instruct on a Modal L4, SGLang v0.5.21, greedy, at most 512 new tokens. Two per question:
  - with source: the stop 37 software prompt or the engine's legislation prompt, source included;
  - closed-book: the same prompt with the source sentence and the source removed (`You answer questions about
    software.` or `You answer questions about legislation.`, then the same instructions with "the
    documentation" or "the provisions" replaced by "what you know").
- Your sheet: every sentence (engine segmenter), under its question, the source and the answer so far. Column
  `correct`: yes if every claim in the sentence matches the source shown, no if any does not, unsure otherwise.
  Questions in a seeded random order, the two answers per question shuffled and lettered. The key is git-ignored;
  its sha256 and the battery files' sha256 are recorded here before you grade.
- The sealed files do not change after that commit. Stop 47 reads them once.

### Stop 43: rows and prompts fixed (2026-10-09, before any answer)

`batteries/fresh/` holds the 80 rows (README there lists every departure from verbatim quotes). The closed-book
system prompts, exactly:
- software: `You answer questions about software. State figures, defaults, version numbers and names exactly. If you
  do not know the answer, say so. Answer in a few plain sentences, without headings or lists.`
- statutes: `You answer questions about legislation. State figures, dates, section numbers and the names of Acts
  exactly. If you do not know the answer, say so. Answer in a few plain sentences, without headings or lists.`

The with-source prompts are stop 37's software prompt and the engine's `SYSTEM_PROMPT`. Answers run on a Modal L4
in chunks of 40, written as each chunk returns; a rerun answers only what is missing. Modal list prices read
2026-10-09: L4 $0.80, L40S $1.95, A100 80 GB $2.50, H100 $3.95 per hour, plus 15 % in the ledger
(`results/distill/modal_ledger.json`).

### Stop 44: teacher check and untrained baselines (method fixed 2026-10-09, before any teacher call)

On stop 42's texts (Part A, Part B; statutes reported apart and circular for Claude teachers).
- Batched teacher prompt: the passages once, the answer so far, then the clauses of one answer that share the same
  candidates, numbered, each judged with the earlier ones as context only. The rule and labels text are stop 42's.
  At most 12 clauses per call. Reply: `{"results": [...]}`, one `{sentence, label, passage, reason}` per clause, at
  most 3 asks. Each label is stored under the clause's stop 42 single-clause prompt key. Batched prompt sha256
  `57165b8fa735a5c4c736b008ffdc0f12f6226aaccb255aa7b4c58b6f6973509b`. Calls: Part A 32, Part B 39 (85 clauses),
  statutes 172.
- Runs: Gemini batched on all three sets; Opus 4.6 batched on all three; Opus 5.5 batched on Part A and B only.
- Batching rule: used for the teachers if Gemini batched agrees with Gemini per clause (stop 42 labels) on at
  least 90 % of clauses, and its Replace strict accuracy on Part A and on Part B each drops by at most one text.
  Otherwise teachers are called per clause.
- Consensus labels: Gemini and Opus 4.6 agree, kept; they disagree, Opus 5.5 decides (Part A and B). The students
  train on consensus labels unless consensus is less accurate than Gemini alone on both Part A and Part B under
  Replace strict.
- Untrained baselines on the 280 per-clause prompts, one at a time after a bulk pass: Qwen3.8 27B FP8 with thinking
  off on an L40S, and K2 Horizon 7B @3b6ae39 at low effort on an L4 (FP8). Same replay as stop 42.
- Reported: each arm on the stop 42 table (false rollbacks, caught, accuracy, bar), agreement between teachers,
  Opus 5.5 spend, latency per clause.

### Stop 43: answers and sheet sealed (2026-10-09, before you grade)

160 answers on a Modal L4 (4 chunks, all finished, $0.07 by the ledger): 360 sentences, 163 from answers with the
source and 197 closed-book. Your sheet is `results/fresh/sheet.md` (git-ignored: it quotes statute text), your
column is `correct` in `results/fresh/grades.csv`. Seal (`results/fresh/seal.json`), sha256:
- `batteries/fresh/software.jsonl` `9c31235f2b023cbc7fc34c70ce8df9a64ca0a59646ce48dfd2295eed4bf28b6a`
- `batteries/fresh/statutes.jsonl` `9e44bc8960fd1cdab5b7c68d510bb89c09480a41242bfb21e580a5497ed3aa3c`
- `results/fresh/answers.jsonl` `36b687cb5e77dfbb2e54c43d3d4f6ca34a39d937c3c2cf7a6f02612e696e7e9d` (git-ignored)
- `results/fresh/key.json` `9d052dcca678f94a3ee9010bd07e9251c5f615cbdac5e3947ef98afbc886497b` (git-ignored)
- `results/fresh/sheet.md` `70cadb0bd6712c2dc23390e520ce2822f7ccb24d965ed7bf59119a575cad42f8` (git-ignored)

No model sees these answers before stop 47. Training data in stop 45 excludes every fresh source by code.

### Stop 44: a change before any K2 result (2026-10-09)

SGLang 0.5.21 serves K2 Horizon in FP8 only from pre-quantised weights, so the untrained K2 baseline runs in bf16
on an L40S, not FP8 on an L4. The trained student's target GPU is decided in stop 46.

### Stop 45: training data (method fixed 2026-10-09, before any question or label call)

- Pool (`scripts/distill_data.py pool`, seed 20261009): 250 in-force statute sections from the Acts the batteries
  draw on, at most 6 per Act, 400 to 6,000 characters, none overlapping any battery, the fresh test or an anchor;
  60 software sections from 20 public documentation pages used by no battery (at most 5 per page, 300 to 2,500
  characters, split at text blocks). The code fails if any source overlaps a test set. Statute premises as run,
  with an enrichment layer built for the new sections.
- Questions: Gemini writes 3 per source from the source text only (prompt sha256 in `distill_data.QUESTION_SHA`).
- Answers: Qwen 2.5 7B on a Modal L4, greedy, with the source and closed-book (stop 43's prompts).
- Clauses: every sentence through the verifier with the recording scorer; the clauses that reach the entailment
  check, with their candidates and the answer so far.
- Labels: Gemini and Opus 4.6, batched per answer as in stop 44 (or per clause if stop 44's batching rule fails).
  Batches with a disagreement go to Opus 5.5 whole, and its labels are used for the disputed clauses only, until
  the $40 cap. Disputed clauses left after the cap are dropped and counted.
- Examples: the stop 42 per-clause prompt and the label's JSON reply. Validation is 10 % of sources, chosen by a
  hash of the source id. Prompts over 8,192 tokens are dropped from training, kept in the counts.

### Stop 44: results (2026-10-09)

Raw: `results/distill/check44.json`, labels in `results/distill/labels/` and `results/auditor_judge/labels/`.

Batching rule: not met. Gemini batched agreed with Gemini per clause on 270 of 291 clauses (92.8 %, rule 90 %), but
Replace strict on Part A got 2 texts fewer right (rule: at most 1). Part B: 1 fewer. Teachers are called per clause
from here.

Opus 4.6 hit the router's limit after 167 calls (about 440k input tokens): HTTP 429 with Retry-After 13,155 s. It
covered Part A and B fully and 96 of 174 statute clauses. Opus 5.5 covered Part A and B for $0.57.

| Arm (Replace strict unless noted) | Part A FR / caught | Part A accuracy | Part B FR / caught | Part B accuracy |
|---|---|---|---|---|
| V0 | 19 / 4 | 38 % | 9 / 4 | 68 % |
| Gemini per clause (stop 42) | 6 / 6 | 82 % | 7 / 8 | 82 % |
| Gemini batched | 8 / 6 | 76 % | 8 / 8 | 80 % |
| Opus 4.6 batched | 1 / 5 | 94 % | 1 / 3 | 85 % |
| Opus 5.5 batched | 3 / 5 | 88 % | 3 / 3 | 80 % |
| Consensus (Gemini per clause and Opus 4.6; Opus 5.5 on disagreement) | 2 / 5 | 91 % | 2 / 3 | 82 % |
| Qwen 27B, thinking off, untrained | 1 / 5 | 94 % | 2 / 2 | 80 % |
| K2 Horizon 7B, low effort, untrained | 1 / 3 | 88 % | 1 / 1 | 80 % |

Part A has 28 right and 6 wrong sentences, Part B 32 right and 8 wrong answers. Consensus is not less accurate than
Gemini alone on both levels, so by the rule the students train on consensus labels. Teacher agreement: Gemini and
Opus 4.6 75 % (213 clauses), Gemini and Opus 5.5 83 %, Opus 4.6 and Opus 5.5 97 % (117 clauses). Nearly every
disagreement is Gemini saying not stated where an Opus model says supported.

Statutes (Claude's labels, Replace strict): Gemini 68 %, Qwen 27B thinking off 67 %, K2 low 67 %.

Latency per clause, one at a time on an L40S: Qwen 27B thinking off p50 3.0 s, p95 4.8 s (62 tokens); K2 low p50
1.5 s, p95 3.9 s (70 tokens, a short reasoning before the reply). K2's first run lost 232 replies: at low effort it
opens `<ifm|think_faster>` but closes `</ifm|think>`, so SGLang's parser left the reply inside the reasoning. The
client now takes the text after the last close tag, and the run was repeated before any reading. Router spend:
Opus 5.5 $0.57 of $40. Modal $1.37 of $55.

Pool for stop 45: 310 sources, 930 questions, 1,860 answers, 3,603 sentences, 3,004 unique clauses that reach the
entailment check (mean 6,200 characters per prompt). Fewer than the 5,000 planned.

### Stop 45: changes before any training label (2026-10-09, your decisions)

- Teacher: Gemini alone, per clause, on the stop 42 prompt. Opus 4.6 is dropped from training labels (router limit).
  Opus 5.5 labels a random 500 training clauses (seed 20261009), per clause, to measure label quality; its labels
  do not enter training. The stop 46 gate compares the student with Gemini's labels.
- Pool topped up to about 5,000 clauses: statute sections raised from 250 to 460 requested, 412 available under
  the per-Act cap (same seed, same order, so the first 250 and their ids are unchanged). Software stays at 60
  sections.

### Stop 46: the student (method fixed 2026-10-09, before any training)

- Student: K2 Horizon 7B @3b6ae39. LoRA rank 16, alpha 32, dropout 0.05, all linear layers; learning rate 1e-4,
  cosine, 3 % warm-up; batch 1 with 16 accumulation steps; one epoch; loss on the reply only; examples over 8,192
  tokens dropped. The reply follows an empty reasoning block (`<ifm|think>\n</ifm|think>`), in training and at
  inference, so the student never thinks. One H100; torch 2.14.0, transformers 5.17.0, peft 0.21.0, trl 1.13.0.
  A second epoch runs only if the first epoch's validation agreement with Gemini is below 85 %, and is kept only
  if agreement rises. A 10-step smoke run comes first. Checkpoints are committed to a Modal volume every 50 steps.
- Serving: the adapter merged in bf16, SGLang 0.5.21 on an L40S (SGLang serves K2 in FP8 only from pre-quantised
  weights, and bf16 does not fit an L4 with long statute prompts), temperature 0, at most 512 tokens.
- Readings: label agreement with Gemini on validation; the stop 42 table on Part A, Part B and statutes (Replace
  and Replace strict); latency per clause one at a time on 20 Part A prompts.
- Gate: if the student's Replace strict accuracy on Part A or on Part B is more than 3 points below Gemini's
  (stop 42 labels: Part A 82.4 %, Part B 82.5 %), work halts for your review before Qwen 27B is trained. Note:
  K2 untrained at low effort already scores 88.2 % and 80.0 %.
- Latency target: p95 at most 2 s per clause on the L40S.

### Stop 45: results (2026-10-09)

Pool (`results/distill/pool_index.json`): 412 statute sections and 60 software sections, 472 sources, none in any
test set (checked in code). Gemini wrote 3 questions per source (1,416; prompt sha256 in
`distill_data.QUESTION_SHA`); Qwen 2.5 7B wrote 2,832 answers on an L4 (with source and closed-book); 5,393 sentences
gave 4,433 unique clauses that reach the entailment check. Gemini labelled all 4,433 per clause, none failed:
1,850 + 197 not stated, 1,755 + 172 supported, 413 + 46 contradicted (train + validation). Train 4,018 examples from
426 sources, validation 415 from 46 sources.

Opus 5.5 labelled a random 500 of them: it agreed with Gemini on 410 (82 %). Of the 90 differences, Gemini said not
stated where Opus said contradicted 47 times and supported 36 times; the other 7 split 5 and 2. So Gemini's labels
lean to not stated, the same lean seen on the dev sets. Opus 5.5 spend so far $7.67 of $40; Gemini calls 5,600.

### Stop 47: the fresh test (method fixed 2026-10-09, before any judge sees a fresh clause)

360 sentences; 319 reach the entailment check, giving 323 per-clause prompts (stop 42's prompt) and 3,236
(candidate, clause) pairs. The judges label them before your grades exist. No grade is in any prompt, and the code
fails if a question appears in one. Scoring runs once, from the committed labels, after your grades are committed.
Units are sentences; `unsure` is left out.

Candidates and placements (Replace or Replace strict, whichever had the higher mean accuracy on Part A and Part B;
ties go to Replace):
- V0 (DeBERTa, scored on an L4 and replayed), claim check only, no auditor.
- Gemini per clause, the teacher: Replace (dev 82.4 / 87.5 against 82.4 / 82.5).
- Qwen3.8 27B low, thinking on, off the shelf (stop 42 settings, H100): Replace strict (94.1 / 87.5).
- Qwen3.8 27B thinking off, untrained (L40S): Replace (tie).
- K2 Horizon 7B low effort, untrained (L40S): Replace (tie).
- The K2 student (L40S): placement chosen from its stop 46 dev numbers by the same rule.

Readings, per domain (software, statutes) and in total:
- F1: each candidate against V0 at the stop 40 bar (false rollbacks at most half, caught at least 90 %).
- F2, the distillation reading: the student succeeds if its accuracy is within 3 points of Gemini's on each
  domain and its p95 per clause one at a time is at most 2 s.
- F3: the student against Qwen 27B low off the shelf.
- F4: latency per clause, and time added per answer, from the bulk runs.
- F5: every error of the teacher and the student, with its reason. Not reclassified.
- Also reported: answers with the source and closed-book apart; for the sentences you grade wrong, how often each
  judge says contradicted and how often not stated.

### Stop 46: results (2026-10-09)

Training: 4,018 examples, none over 8,192 tokens, one epoch (252 steps) in 33.5 min on an H100, final loss 0.28.
Two allocation warnings for memory at steps 33 and 156; the run continued. Validation agreement with Gemini: 370
of 415 (89.2 %), so no second epoch (rule: below 85 %). Most differences: Gemini contradicted, student not stated
(15); Gemini not stated, student supported (14).

| Arm | Part A strict FR / caught | Part A accuracy | Part B strict FR / caught | Part B accuracy | Statutes strict |
|---|---|---|---|---|---|
| Teacher (Gemini per clause) | 6 / 6 | 82.4 % | 7 / 8 | 82.5 % | 68.3 % |
| K2 student | 6 / 4 | 76.5 % | 5 / 5 | 80.0 % | 64.6 % |
| K2 untrained, low effort (stop 44) | 1 / 3 | 88.2 % | 1 / 1 | 80.0 % | 66.7 % |

Under Replace the student scores 76.5 % and 77.5 %. Latency one at a time on the L40S: p50 1.2 s, p95 1.7 s
(51 tokens), within the 2 s target. Bulk (16 at a time): p50 3.2 s.

Gate: the student is 5.9 points below the teacher on Part A (2 of 34 texts) and 2.5 on Part B. Work halts for
your review before Qwen 27B is trained. The student is less accurate than the untrained K2 on Part A: it learned
Gemini's lean to not stated, which rolls back right sentences (6 against 1). Modal spend $6.33 of $55. Router: Opus
5.5 $7.67 of $40. Gemini is rate-limited until about 18:07 UTC (HTTP 429, Retry-After 5,808 s) with 200 of 323 fresh
clauses labelled.

### Stop 47: results (2026-10-10)

Order of events: your grades were committed (`b8b3c4d`), Gemini labelled its last 123 fresh clauses, then the
scoring ran once. One departure: those 123 Gemini labels were made after your grades existed. No grade is in any
prompt and the prompt was unchanged. You graded 360 sentences: 210 yes, 148 no, 2 unsure. Units: 358 (software 117
right and 53 wrong, statutes 93 right and 95 wrong). Raw: `results/fresh/report.json`, `errors.jsonl`.

Each cell is false rollbacks / wrong sentences caught, then accuracy.

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

- F1: the two untrained Replace arms pass the bar on software and in total. No arm passes on statutes. The two
  strict arms fail the bar on false rollbacks and have the highest accuracy.
- F2: the student is 10.0 points above Gemini on software and 9.5 above on statutes, with p95 1.7 s one at a
  time. It succeeds as written. The two arms had different placements, so this gap is mostly the placement (see
  below).
- F3: the student is 4.0 points below Qwen 27B low (3.5 on software, 4.3 on statutes), with 17 more false
  rollbacks and 3 more caught.
- F4: latency per clause in the bulk runs (requests in parallel, so queueing is included): Gemini p50 6.1 s, p95
  24.8 s; Qwen low 6.6 s, 19.4 s; Qwen thinking off 11.4 s, 17.8 s; K2 low 3.5 s, 11.1 s; student 2.1 s, 4.9 s.
  Time added per answer (149 answers reach the judge): student p50 4.6 s, p95 10.8 s; K2 low 8.2 s, 24.2 s; Gemini
  14.7 s, 53.1 s; Qwen low 15.6 s, 39.7 s. The scored report left the per-answer figure out; it is in
  `posthoc.json`.
- F5: 95 errors for Gemini (30 right sentences rolled back, 65 wrong passed) and 60 for the student (52 and 8),
  listed in `results/fresh/errors.jsonl`.
- With source and closed-book apart: answers with the source have 141 right and 22 wrong sentences, closed-book 69
  and 126. On answers with the source: no auditor 86.5 %, V0 77.3 %, Gemini 82.8 %, Qwen low strict 88.3 %, student
  81.6 %. Closed-book: no auditor 35.4 %, V0 61.5 %, Gemini 65.6 %, Qwen low strict 86.2 %, student 84.6 %.
- Labels on the sentences you graded wrong (120 clauses): Gemini not stated 90, contradicted 28, supported 2;
  student 91, 20, 9; Qwen low 71, 36, 13; K2 low 66, 24, 30.

### Stop 47: readings added after the run (2026-10-10, not pre-registered)

`scripts/fresh_posthoc.py`, raw in `results/fresh/posthoc.json`. They change no figure above.

Every judge under both placements, total (false rollbacks / caught, accuracy):

| Judge | Replace | Replace strict |
|---|---|---|
| Gemini | 30 / 83, 73.5 % | 62 / 146, 82.1 % |
| Qwen 27B low | 26 / 86, 75.4 % | 35 / 137, 87.2 % |
| Qwen 27B thinking off, untrained | 21 / 78, 74.6 % | 26 / 132, 88.3 % |
| K2 low, untrained | 19 / 71, 73.2 % | 22 / 119, 85.8 % |
| K2 student | 28 / 78, 72.6 % | 52 / 140, 83.2 % |

- Placement decides more than the judge. Strict adds 9 to 14 points for every judge. Gemini labels 89 of the 148
  wrong sentences not stated and 28 contradicted; the claim check stops 29 before the judge. Replace passes a
  sentence that is not stated. The dev sets had few wrong sentences (6 of 34 and 8 of 40), so they picked Replace
  for three arms.
- Same placement: under strict the student is 4.7 points above Gemini on software and 2.2 below on statutes.
  Under Replace it is 1.7 below and level. F2 holds either way.
- Under strict the untrained K2 is 2.6 points above the student, with 22 false rollbacks against 52 and 119 caught
  against 140. The student copied Gemini, which has the most false rollbacks (62).
- The claim check rolls back 12 right sentences before any judge sees them (all `UNGROUNDED_FIGURE`). That is the
  floor for every judge arm.
- List numbers. The closed-book answer to fl-02 is a numbered list. The segmenter split "1.", "2.", "3." and "4."
  into sentences. You graded them yes (no claim). The claim check rolls back "2.", "3." and "4." as figures not in
  the source, and the strict judges roll back "1." as not stated. Without these 4 sentences every arm gains 0.5 to
  1.0 point and the order is unchanged. This is a defect in the segmenter and the claim check, not in the judges.
- Your side experiment: one prompt with the whole sheet (question, source, both answers). Gemini agrees with your
  grades on 329 of 360 sentences, Opus 5.5 on 349. Read as an auditor (no or unsure means rollback): Gemini 17 / 136,
  91.9 %; Opus 5.5 2 / 145, 98.6 %. These are not candidates: they saw the question and the source as you saw it.
  The judge in the auditor sees one clause, the auditor's candidate passages and no question. The same Gemini model
  scores 82.1 % there.
- Checked after stop 48: the candidate passages hold the whole source in all 323 fresh prompts. Software: 1
  passage. Statutes: 15 passages at the median and up to 59, about 4 times the source length, because joined and
  derived passages repeat text. The gap to the whole sheet is not missing source. What differs: no question, the
  source cut and repeated, one sentence per call, and a different rule (supported, contradicted or not stated
  against your yes, no or unsure).

## Stops 48 and 49: an awareness signal for the auditor (method fixed 2026-10-10, before any run)

Stop 47 showed that most wrong sentences are facts the generator added from memory. These stops test a signal read
from the model itself: whether it was reading its input when it wrote. Your direction (2026-10-10). The fresh test
was already used after stop 47 to compare placements, so these stops are exploratory on it. A result here needs a
new graded set to confirm it. No student is trained. No router call is made. Nothing in `src/` changes.

Two directions, both on the 358 graded fresh sentences, compared with the stop 47 table:
- J, the judge. K2 Horizon 7B at low effort and Qwen3.8 27B with thinking off, both untrained, label each clause
  with the stop 42 prompt. The signal says whether the judge read the passages. A label under the threshold is
  asked again.
- G, the generator. Qwen 2.5 7B only. The signal says whether each sentence it wrote came from the source. No
  judge and no DeBERTa.

### The signal

Read in Hugging Face transformers (torch 2.14.1, transformers 5.18.0), eager attention, bf16, from the model that
produced the text. Two measures:
- Attention share. For each token of the text, the attention from its position to the input span, over all
  attention except to the first token, mean over heads (stop 29's measure). Mean over the text's tokens. Four
  summaries by layer: all layers, and the lower, middle and upper third.
- Dependence on the input. Log-likelihood per token of the text with the input, minus the same without it.

That is five candidates, in this order: attention all layers, lower, middle, upper, dependence. Higher means more
aware. The sign is fixed.

- G. Text: one sentence of an answer (a token belongs to the sentence in which it starts). Input span: the source
  inside the with-source prompt of stop 43. With: that prompt and the answer so far. Without: the closed-book
  prompt of stop 43 and the answer so far. Answers written with the source are measured as written. Closed-book
  answers are fed under the with-source prompt, which is not how they were written.
- J. Text: every token the judge generates (reasoning and reply). Input span: the passages and the sentence to
  check. With: the stop 42 prompt. Without: the same prompt with the passages replaced by `(none)`.

Folds: the 80 questions are split in two by question (seed 20261010), 20 software and 20 statutes in each. For
each fold the candidate with the highest AUROC on that fold is chosen (ties go to the earlier in the order above),
with its threshold. Both are applied to the other fold only. No sentence is scored with a choice made on its own
grade.

### Stop 48: offline check, one attempt per item

- G: Qwen 2.5 7B (`a09a3545`) on an L4. 160 answers, each fed under both prompts.
- J: K2 Horizon 7B (`3b6ae394`) on an L40S and Qwen3.8 27B on an H100. Each of the 323 fresh clause prompts is
  answered once with the recorded sampling of stop 44 and seed 0. K2: temperature 1.0, top_p 0.95, low effort, at
  most 2,048 new tokens. Qwen: temperature 0.7, top_p 0.8, top_k 20, presence penalty 1.5 on generated tokens,
  thinking off, at most 512 new tokens. The measures are read in the same pass. A reply that does not parse is
  sampled again with seed 100, then 200. After that it counts as not stated.
- A label is right when it agrees with your grade of its sentence: supported on a right sentence, contradicted
  or not stated on a wrong one. Sentences graded unsure are left out.

Readings:
- A1, generator: AUROC of each candidate, right sentences against wrong, in total, per domain, and per answer
  kind (with source: 141 right, 22 wrong; closed-book: 69 and 126). Dependence separates the two kinds of answer by
  construction, and the kind predicts the grade. So the gate for G uses the AUROC within kind: only pairs of a
  right and a wrong sentence from the same kind of answer are compared. The total is reported beside it.
- A2, judges: AUROC of each candidate, right labels against wrong labels. Supported labels apart: supported on a
  right sentence against supported on a wrong one. Agreement of the labels with the recorded SGLang labels.
- A3, the generator signal as the auditor: a sentence under the threshold is rolled back. Two arms: the signal
  alone, and the claim check followed by the signal. Threshold: the value with the highest accuracy on the other
  fold (ties go to the lower value). Scored as in stop 47 (false rollbacks, caught, accuracy), in total, per
  domain and per answer kind. Also the with-source answers alone, with the threshold tuned on with-source
  sentences of the other fold.
- A4: seconds per sentence and per clause, and the share of it added by the measures.
- Check: share of answer tokens equal to the model's top token under the prompt they were written with.

Gate, fixed now. A direction goes to stop 49 if the candidate chosen on each fold scores an AUROC of at least
0.65 on the other fold and at least 0.70 on average over the two. For G the AUROC is within kind. For J each
judge is gated on its own. A direction that does not pass stops and is reported as failed.

Fallbacks, recorded if used: if K2's custom code does not return attention weights, K2 runs on dependence only. If
transformers cannot load the FP8 weights of Qwen3.8 27B, the bf16 weights of the same model are used, with the
revision recorded here.

### Stop 49: the retry loop (only for a direction that passes its gate)

- J loop. Attempt 1 is stop 48's. Threshold: on the tuning fold, the value that flags the largest share of wrong
  labels minus the share of right labels (ties go to the lower value). A clause whose awareness is under the
  threshold of the other fold is asked again with seeds 1 to 5, same prompt and sampling. The first attempt at or
  over the threshold is kept. If none is, the attempt with the highest awareness is kept and the clause is counted
  as exhausted. No grade is used in the loop. Kept labels go through the stop 47 replay under Replace strict.
  - B1: the retry arm against the attempt-1 arm, and against the stop 47 arms (K2 low strict 85.8 %, Qwen 27B
    thinking off strict 88.3 %, K2 student 83.2 %, V0 68.7 %). A gain under 1.0 point in total (4 sentences)
    counts as no gain.
  - B2: clauses retried, exhausted, and labels changed to right and to wrong.
  - B3: seconds added per clause.
- G loop. Qwen 2.5 7B writes with the source; a sentence under the threshold is cut back and sampled again, at most
  5 times, keeping the most aware. It writes new sentences, which need new grades. Work halts for you before it
  runs.
- Which direction wins: accuracy on the 358 sentences, G from A3 (claim check then signal) and J from B1.

Spend and fail safe. Every GPU job runs in chunks. Each result is appended to JSONL under its prompt hash and seed,
and a rerun skips what is done. A failed chunk is reported and retried on the next run. The Modal ledger is checked
before each chunk and charged the wall-clock time of each chunk after it, failed or not. Stage stops in code: $12
for stop 48, $15 for stop 49, inside the $55 cap ($6.46 spent).

### Stop 48: results (2026-10-10)

All three gates fail. Stop 49 does not run. Raw: `results/awareness/` (`generator.jsonl`, `k2-low.jsonl`,
`qwen27-nothink.jsonl`, `report48.json`). Scored by `uv run python scripts/awareness.py report48`.

Departures from the method:
- Qwen3.8 27B ran from its bf16 weights (`Qwen/Qwen3.8-27B` at `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`), the
  fallback fixed above. Transformers loads the FP8 file but cannot run it in this image: the FP8 kernel package is
  missing and one group of weights is not matched. The labels of stop 47 came from the FP8 weights on SGLang.
- Qwen3.8 27B has 64 layers, of which 16 are attention layers. The attention share uses those 16.
- K2's code computes attention weights and drops them. They were read at its attention modules (36 layers). The
  dependence-only fallback was not needed.
- A retry rule detail not written above: a reply that never parses cannot be the kept attempt unless nothing else
  exists. Not used, since no loop ran.

Check on the replay: 88.4 % of answer tokens equal the model's top token under the prompt they were written with
(stop 29 measured 92 to 94 %). The judges' labels in transformers agree with the recorded SGLang labels on 291 of
323 clauses (K2, temperature 1.0) and 309 of 323 (Qwen). K2 needed a second sample for 2 replies. No reply stayed
unparsed.

A1, generator (Qwen 2.5 7B), AUROC of right against wrong sentences:

| Sentences (right / wrong) | Attention all | Lower | Middle | Upper | Dependence |
|---|---|---|---|---|---|
| Total (210 / 148) | 0.66 | 0.56 | 0.71 | 0.66 | 0.82 |
| Software (117 / 53) | 0.72 | 0.68 | 0.72 | 0.71 | 0.73 |
| Statutes (93 / 95) | 0.80 | 0.69 | 0.84 | 0.77 | 0.87 |
| With source (141 / 22) | 0.61 | 0.54 | 0.61 | 0.65 | 0.65 |
| Closed-book (69 / 126) | 0.56 | 0.46 | 0.62 | 0.54 | 0.67 |
| Within kind, the gate | 0.57 | 0.48 | 0.62 | 0.57 | 0.67 |

Gate for G: fold 0 chose dependence, 0.58 on the other fold. Fold 1 chose attention middle, 0.56. Both are under
0.65. Failed. Over all pairs, where the kind of answer helps, dependence scores 0.82 on each fold. That figure
mostly tells a closed-book answer from one written with the source.

A3, the generator signal as the auditor (false rollbacks / caught, accuracy), beside stop 47:

| Arm | Software | Statutes | With source | Closed-book | Total |
|---|---|---|---|---|---|
| Signal alone | 27 / 24, 67.1 % | 9 / 48, 70.2 % | 4 / 2, 85.3 % | 32 / 70, 54.9 % | 36 / 72, 68.7 % |
| Claim check then signal | 30 / 26, 66.5 % | 15 / 65, 76.1 % | 10 / 5, 83.4 % | 35 / 86, 61.5 % | 45 / 91, 71.5 % |
| V0 (stop 47) | 22 / 18, 66.5 % | 20 / 60, 70.7 % | 77.3 % | 61.5 % | 42 / 78, 68.7 % |
| K2 low, strict (stop 47) | | | | | 22 / 119, 85.8 % |

With-source answers alone, threshold tuned on with-source sentences: the best threshold rolls back nothing (86.5 %,
the same as no auditor).

A2, judges, AUROC of right labels against wrong labels:

| Judge, clauses (right / wrong labels) | Attention all | Lower | Middle | Upper | Dependence |
|---|---|---|---|---|---|
| K2 low, total (284 / 37) | 0.54 | 0.54 | 0.57 | 0.51 | 0.57 |
| K2 low, software (144 / 16) | 0.74 | 0.74 | 0.76 | 0.68 | 0.72 |
| K2 low, statutes (140 / 21) | 0.54 | 0.56 | 0.56 | 0.50 | 0.45 |
| K2 low, supported labels (192 / 28) | 0.55 | 0.54 | 0.61 | 0.49 | 0.61 |
| Qwen 27B, total (292 / 29) | 0.49 | 0.49 | 0.50 | 0.49 | 0.46 |
| Qwen 27B, software (150 / 10) | 0.80 | 0.76 | 0.79 | 0.80 | 0.62 |
| Qwen 27B, statutes (142 / 19) | 0.48 | 0.49 | 0.49 | 0.47 | 0.38 |
| Qwen 27B, supported labels (187 / 15) | 0.44 | 0.44 | 0.46 | 0.41 | 0.42 |

Gate for J. K2: both folds chose attention middle, 0.53 and 0.62 on the other fold. Failed. Qwen 27B: attention
middle 0.43 and dependence 0.42. Failed.

The attempt in transformers, scored as in stop 47 under Replace strict: K2 22 / 121, 86.3 % (recorded 22 / 119,
85.8 %); Qwen 27B 27 / 134, 88.5 % (recorded 26 / 132, 88.3 %). The recorded arms reproduce stop 47.

A4, time. Generator: 0.24 s per sentence at p50 for both passes; the pass without the source is 0.16 s per answer.
K2: 3.3 s per clause at p50 and 9.6 s at p95 to generate token by token, and 0.09 s for the pass without passages.
Qwen 27B: 5.5 s and 7.5 s, and 0.33 s. The attention share is read during generation at no extra pass. These
times are from transformers and are not comparable with SGLang's.

Spend: stop 48 $3.79 (stage stop $12). Modal $10.25 of $55. No router call.

### Stop 48: readings added after the run (2026-10-10, not pre-registered)

`uv run python scripts/awareness.py posthoc48`, raw in `results/awareness/posthoc48.json`.

- The signal follows the label, not whether the label is right. Mean attention share by label, K2: supported 0.21,
  contradicted 0.19, not stated 0.16. Qwen 27B: 0.37, 0.34, 0.31.
- Most wrong labels are supported on a wrong sentence: 28 of 37 for K2 and 15 of 29 for Qwen 27B. These have
  attention as high as right supported labels. The judge is reading the passages when it makes this error. It is
  not falling back on memory.
- The attention share rises with the length of the passages (rank correlation 0.28 to 0.51). Statute passages
  are about 15 times longer than software passages (1,266 against 83 tokens at p50 for K2). On software alone the
  signal separates (0.74 to 0.80), on 10 to 16 wrong labels.
- A second sample of the same prompt changes 32 of K2's labels: 11 become right and 9 become wrong. For Qwen 27B 14
  change, 4 each way. Asking again without a working signal is a coin toss.
- Generator, means within kind. With source: dependence 1.28 for right sentences and 0.86 for wrong; attention
  middle 0.20 and 0.18. Closed-book: -0.82 and -1.30; 0.16 and 0.14. The direction is as expected and the overlap
  is large.

## Stop 50: Gemini 3.1 Pro as a per-clause judge (method fixed 2026-10-10, before any call)

Your direction: test one more teacher candidate on data we already hold, and put it beside Gemini 3.8 Flash and
Opus 5.5. No whole-sheet prompt: it cannot run in production. Stop 49 (the retry loop) stays not run.

- Model: `gemini-3.1-pro-low` on the router, the id you gave. No other new model is called.
- Prompt: the stop 42 per-clause prompt, unchanged (sha256 `72ce7d0514311749ccdd1d9f4430f5beea7d8757eeb9bd73be16fe9eae0e437b`). Temperature 0, one clause per
  call, at most 3 asks for a valid reply, as for Flash.
- Sets, in this order:
  1. The fresh test, 323 clause prompts. Scored with your grades in the stop 47 table, under Replace and Replace
     strict, beside the recorded arms.
  2. The stop 42 sets, 280 clause prompts (Part A, Part B, statutes). Scored in the stop 44 table beside Flash per
     clause, Opus 4.6 batched, Opus 5.5 batched (Part A and B only) and the two untrained judges.
  3. The 500 training clauses that Opus 5.5 audited in stop 45. No grades exist for these.
- Readings:
  - C1, fresh: false rollbacks, caught and accuracy in total, per domain and per kind of answer. Pro against each
    recorded arm under strict: sentences only one of the two gets right, and an exact two-sided sign test.
  - C2, stop 42 sets: accuracy under Replace and Replace strict per set.
  - C3, agreement of labels: Pro with Flash on all three sets, Pro with Opus 5.5 on Part A, Part B and the 500.
    On the 500, where Flash and Opus 5.5 differ, which of the two Pro sides with.
  - C4: time per clause through the router (p50, p95), tokens and cost per clause.
- Reading fixed now: Pro counts as a better judge than Flash only if its strict accuracy on the fresh test is
  higher and the sign test gives p under 0.05. Otherwise the two are not told apart. No teacher is chosen by this
  stop; you decide after the figures.
- A clause with no valid label after two reruns counts as not stated, and the count is reported.
- Limits. Opus 5.5 has no per-clause labels on the fresh test, so the fresh table has no Opus 5.5 row. Its rows on
  Part A and B come from batched calls and Pro's from per-clause calls. The fresh test has been used since stop 47;
  this stop is exploratory on it.
- Fail safe: each label is appended as it returns, keyed by prompt hash; a rerun asks only what is missing.
- Spend: priced in the ledger at $2.00 and $12.00 per million input and output tokens (the list prices you gave;
  what the router bills is not known to this repo). Hard stop at $15 in code. Modal: none.
