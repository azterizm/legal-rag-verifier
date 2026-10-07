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
