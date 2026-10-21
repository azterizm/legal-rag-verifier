# Research index

This page maps the evaluation behind the package to its files. Each test has a stop number. For each stop it
lists the method, the figures, the scripts and the results.

Read in this order. [`VERDICT.md`](VERDICT.md) states what holds. [`measurements.md`](measurements.md) holds
every figure. [`GRID.md`](GRID.md) holds every method, each fixed before its run. This page says where the
files are.

## Folders

| Folder | Contents |
|---|---|
| [`batteries/`](../batteries) | Test sets: sentences with labels, and questions. Fixed before use. |
| [`enrichment/`](../enrichment) | One JSON per provision: its elements and thresholds, each tied to a verbatim quote. Built by `enrich_premises.py` with Gemini 3.8 Flash. |
| [`results/`](../results) | Answers, traces, judge labels, grades and reports, one folder per test. |
| [`scripts/`](../scripts) | The code that built the batteries, ran each test and scored it. Not part of the package. |
| [`data/`](../data) | The statute corpus, built with `legal-rag-router`. Only `MANIFEST.json` is published. |
| [`tests/`](../tests) | Unit tests, including the scripts behind the figures (`test_<script>.py`). |

## Conventions

- Stop numbers come from the internal progress log. Only stops with a run are listed.
- Each method in `GRID.md` was committed before its run. Changes after a run are marked "not pre-registered".
- `report.json` in a results folder holds the figures `measurements.md` quotes.
- `grades.csv` holds the hand grades. `grader-*.jsonl` holds the model graders' labels, and `*.again.jsonl` their
  second pass. `leftover.csv` lists the sentences the graders did not settle, which were graded by hand.
- `seal.json` holds the hashes of a sheet or test fixed before grading.
- Answers, traces, grading sheets and keys quote statute text. They are git-ignored and stay local. Their
  counts and hashes are in the reports.
- Scripts named `modal_*.py` run on Modal. `router.py` calls the hosted models. Both are paid and keep a spend
  ledger in `results/`.

## Before the grid

