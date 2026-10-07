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
