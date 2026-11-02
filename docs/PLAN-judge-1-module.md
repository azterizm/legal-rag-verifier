# Plan, phase 1 of 3: the LLM judge as a package module, release 0.5.0 (stop 77)

Status: written 2026-11-01. Steps 0–6 are built in stop 77 (2026-11-02; `docs/GRID.md` stop 77). Step 7, the
release of 0.5.0, awaits your go. Every ⛔ needs your go, as `CLAUDE.md` requires for public API changes, releases
and paid calls.

Phase 2 (the judge mode in `answer-check-mcp`) is planned in that repository's `docs/PLAN-judge-2-mode.md`.
Phase 3 (testing) is split by repository: this repository's part is `docs/PLAN-judge-3-testing.md`.

## Why

The README's results come from the LLM judge: the 240-question loop (stops 68 and 70) and the judge's accuracy on
the two fresh tests (stops 47, 56 and 61). The judge lives in `scripts/` (`auditor_judge.py`, `live_loop.py`,
`fresh_arms.py`), which the wheel does not ship. Someone who installs the package gets the claim check and the
DeBERTa head, and cannot reproduce the measured configuration. Release 0.5.0 moves the judge into the package with
its measured prompt fixed, so one install and one OpenAI-compatible endpoint reproduce it.

## What exists today (read 2026-11-01)

| Piece | Where | Notes |
|---|---|---|
| Prompt | `scripts/auditor_judge.py` `SYSTEM`, `USER` (stop 42), `SHORT_REPLY` (stop 61) | The short prompt's SHA-256 recorded in `results/fresh2_arms/short.json` is `7748f874db90…` |
| Reply parsing | `auditor_judge.py` `extract_json`, `parse_reply`, `ask` | At most 3 asks, then the reply counts as not stated |
| Label to scores | `auditor_judge.py` `one_hot` | Supported or contradicted on the named passage, neutral everywhere otherwise |
| Scorer | `scripts/live_loop.py` `LiveJudge` | Implements `NLIScorer`, holds the answer so far in `prefix`, logs each call |
| Verifier wrapper | `live_loop.py` `LoopVerifier` | Sets `prefix` to the committed sentences |
| Config | `auditor_judge.py` `STRICT_FIGURES` | `VerifierConfig(neutral_policy="strict", neutral_with_grounded_claim="rollback", ungrounded_figure="judge")` |
| Endpoint call | `auditor_judge.py` `server_chat` | urllib POST to `/v1/chat/completions` with `chat_template_kwargs`, and the answer recovered from `reasoning_content` when a parser leaves it there |
| Server presets | `scripts/modal_distill.py` `JUDGES`, `QUANT` | `qwen27-nothink`, `qwen27-low`, and `qwen27-ar4` (`Vishva007/Qwen3.8-27B-W4A16-AutoRound-GPTQ` at `1b9d56b4`) |
| Post-hoc prompts | `scripts/fresh_arms.py` | Each clause's prompt is built from a stored `unit["prefix"]` |

The configuration stop 65 called "the configuration that stands": Qwen 27B AutoRound 4-bit, the short reply,
`STRICT_FIGURES`, seed 0, the stop 47 sampling. Its measured accuracy (stop 61, hand grades): 93.8% on the first
test (354 sentences) and 90.1% on the second (151), at 0.54 s per clause at p50. Stop 68 ran it in the loop: the
7B's answers holding a wrong sentence fell from 198 to 28 of 240 closed-book, with 7% refusals.

A limit to carry into every document: on answers written with the source, every judge in stop 56 scored below no
judge (88.9% against 94.4%, on 72 sentences). Stop 70 found the loop still helped the 7B with the source in the
prompt (25 answers with a wrong sentence to 13, Holm p = 0.045).

## Step 0: pin the measured configuration, before any code ⛔

Read stops 47, 56, 61, 65 and 68 in `GRID.md` and the scripts they name, and write one table as stop 77's method:

- model, revision, quantisation, server and server version
- sampling: temperature, top_p, top_k, min_p, presence_penalty, max_tokens, seed
- chat template arguments: thinking on or off, effort
- reply form (short), the retry message, and how a reply that never parses is scored
- the `VerifierConfig`
- how the answer so far is built, post-hoc (`fresh_arms.py` units) and live (`LoopVerifier`)
- each accuracy figure with the exact configuration it belongs to, and its source file

Open point for you: the default preset. The proposal is stop 65's configuration, because the live loop's results
rest on it. The FP8 model is an alternative preset: stop 55 found it matched the 4-bit model on 148 of 153 clauses.

## Design (proposed) ⛔ before code, as it adds public API

- A new module `legal_rag_verifier.judge`, stdlib only (urllib and json), so the core wheel keeps zero runtime
  dependencies (`scripts/check_wheel.py` stays green).