| Run | Figures | Scripts | Results |
|---|---|---|---|
| NLI latency | [M2](measurements.md#m2--nli-latency-2026-10-05) | [`nli_latency.py`](../scripts/nli_latency.py) | [`nli_latency.json`](../results/nli_latency.json) |
| Detector on the dev battery, threshold sweep | [M2](measurements.md#m2--detector-on-the-dev-battery-2026-10-05) | [`run_battery.py`](../scripts/run_battery.py) | `results/dev-*.json` |
| Claim check fixes and enrichment, dev only | [Accuracy plan](measurements.md#accuracy-plan--step-1-deterministic-and-step-2-enrichment-dev-only-2026-10-06) | [`enrich_premises.py`](../scripts/enrich_premises.py), [`run_battery.py`](../scripts/run_battery.py) | `results/ablate-*.json`, [`enrichment/`](../enrichment) |
| Defaults confirmed on dev | [Defaults](measurements.md#defaults-confirmed-on-dev-and-an-mps-fix-2026-10-06) | [`run_battery.py`](../scripts/run_battery.py) | `results/dev-default-*.json` |
| Sealed held-out battery, run once | [Held-out](measurements.md#held-out--sealed-heldout-2026-10-06-run-once-per-detector-2026-10-06) | [`run_battery.py`](../scripts/run_battery.py) | `results/heldout-2026-10-06-*.json` |
| Real answers from another system, anonymised | [Live answers](measurements.md#real-answers-from-legal-rag-audit-live-runs-anonymised-2026-10-06) | [`score_audit_live.py`](../scripts/score_audit_live.py) | `results/audit-live-*.json` |
| Engine and Hugging Face backend on a Mac | [M3](measurements.md#m3-live-run-engine--hf-backend-on-the-mac-2026-10-06-development-only) | [`live_demo.py`](../scripts/live_demo.py) | `results/live-demo-*.json` |
| Date-filtered NLI candidates, dev only | [Date filter](measurements.md#date-filtered-nli-candidates-2026-10-06-dev-only-held-out-sealed-and-not-re-run) | [`run_battery.py`](../scripts/run_battery.py) | `results/*-datefilter*.json` |
| SGLang and Qwen 2.5 7B on one L4 | [M4](measurements.md#m4-spike-sglang--qwen-25-7b-on-one-modal-l4-2026-10-06) | [`modal_m4.py`](../scripts/modal_m4.py), [`m4_spike.py`](../scripts/m4_spike.py) | [`m4-sglang.json`](../results/m4-sglang.json) |
| Rollback round trip profiled | [Profile](measurements.md#rollback-round-trip-on-the-l4-profiled-2026-10-06) | [`m4_profile.py`](../scripts/m4_profile.py) | [`m4-profile.json`](../results/m4-profile.json) |

## The 2x2 grid and the DeBERTa auditor

| Stop | Question | Method | Figures | Scripts | Results |
|---|---|---|---|---|---|
| Grid | Does rollback per sentence beat a full retry, on Gemini and on Qwen 2.5 7B? | [GRID](GRID.md#cells) | [figures](measurements.md#2x2-grid-results-2026-10-07-method-in-docsgridmd) | [`grid_prompts.py`](../scripts/grid_prompts.py), [`grid_cells.py`](../scripts/grid_cells.py), [`grid_qwen.py`](../scripts/grid_qwen.py), [`grid_gemini.py`](../scripts/grid_gemini.py), [`grid_judge.py`](../scripts/grid_judge.py), [`grid_score.py`](../scripts/grid_score.py), [`grid_report.py`](../scripts/grid_report.py) | [`results/grid/`](../results/grid) `4A` to `4D`, `judge.jsonl`, `report.json` |
| 27 | Does inserting the provision at the cut make the retry pass? | [method](GRID.md#stop-27-the-injection-ab-method-fixed-2026-10-07-before-the-test-run) | [figures](measurements.md#injection-ab-stop-27-2026-10-07-method-in-docsgridmd) | [`grid_inject.py`](../scripts/grid_inject.py), [`grid_qwen.py`](../scripts/grid_qwen.py) | [`results/grid/`](../results/grid) `4B-inject.jsonl`, `inject_ab.json` |
| 29 | Where should the provision go, and what does it do to attention? | [method](GRID.md#stop-29-where-the-provision-goes-and-what-it-does-to-attention-method-fixed-2026-10-07-before-any-run) | [figures](measurements.md#placement-and-attention-replay-stop-29-2026-10-07-method-in-docsgridmd) | [`replay_states.py`](../scripts/replay_states.py), [`replay_run.py`](../scripts/replay_run.py), [`attention_replay.py`](../scripts/attention_replay.py), [`replay_report.py`](../scripts/replay_report.py) | [`results/grid/replay/`](../results/grid/replay), `replay_states.json` |
| 30 | Injection with the question restated, and the router as the abstention gate | [method](GRID.md#stop-30-injection-v2-method-fixed-2026-10-07-before-any-run) | [figures](measurements.md#injection-v2-stop-30-2026-10-07-and-2026-10-08-method-in-docsgridmd) | [`grid_routes.py`](../scripts/grid_routes.py), [`grid_qwen.py`](../scripts/grid_qwen.py) | [`results/grid/`](../results/grid) `4B-inject-v2.jsonl`, [`dev/`](../results/grid/dev) |
| 36 | Were the rollbacks and retries right, by hand? | [method](GRID.md#stop-36-human-check-of-rollbacks-and-retries-method-fixed-2026-10-08-before-any-label-or-test-judge-call) | [figures](measurements.md#rollbacks-and-retries-labelled-stop-36-2026-10-08-method-in-docsgridmd) | [`rollback_review.py`](../scripts/rollback_review.py) | [`results/grid/rollback/`](../results/grid/rollback) |
| 37 | Does the loop help on software questions, graded by hand? | [method](GRID.md#stop-37-the-loop-on-software-questions-graded-by-you-method-fixed-2026-10-08-before-the-run) | [figures](measurements.md#software-battery-graded-by-you-stop-37-2026-10-08-method-in-docsgridmd) | [`software_battery.py`](../scripts/software_battery.py), [`software_review.py`](../scripts/software_review.py), [`modal_m4.py`](../scripts/modal_m4.py) | [`results/software/`](../results/software) |
| 40 | Does the question help the entailment check? | [method](GRID.md#stop-40-the-question-in-the-entailment-check-offline-method-fixed-2026-10-08-before-any-scoring) | [figures](measurements.md#the-question-in-the-entailment-check-stop-40-2026-10-08-method-in-docsgridmd) | [`nli_context.py`](../scripts/nli_context.py) | [`results/nli_context/`](../results/nli_context) |
| 41 | Do derived facts help the entailment check? | [method](GRID.md#stop-41-derived-facts-for-the-entailment-check-method-fixed-2026-10-09-before-any-scoring) | [figures](measurements.md#derived-facts-for-the-entailment-check-stop-41-2026-10-09-method-in-docsgridmd) | [`normalise_sources.py`](../scripts/normalise_sources.py), [`nli_normalised.py`](../scripts/nli_normalised.py), [`modal_normalise.py`](../scripts/modal_normalise.py) | [`results/normalise/`](../results/normalise) |

## The LLM judge

| Stop | Question | Method | Figures | Scripts | Results |
|---|---|---|---|---|---|
| 42 | Can a reasoning LLM replace DeBERTa as the auditor's judge? | [method](GRID.md#stop-42-a-reasoning-llm-as-the-auditors-judge-method-fixed-2026-10-09-before-any-judge-call) | [figures](measurements.md#a-reasoning-llm-as-the-auditors-judge-stop-42-2026-10-09-method-in-docsgridmd) | [`auditor_judge.py`](../scripts/auditor_judge.py), [`modal_auditor_judge.py`](../scripts/modal_auditor_judge.py) | [`results/auditor_judge/`](../results/auditor_judge) |
| 43 to 47 | A fast student of a frontier teacher, and the first fresh test (358 sentences, graded by hand) | [method](GRID.md#stops-43-to-47-a-fast-student-of-a-frontier-teacher-method-fixed-2026-10-09-before-any-run) | [figures](measurements.md#a-distilled-judge-and-the-fresh-test-stops-43-to-47-2026-10-09-and-2026-10-10-method-in-docsgridmd) | [`fresh_battery.py`](../scripts/fresh_battery.py), [`teachers.py`](../scripts/teachers.py), [`check44.py`](../scripts/check44.py), [`distill_data.py`](../scripts/distill_data.py), [`page_sections.py`](../scripts/page_sections.py), [`check46.py`](../scripts/check46.py), [`fresh_eval.py`](../scripts/fresh_eval.py), [`fresh_report.py`](../scripts/fresh_report.py), [`fresh_posthoc.py`](../scripts/fresh_posthoc.py) | [`results/distill/`](../results/distill), [`results/fresh/`](../results/fresh), [`batteries/fresh/`](../batteries/fresh) |
| 48, 49 | Does the model's own attention or likelihood flag a wrong sentence? | [method](GRID.md#stops-48-and-49-an-awareness-signal-for-the-auditor-method-fixed-2026-10-10-before-any-run) | [figures](measurements.md#an-awareness-signal-for-the-auditor-stop-48-2026-10-10-method-in-docsgridmd) | [`awareness.py`](../scripts/awareness.py), [`awareness_replay.py`](../scripts/awareness_replay.py) | [`results/awareness/`](../results/awareness) |
| 50 | Gemini 3.1 Pro as a per-clause judge | [method](GRID.md#stop-50-gemini-31-pro-as-a-per-clause-judge-method-fixed-2026-10-10-before-any-call) | [figures](measurements.md#gemini-31-pro-as-a-per-clause-judge-stop-50-2026-10-10-method-in-docsgridmd) | [`teacher_pro.py`](../scripts/teacher_pro.py) | [`results/teacher_pro/`](../results/teacher_pro) |
| 51 | Opus 5.5 as a per-clause judge | [method](GRID.md#stop-51-opus-55-as-a-per-clause-judge-on-the-fresh-test-method-fixed-2026-10-10-before-any-call) | [figures](measurements.md#opus-55-as-a-per-clause-judge-stop-51-2026-10-10-method-in-docsgridmd) | [`teacher_opus.py`](../scripts/teacher_opus.py) | [`results/teacher_opus/`](../results/teacher_opus) |
| 52, 53 | The claim check's false rollbacks, and a judge shown the question | [method](GRID.md#stops-52-and-53-the-claim-checks-false-rollbacks-and-a-judge-shown-the-question-method-fixed-2026-10-11-before-any-call) | [figures](measurements.md#the-claim-check-behind-an-llm-judge-and-the-judges-view-stops-52-and-53-2026-10-11-method-in-docsgridmd) | [`fresh_arms.py`](../scripts/fresh_arms.py), [`fresh_errors.py`](../scripts/fresh_errors.py) | [`results/fresh_arms/`](../results/fresh_arms) `report.json`, `errors.json` |
| 54 | Where the judges fail, and notes on applying the labels | [method](GRID.md#stop-54-notes-on-applying-the-labels-qwen-27b-method-fixed-2026-10-11-before-any-call) | [figures](measurements.md#where-the-judges-fail-and-notes-on-applying-the-labels-stop-54-2026-10-11-method-in-docsgridmd) | [`fresh_arms.py`](../scripts/fresh_arms.py) | [`results/fresh_arms/`](../results/fresh_arms) |
| 55 | Qwen 27B as the judge at 4 bits | [method](GRID.md#stop-55-qwen-27b-at-4-bits-method-fixed-2026-10-11-before-any-run) | [figures](measurements.md#qwen-27b-at-4-bits-stop-55-2026-10-11-method-in-docsgridmd) | [`fresh_arms.py`](../scripts/fresh_arms.py), [`modal_distill.py`](../scripts/modal_distill.py) | [`results/fresh_arms/quant.json`](../results/fresh_arms/quant.json) |
| 56 | A second fresh test (151 sentences, graded by hand) | [method](GRID.md#stop-56-a-second-fresh-test-method-fixed-2026-10-11-before-any-source-is-drawn) | [figures](measurements.md#the-second-fresh-test-stop-56-2026-10-11-method-in-docsgridmd) | [`fresh_set.py`](../scripts/fresh_set.py), [`fresh_battery.py`](../scripts/fresh_battery.py), [`fresh_arms.py`](../scripts/fresh_arms.py) | [`results/fresh2/`](../results/fresh2), [`results/fresh2_arms/`](../results/fresh2_arms), [`batteries/fresh2/`](../batteries/fresh2) |
| 57 | Qwen 27B as generator and judge, and Opus 5.5 as a grader | [method](GRID.md#stop-57-qwen-27b-as-generator-and-judge-method-fixed-2026-10-11-before-any-run) | [figures](measurements.md#qwen-27b-as-generator-and-judge-stop-57-2026-10-11-method-in-docsgridmd) | [`self_judge.py`](../scripts/self_judge.py), [`fresh_grader.py`](../scripts/fresh_grader.py) | [`results/fresh2-q27/`](../results/fresh2-q27), [`results/fresh2-q27_arms/`](../results/fresh2-q27_arms) |
| 58 | A refusal rule on the judge's side | [method](GRID.md#stop-58-a-refusal-rule-on-the-judges-side-method-fixed-2026-10-11-before-any-run) | [figures](measurements.md#a-refusal-rule-on-the-judges-side-stop-58-2026-10-11-method-in-docsgridmd) | [`refusal_rule.py`](../scripts/refusal_rule.py) | [`refusal.json`](../results/fresh2-q27_arms/refusal.json) |
| 59 | The judge inside the live loop | [method](GRID.md#stop-59-the-judge-inside-the-loop-method-fixed-2026-10-12-before-any-run) | [figures](measurements.md#the-judge-inside-the-loop-stop-59-2026-10-12-method-in-docsgridmd) | [`live_loop.py`](../scripts/live_loop.py), [`live_report.py`](../scripts/live_report.py) | [`results/fresh2-live/`](../results/fresh2-live), [`results/fresh2-live_arms/`](../results/fresh2-live_arms) |
| 60 | DeBERTa on the second fresh test | [method](GRID.md#stop-60-deberta-v0-on-the-second-test-method-fixed-2026-10-12-before-any-run) | [figures](measurements.md#deberta-v0-on-the-second-fresh-test-stop-60-2026-10-12-method-in-docsgridmd) | [`fresh_arms.py`](../scripts/fresh_arms.py) | [`v0.json`](../results/fresh2_arms/v0.json), [`results/fresh2/scores/`](../results/fresh2/scores) |
| 61 | A judge reply without the reason | [method](GRID.md#stop-61-a-judge-reply-without-the-reason-method-fixed-2026-10-12-before-any-run) | [figures](measurements.md#a-judge-reply-without-the-reason-stop-61-2026-10-12-method-in-docsgridmd) | [`fresh_arms.py`](../scripts/fresh_arms.py), [`live_loop.py`](../scripts/live_loop.py) | `short.json` in [`fresh_arms/`](../results/fresh_arms) and [`fresh2_arms/`](../results/fresh2_arms) |
| 62 | Two smaller judges, untrained | [method](GRID.md#stop-62-two-smaller-judges-untrained-method-fixed-2026-10-12-before-any-run) | [figures](measurements.md#two-smaller-judges-untrained-stop-62-2026-10-12-method-in-docsgridmd) | [`fresh_arms.py`](../scripts/fresh_arms.py) | `small.json` in [`fresh_arms/`](../results/fresh_arms) and [`fresh2_arms/`](../results/fresh2_arms) |
| 63 | Smaller judges trained on Qwen 27B's labels | [method](GRID.md#stop-63-two-smaller-judges-trained-on-qwen-27bs-labels-method-fixed-2026-10-12-before-any-run) | [figures](measurements.md#a-1b-judge-trained-on-the-qwen-27bs-labels-stop-63-2026-10-12-method-in-docsgridmd) | [`students.py`](../scripts/students.py), [`modal_distill.py`](../scripts/modal_distill.py) | [`results/distill/students/`](../results/distill/students) |
| 64 | The 1B judge trained on more data | [method](GRID.md#stop-64-the-1b-judge-trained-on-more-data-method-fixed-2026-10-12-before-any-run) | [figures](measurements.md#the-1b-judge-trained-on-more-data-stop-64-2026-10-12-method-in-docsgridmd) | [`pool2.py`](../scripts/pool2.py), [`students.py`](../scripts/students.py) | [`results/distill/students/`](../results/distill/students), [adapters](https://huggingface.co/azterizm/minicpm5-1b-clause-judge) |
| 65 | The live loop with the short reply | [method](GRID.md#stop-65-the-live-loop-with-the-short-reply-method-fixed-2026-10-12-before-any-run) | [figures](measurements.md#the-loop-with-the-short-judge-reply-stop-65-2026-10-12-method-in-docsgridmd) | [`live_loop.py`](../scripts/live_loop.py), [`live_report.py`](../scripts/live_report.py), [`fresh_grader.py`](../scripts/fresh_grader.py) | [`results/fresh2-short-live/`](../results/fresh2-short-live), [`results/fresh2-short-live_arms/`](../results/fresh2-short-live_arms) |
| 66 | Two hosted decision APIs as the judge | [method](GRID.md#stop-66-two-hosted-decision-apis-as-the-judge-method-fixed-2026-10-13-before-any-run) | [figures](measurements.md#two-hosted-decision-apis-as-the-judge-stop-66-2026-10-13-method-in-docsgridmd) | [`decisions.py`](../scripts/decisions.py) | `decisions.json` in [`fresh_arms/`](../results/fresh_arms) and [`fresh2_arms/`](../results/fresh2_arms), [`results/decisions/`](../results/decisions) |
| 73 | ConSens (Iris.ai) per sentence, Llama 3.2 1B, against the judge | [method](GRID.md#stop-73-consens-per-sentence-beside-the-judge-method-fixed-2026-10-21-before-any-run) | [figures](measurements.md#consens-per-sentence-stop-73-2026-10-21-method-in-docsgridmd) | [`consens.py`](../scripts/consens.py), [`modal_distill.py`](../scripts/modal_distill.py) | [`results/fresh2_arms/consens.json`](../results/fresh2_arms/consens.json), [`results/fresh_arms/consens.json`](../results/fresh_arms/consens.json) |

## The loop at scale

| Stop | Question | Method | Figures | Scripts | Results |
|---|---|---|---|---|---|
| 67 | Does the retry repeat the error, and does editing the KV cache help? | [method](GRID.md#stop-67-does-the-retry-repeat-the-error-and-does-editing-the-kv-cache-help-method-fixed-2026-10-14-before-any-run) | [figures](measurements.md#retries-after-a-real-error-and-the-kv-cache-edit-stop-67-2026-10-14-method-in-docsgridmd) | [`retry_states.py`](../scripts/retry_states.py), [`kv_retry.py`](../scripts/kv_retry.py), [`retry_grader.py`](../scripts/retry_grader.py), [`retry_report.py`](../scripts/retry_report.py) | [`results/retry/`](../results/retry) |
| 68 | The live loop closed-book on 240 questions, three generators. The 120 questions beyond the fresh tests come from the stop 64 pool, which stays local. | [method](GRID.md#stop-68-the-plain-text-passage-in-the-live-loop-three-generators-method-fixed-2026-10-14-before-any-run) | [figures](measurements.md#the-plain-text-passage-in-the-live-loop-three-generators-stop-68-2026-10-14-method-in-docsgridmd) | [`live68.py`](../scripts/live68.py), [`live_loop.py`](../scripts/live_loop.py), [`live68_grade.py`](../scripts/live68_grade.py) | [`results/live68/`](../results/live68), [`live68_report.json`](../results/live68_report.json) |
| 69 | Does the judge re-asked, or a second judge, catch what the loop kept? | [method](GRID.md#stop-69-does-the-judge-agreeing-with-itself-or-a-second-judge-catch-the-wrong-sentences-the-loop-kept-method-fixed-2026-10-15-before-any-call) | [figures](measurements.md#the-judge-re-asked-and-a-second-judge-on-the-loops-committed-sentences-stop-69-2026-10-15-method-in-docsgridmd) | [`judge69.py`](../scripts/judge69.py) | [`results/judge69/`](../results/judge69) |
| 70 | The live loop with the source in the prompt | [method](GRID.md#stop-70-the-live-loop-with-the-source-in-the-prompt-for-generators-that-err-method-fixed-2026-10-15-before-any-run) | [figures](measurements.md#the-live-loop-with-the-source-in-the-prompt-stop-70-2026-10-15-method-in-docsgridmd) | [`live70.py`](../scripts/live70.py), [`live_loop.py`](../scripts/live_loop.py), [`live68_grade.py`](../scripts/live68_grade.py) | [`results/live70/`](../results/live70), [`live70_report.json`](../results/live70_report.json) |
| 71 | The 7B loop against Gemini 3.8 Flash and Claude Opus 4.6 | [method](GRID.md#stop-71-the-loop-with-a-7b-generator-against-two-frontier-models-method-fixed-2026-10-15-before-any-call) | [figures](measurements.md#the-7b-loop-against-two-frontier-models-stop-71-2026-10-16-method-in-docsgridmd) | [`sota71.py`](../scripts/sota71.py) | [`sota71_report.json`](../results/sota71_report.json) |
| 72 | The 27B loop against the same frontier models | [method](GRID.md#stop-72-the-loop-with-the-27b-as-generator-against-the-frontier-models-method-fixed-2026-10-16-before-any-run) | [figures](measurements.md#the-27b-loop-against-two-frontier-models-stop-72-2026-10-16-method-in-docsgridmd) | [`live72.py`](../scripts/live72.py) | [`live72_report.json`](../results/live72_report.json) |

## The claim check

| Stop | Question | Method | Figures | Scripts | Results |
|---|---|---|---|---|---|
| 75 | French figure formats, with every English claim read as before | [method](GRID.md#stop-75-french-figure-formats-in-the-claim-check-method-fixed-2026-10-21-before-the-code) | [figures](measurements.md#french-figure-formats-stop-75-2026-10-21-method-in-docsgridmd) | [`claims75.py`](../scripts/claims75.py) | [`results/claims75.json`](../results/claims75.json), [`results/claims75_corpus.json`](../results/claims75_corpus.json), [`results/claims75_grades.csv`](../results/claims75_grades.csv), [`results/claims75_narrow.json`](../results/claims75_narrow.json), [`results/claims75_corpus76.json`](../results/claims75_corpus76.json), [`results/claims75_grades76.csv`](../results/claims75_grades76.csv), [`results/claims75_narrow2.json`](../results/claims75_narrow2.json), [`results/claims75_corpus77.json`](../results/claims75_corpus77.json), [`results/claims75_grades77.csv`](../results/claims75_grades77.csv) |

## Shared scripts

These are used by many stops.

| Script | Role |
|---|---|
| [`auditor_judge.py`](../scripts/auditor_judge.py) | The LLM judge as an entailment scorer (`JudgeScorer`) and the replay of the auditor's verdicts. |
| [`live_loop.py`](../scripts/live_loop.py) | The in-flight loop with the LLM judge, as run in stops 59 to 72. |
| [`fresh_arms.py`](../scripts/fresh_arms.py) | Runs and scores the judges on both fresh tests, stops 52 to 66. |
| [`fresh_grader.py`](../scripts/fresh_grader.py) | Opus 5.5 grades a sheet as the hand grader did. |
| [`grid_cells.py`](../scripts/grid_cells.py) | The remediation loops of the grid, for any generator. |
| [`modal_distill.py`](../scripts/modal_distill.py) | Modal entrypoints from stop 43 on: generators, judge servers and training. |
| [`modal_ledger.py`](../scripts/modal_ledger.py) | Modal spend at list prices, with a hard stop. |
| [`router.py`](../scripts/router.py) | Calls to hosted models, with retries and a spend ledger. |
| [`check_wheel.py`](../scripts/check_wheel.py) | Checks the built wheel ships code only. Used in CI, not in the research. |

## Batteries

| Folder | Contents | Used by |
|---|---|---|
| [`batteries/verifier/`](../batteries/verifier) | The detector batteries: dev (271 rows) and held-out (346 rows, sealed). Sentences with labels against real provisions. | Before the grid |
| [`batteries/router/`](../batteries/router) | Questions copied unchanged from `legal-rag-router`, with its seals. | Grid prompts, verifier batteries |
| [`batteries/grid/`](../batteries/grid) | The grid's prompts, and the router's route for each. | Grid, stops 27 to 36 |
| [`batteries/software/`](../batteries/software) | 40 software questions with quoted premises. | Stop 37 |
| [`batteries/fresh/`](../batteries/fresh) | 80 questions for the first fresh test. | Stop 43 on |
| [`batteries/fresh2/`](../batteries/fresh2) | 40 questions for the second fresh test. | Stop 56 on |
