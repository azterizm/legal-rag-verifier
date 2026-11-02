# Plan, phase 3 of 3: testing the judge module (this repository's part)

Status: written 2026-11-01. The free tests are written and green (stop 77); the live check awaits its go. Phase 1
is `docs/PLAN-judge-1-module.md`. The MCP server's tests are in `answer-check-mcp/docs/PLAN-judge-3-testing.md`,
and its live smoke runs during the live check below, at no extra spend.

Two kinds of test. The free ones run on every push and need no model. The live check needs a model and costs money,
so it runs once, with your go and a hard spend cap.

## Free tests (no model, no spend)

Written before the code (phase 1, step 2), each failing first.

| Test | What it proves |
|---|---|
| Prompt bytes and hashes | `SYSTEM`, `USER` and `SHORT_REPLY` match `scripts/auditor_judge.py` byte for byte, and the short prompt for a recorded unit hashes to the value in `results/fresh2_arms/short.json` (`7748f874db90…`) |
| Request body | Against a fake OpenAI-compatible server (pattern: `FakeServer` in `tests/test_sglang_backend.py`): the path, the model, the system and user messages, the sampling, `chat_template_kwargs`, and the `Authorization` header only when a key is set |
| Reply parsing | Plain JSON, fenced JSON, JSON after a reasoning block, an answer left in `reasoning_content`, and a bad label |
| Retries | A bad reply is asked again with the retry message, at most 3 times, then scored as not stated |
| Scoring | `supported` and `contradicted` land on the named passage. A passage number out of range applies to every candidate, and `not_stated` is neutral everywhere |
| Prefix | Post-hoc, each sentence's prompt carries the sentences before it, as step 0 pins. Live, the engine's committed sentences, as `LoopVerifier` |
| Secrets | A key set through `api_key_env` appears in no log line, call record, trace or error message |
| Failure | A timeout or an HTTP 500 counts as an attempt, and three failures score not stated, as measured |
| Zero dependencies | `scripts/check_wheel.py` passes on the built wheel |
| DeBERTa warning | Instantiating `SentenceNLIVerifier` emits a `UserWarning` citing `docs/VERDICT.md` and pointing to `legal_rag_verifier.judge` |

### The replay test: reproducing the published figures for free

The judge's labels for the second fresh test are stored locally in `results/fresh2/labels` (git-ignored, as they
quote statute text). A fake endpoint serves each recorded label by the hash of the prompt it was given. Running
`JudgedVerifier` over the 151 graded sentences through the package code must then give:

- every per-sentence verdict as recorded
- 90.1% accuracy (8 false rollbacks, 60 caught) for the short reply, as in `results/fresh2_arms/short.json`

A prompt whose hash is not in the recording fails the test, so any drift in the prompt or the prefix shows at once.
The same is done for the first fresh test (93.8%, 354 sentences) if its labels are stored the same way. The test
runs only where the local results exist and skips in CI, like the `full_data` tests.

## The live check (paid) ⛔

The point is to show that the released package, called against a real server, judges as the research runs did. It
does not add new evidence: the sealed tests have already been run. Pass rules are fixed in `GRID.md` before the
run, as for every stop.

### Option A, recommended: the measured judge on Modal

- Qwen3.8 27B AutoRound 4-bit at `1b9d56b4`, SGLang 0.5.21, one L40S: stop 65's server, launched with
  `scripts/modal_distill.py`.
- The package's `JudgedVerifier` with the default preset, run live over the second fresh test's 151 graded
  sentences. The grades already exist, so nothing is graded again.
- Pass rules: accuracy within 3 points of 90.1%. Label agreement with the recorded labels is reported but has no
  threshold, because sampling at temperature 0.7 varies, as stop 69's re-asks showed. Time per call at p50 near
  0.54 s.
- Spend: the `modal_ledger.py` hard stop set to $5. For scale, stop 72's 480 answers cost $1.24.
- The MCP server's live smoke runs against the same server in the same session (its own plan).

### Option B: a hosted model

- A hosted OpenAI-compatible endpoint, for a preset that needs no GPU.
- No hosted model has been measured with the short reply. Opus 5.5 (92.1%) and Gemini 3.1 Pro (90.7%) were
  measured "as tuned", which includes the two notes the module does not ship. So this run would create a new
  measured preset, not reproduce one.
- Spend: Opus 5.5 has $2.77 left in this repository's budget (`ROADMAP.md` status).
- Same pass rule shape, set before the run.

Recommendation: run A first, because it reproduces a configuration the README already quotes. B can follow if a
GPU-free preset is wanted.

## Order

1. All free tests green, including the replay test, before the release in phase 1, step 7.
2. The live check after the release, against the installed 0.5.0 wheel from PyPI in a clean environment, with your
   go on the option and the cap.
3. The result goes in `measurements.md` as stop 77 and in the `CHANGELOG`'s Evaluation section, including a
   failure if it fails.