- The prompt constants copied byte for byte, with their SHA-256 hashes as constants. A test fails if a byte changes.
- `OpenAIChat(base_url, model, *, api_key_env=None, sampling, template_kwargs, timeout)`: one POST to
  `/v1/chat/completions`. It works against SGLang, vLLM and hosted OpenAI-compatible APIs. The key is read from the
  named environment variable at call time and never appears in a log, a trace or an error message.
- `Judge(chat, *, reply="short")`: implements `NLIScorer` (`model_id`, `score(premises, hypothesis)`), holds
  `prefix`, asks at most 3 times, scores a reply that never parses as not stated (as measured), and keeps a call log
  (label, passage, attempts, ms, tokens).
- `JudgedVerifier(Verifier)`: sets the judge's prefix. In `check_text`, the sentences before the current one,
  matching the post-hoc runs once step 0 confirms how their prefix was built. In the engine, the committed sentences,
  as `LoopVerifier` does. Its default config is the measured one.
- `PRESETS`: named measured configurations. Each holds the model id and revision, sampling, template arguments,
  reply form, prompt hash, and the figure it was measured at with its link in `measurements.md`. A judge built
  outside the presets is marked unmeasured in its call log.
- Warn on DeBERTa NLI use: instantiating `SentenceNLIVerifier` emits a `UserWarning` pointing out that empirical
  research found the DeBERTa NLI head did not improve answers (58.3%–68.7% accuracy on statute sentences, vs
  90.1%–93.8% for the LLM judge; see `docs/VERDICT.md`), recommending `legal_rag_verifier.judge` instead.

Decisions for you (⛔, recorded in `API.md` §5 "Names to confirm"):

1. Module and class names: `judge`, `OpenAIChat`, `Judge`, `JudgedVerifier`, `PRESETS`.
2. The trace. Adding judge fields to `SentenceVerdict.to_dict` changes the trace format. The alternative is the
   judge's own call log, read from `JudgedVerifier`, with no trace change. Proposal: the call log, no trace change.
3. Whether the scripts then import from the package, so there is one implementation. Proposal: yes, in the same
   stop, with their tests rerun.

Out of scope: the 1B student judge (it needs torch, so a later `[judge-local]` extra), the notes prompt (stop 54,
dropped in stop 56), anything specific to one hosted provider, and any change to verdict or reason names.

## Steps

1. Step 0's table committed to `GRID.md` as stop 77's method, before the code (method first, as for every stop).
2. Tests written first, failing. The phase 3 plan lists them: prompt bytes and hashes, the request body against a
   fake OpenAI-compatible server, reply parsing, retries, scoring, the prefix post-hoc and live, the key kept out of
   every output, the timeout path, the warning on `SentenceNLIVerifier` initialisation, and the replay of recorded labels.
3. The code in `src/legal_rag_verifier/judge.py`, and the warning in `src/legal_rag_verifier/nli.py`.
4. The scripts switched to the package code (decision 3), then `tests/test_auditor_judge.py` and
   `tests/test_live_loop.py` rerun.
5. Documents:
    - `API.md` gains a judge section.
    - The README gains "Use the judge", with the measured presets in a table, the sentence "any other model is
      unmeasured", and the with-source limit next to the figure.
    - `VERDICT.md` item 2 is updated. (Built: item 1 was updated instead, because item 2 is about the source
      turn.)
6. Checks: `uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest`, then the wheel check
   in a clean worktree.
7. Release 0.5.0 ⛔:
    - Update the version, the `CHANGELOG` (Added: the judge module. Evaluation: the replay result from phase 3),
      the citation date and `SECURITY` (supported 0.5.x).
    - Push, then tag with your go. The tag publishes to PyPI through the Trusted Publisher.

## Done when

- `pip install legal-rag-verifier==0.5.0` and one documented command against an SGLang or vLLM server running the
  default preset judge sentences with the measured configuration.
- The replay test (phase 3) gives the recorded verdicts and the recorded accuracy exactly.
- The core wheel still has zero runtime dependencies.
- Instantiating `SentenceNLIVerifier` warns the caller that the LLM judge was found to be more accurate, citing `docs/VERDICT.md`.
- The scripts and the package share one judge implementation.

## Risks

- The prefix rule differs from the post-hoc runs. That changes prompts, so their hashes stop matching the recorded
  labels. The replay test catches it.
- Hosted endpoints treat `chat_template_kwargs` and reasoning fields differently. Presets are per endpoint, and a
  hosted model is unmeasured until phase 3 measures it.
- Sampling at temperature 0.7 is not deterministic, so live labels will not match recorded ones exactly. The replay
  test uses recorded labels, and the live check in phase 3 has its own pass rule.

## Cost and time

About one day of work. No spend: every paid check is in phase 3, behind its own ⛔.
