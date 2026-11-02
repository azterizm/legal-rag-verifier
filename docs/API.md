# `legal-rag-verifier` API (M1, for review ⛔)

Everything below is stdlib-only (core wheel, zero runtime deps). M2 adds `legal_rag_verifier.nli`
(`[nli]` extra), M3 adds `legal_rag_verifier.engine` and `legal_rag_verifier.backends` (`[hf]`), stop 77 adds
`legal_rag_verifier.judge` (stdlib).

## 1. Premise

```python
from legal_rag_verifier.premise import Premise, Passage, PassageKind

Premise.from_records(rows, *, title=None, facts=(), extra_titles=())   # router data/uk rows (R10)
Premise.from_provision(text, coordinate, title, *, in_force_from=None, amended_by=None, previous_text=None)
Premise.from_text(text, *, titles=(), citations=())                    # one window per paragraph
premise.passages: tuple[Passage, ...]     # windows; Passage(text, coordinate, kind, heading)
premise.citations: frozenset[str]         # declared coordinate tails, e.g. "s124/1ZA/a"
premise.titles: tuple[str, ...]           # declared instrument titles
premise.facts                             # passages of kind FACT (linearised temporal metadata)
```

`from_records` makes one window per subsection (stem + children + `text_after`), drops repealed text, declares
every live node's coordinate. Example (ERA 1996 s.124(1ZA), real text):
`(1ZA) The amount specified in this subsection is the lower of— (a) £123,543, and (b) 52 multiplied by a week’s pay of the person concerned.`

## 2. Verifier (the shared detector, R5)

```python
from legal_rag_verifier.verifier import Verifier, VerifierConfig

v = Verifier(nli=None, config=VerifierConfig())       # nli: any NLIScorer (M2)
v.check_text(premise, text, *, query=None) -> list[SentenceVerdict]     # post-hoc (cells 4A/4D)
v.check_sentence(premise, sentence, *, query=None) -> SentenceVerdict   # in-flight, per sentence

VerifierConfig(entail_threshold=0.70, contradict_threshold=0.40,
               neutral_policy="connective" | "strict", top_k=2, align_ratio=0.5,
               neutral_with_grounded_claim="emit" | "rollback",
               ungrounded_figure="rollback" | "judge", totals="off" | "line")
```

`ungrounded_figure` (since stop 54): what happens to a sentence whose only failed claims are figures not found
in the source. `"rollback"` is the default and the behaviour of 0.1.0. With `"judge"` the entailment check
decides: the sentence is emitted only if it is entailed, and its other claims keep their checks. A citation or
an instrument that is not in the source still rolls back. The figure stays in `claims` with its reason, and
`details` names it. Without an NLI scorer `"judge"` behaves as `"rollback"`.

`totals` (since stop 76): `"off"` is the default and the behaviour of 0.3.0. With `"line"`, a money figure that
no window states is grounded when it equals two money figures of the same currency on one line of one window,
added, neither inside brackets on that line: "Price: €279.99 (was €329.99) — Shipping: €4.99" grounds €284.98 and
not €334.98. Sums across lines or windows, of three figures, and of other kinds are never grounded. `details`
names the figure ("€284.98 is the sum of two figures on one line of the source").

`SentenceVerdict`: `text, start, end, verdict (EMIT|ROLLBACK), reasons, claims: [ClaimResult], deontics,
aligned (window indices), nli: NLIResult | None, repair: Repair | None, claim_latency_ns, nli_latency_ns,
details`, plus `.ungrounded` (surface texts) and `.to_dict()` (JSON-ready).

`ClaimResult(claim, grounded_by, reason)`; `claim = Claim(kind, value, text, start, end)` with kinds
`MONEY PERCENT DATE DURATION NUMBER CITATION INSTRUMENT` and canonical values such as `GBP:68400`, `2026-04-06`,
`3:month`, `s124/1ZA/a`, `employment rights act 1996`, `si:2026/310`, `acr:ERA1996`.

## 2a. NLI head (M2, `[nli]` extra)

```python
from legal_rag_verifier.nli import SentenceNLIVerifier

nli = SentenceNLIVerifier(model_name="cross-encoder/nli-deberta-v3-small", device=None)  # cuda > mps > cpu
nli.score(premises, hypothesis) -> list[NLIProbs]      # one batch; one result per premise
nli.model_id                                           # "name@<commit>" from the local hub cache
Verifier(nli=nli)
```

Labels come from the model's `id2label`. A premise longer than the encoder budget is split into chunks (sentence
boundaries, then words); a premise's score is its most related chunk. The verifier scores each window (with its
heading: instrument, citation, section title) and each window joined with a window it cites, in one batch.

Since stop 77, `SentenceNLIVerifier(...)` emits a `UserWarning`: the DeBERTa head did not improve answers
(58.3–68.7 % accuracy on two hand-graded tests, software and UK statutes, vs 90.1–93.8 % for the LLM judge; see
`docs/VERDICT.md`). Use the judge of §2b instead.

## 2b. LLM judge (`legal_rag_verifier.judge`, stdlib)

```python
from legal_rag_verifier.judge import OpenAIChat, Judge, JudgedVerifier, Preset, PRESETS, STRICT_FIGURES

chat = OpenAIChat(base_url, model, *, api_key_env=None, sampling=None, template_kwargs=None, timeout=1800.0)
chat(messages) -> {"content", "ms", "tokens", "finish"}   # one POST to {base_url}/v1/chat/completions
judge = Judge(chat, *, reply="short" | "full")            # an NLIScorer: one call per sentence
Judge.from_preset(name, base_url, *, api_key_env=None)    # the measured PRESETS[name] on that server
judge.score(premises, hypothesis) -> list[NLIProbs]       # one-hot on the passage the reply names
judge.model_id, judge.preset, judge.calls                 # "model@revision" for a preset, else the chat's model
v = JudgedVerifier(judge, config=STRICT_FIGURES)          # a Verifier with the judge as its entailment check
v.check_text(premise, text, *, query=None) -> list[SentenceVerdict]    # post-hoc
v.check_sentence(premise, sentence, *, query=None) -> SentenceVerdict  # live (the engine's path)
v.reset()                                                 # between answers
v.calls                                                   # the judge's call records since the last reset
```

The judge takes the NLI head's place. Each sentence the claim check sends on goes to an OpenAI-compatible chat
endpoint with the candidate windows as numbered passages and the answer so far (to resolve "it" or "this" only,
not as evidence). The reply `supported`, `contradicted` or `not_stated` becomes one-hot `NLIProbs`: entailment
or contradiction 1 on the passage it names (on every candidate when the number is out of range), neutral 1
everywhere for `not_stated`.

The prompt is fixed: `SYSTEM` + `USER` (stop 42), with the reply sentence replaced by `SHORT_REPLY` (stop 61)
when `reply="short"`, the default. `RETRY` re-asks after a reply that does not parse; it names "reason" in short
mode too, as measured. `PROMPT_SHA` = sha256(`SYSTEM + USER`) =
`72ce7d0514311749ccdd1d9f4430f5beea7d8757eeb9bd73be16fe9eae0e437b`; `SHORT_SHA` = sha256 of the short template =
`7748f874db902456700c3ff64c1b4e37621e951ed0c3c65495b8b3c5911be149`. The module raises at import if either differs.
`prompt_key(user)` = sha256(`SYSTEM + "\n" + user`) is the key of one rendered prompt, not a template hash.
`user_prompt`, `short_prompt`, `parse_reply`, `extract_json` and `one_hot` are exported for the scripts.

Answer so far: `check_text` starts a fresh call log and gives each sentence every earlier sentence of the text,
rolled back or not, as measured at stop 61. `check_sentence` gives it the sentences emitted so far, and an emitted
sentence joins them. The engine has no hook for `reset()`: with `InFlightGenerator(backend, JudgedVerifier(judge))`
the caller calls it between answers. `Judge` and `JudgedVerifier` hold per-answer state (the answer so far, the
call log) and are not thread-safe: use one per worker.

`Preset(model, revision, quantisation, server, sampling, template_kwargs, reply, prompt_sha256, figure,
measurements)` is frozen, and its `sampling` and `template_kwargs` are read-only mappings; `measurements` links
into `docs/measurements.md`. `PRESETS["qwen27-ar4"]` is the only
measured configuration: `Vishva007/Qwen3.8-27B-W4A16-AutoRound-GPTQ` at
`1b9d56b428e9f841d7ad566f87660b5f47553c97` (W4A16 AutoRound, GPTQ format), SGLang 0.5.21 on one L40S, thinking
off, temperature 0.7, top_p 0.8, top_k 20, min_p 0.0, presence_penalty 1.5, max_tokens 1024, seed 0, the short
reply, under `STRICT_FIGURES`. It scored 93.8 % (332/354) and 90.1 % (136/151) on the two fresh tests (stop 61).
Any other model, endpoint, sampling, prompt or config is unmeasured, and a judge built by hand records
`preset: None`. `from_preset` does not check the server at `base_url`; its records name the preset either way.

`STRICT_FIGURES = VerifierConfig(neutral_policy="strict", neutral_with_grounded_claim="rollback",
ungrounded_figure="judge")`, the default config of `JudgedVerifier`.

Call record, one per `score`: `sha` (`prompt_key` of the prompt sent), `label` (raw, so `"error"` is kept),
`passage` (the number the reply names, 0 for none), `attempts` (1–3), `ms` (summed over the replies received),
`tokens` (summed completion tokens, `None` when the server reports none), `sentence` (0-based index in the
answer), `preset` (the preset name, `None` for a judge built by hand) and `error` (the class name of the last
exception, `None` on success). No trace change: the call log is read from `JudgedVerifier.calls`, not written
into the engine trace or `SentenceVerdict`.

Failures: one counter, at most 3 attempts in all, shared by transport failures (a timeout, a URL or HTTP error, a
redirect, a connection reset, a malformed body such as a non-JSON body or one with no choices) and replies that do
not parse. A transport failure
re-sends the same messages; a reply that does not parse is re-asked with `RETRY`. After the third failure the
label is `"error"`, scored not stated. `OpenAIChat` does not retry. Neither path was hit in the recorded runs.
Limit: a judge that cannot be reached scores every sentence not stated, so under `STRICT_FIGURES` every sentence
rolls back.

Endpoint: `OpenAIChat` raises `ValueError` unless `base_url` starts with `http://` or `https://`. It does not
follow HTTP redirects: a redirect counts as a failed attempt, so the key is never sent to another host.

Secrets: `api_key_env` names an environment variable, not a key. Its value is read at each call, stripped of
surrounding whitespace, and sent as `Authorization: Bearer` only when set and non-empty; it is never stored, and
never appears in a repr, call record, trace or error message. A value holding a control character raises
`ValueError` naming the variable, not the value. The repr of `OpenAIChat` shows `base_url`, so never put a key in
the URL.

```python
from legal_rag_verifier.judge import Judge, JudgedVerifier

# an SGLang server already serving the model
judge = Judge.from_preset("qwen27-ar4", "http://localhost:30000")
verdicts = JudgedVerifier(judge).check_text(premise, answer, query=question)
```

## 3. Order of checks

1. **Grounding** over the whole premise, declared metadata and, for figures only, the query. Miss → rollback, NLI not run.
2. **Alignment**: top-k windows (lexical now; NLI best-entailed in M2), floor `align_ratio`, plus one hop of
   windows they cite ("subsection (1ZA)" pulls in (1ZA)).
3. **Window checks**: value swap (R3), dropped qualifier (R2: caps, comparatives and conditions; not a minimum stated as the threshold; provision windows only, not facts), deontic shift.
4. **NLI** (M2): when the sentence or query names a date and the premise holds dated versions, only the versions
   in force on it (and undated windows) are candidates; windows ranked by relatedness (1 − P(neutral)); on the most related window,
   contradiction > 0.40 → rollback; entailment ≤ 0.70 → rollback if the sentence has a claim or a
   modal, else per `neutral_policy` (R7).

## 4. Repair hints (consumed by the M3 engine)

`Repair(mode="allow"|"ban", offset, candidates, rejected)`:

| Failure | Mode | Offset | Candidates |
|---|---|---|---|
| ungrounded / misaligned figure | allow | start of the figure | same-kind values in the aligned windows (e.g. `£123,543`) |
| ungrounded citation | allow | start of the citation | aligned windows' citations in the sentence's style (`section …` / `s.…`) |
| ungrounded instrument | allow | start of the title | declared premise titles |
| deontic shift | allow | start of the modal | surfaces of the aligned windows' classes (`must`/`shall`, `may`, …) |
| dropped qualifier, NLI failures, no candidate | ban | 0 | — |

## 4a. Engine (M3, `legal_rag_verifier.engine`, stdlib) and HF backend (`[hf]` extra)

```python
from legal_rag_verifier.engine import InFlightGenerator, Answer, Backend, Segment, Ban, Allow
from legal_rag_verifier.backends.hf import HFBackend

backend = HFBackend.load("unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit")  # cuda > mps > cpu
engine = InFlightGenerator(
    backend,
    Verifier(nli),
    max_rollbacks=3,  # retries per point
    max_total_rollbacks=8,
    steering="allow",  # or "ban", or "inject" (stop 27)
    inject_template=INJECT_TEMPLATE,  # inject only: how the source is written ("{source}", optional "{query}")
    inject_windows=2,
    inject_max_tokens=800,
    refusal=DEFAULT_REFUSAL,
    max_new_tokens=512,
)
answer = engine.generate_verified(query, premise)  # Answer(text, trace); .trace_json()
```

`Backend` protocol (one engine, thin adapters): `name`, `model_id`, `chat(messages) -> Tokens`,
`encode(text)`, `decode(tokens)`, and
`extend(committed, *, stop, max_new, constraint) -> Segment(tokens, text, finish_reason "stop"|"length"|"eos",
prefix_cache_hit_tokens, latency_ns)`. The tokenizer methods are there because the allow-list is built from the
backend's own tokens (plan decision 6). `Constraint = Ban(token_ids)` (first step only) `| Allow(sequences)`
(token trie; stop strings are not honoured while the span is open; lifts when a sequence completes).

Loop per sentence: `extend` to a stop (`.` `;` `\n`) → `find_boundary` confirms it (a trailing `.` peeks one
token; a false stop extends the same sentence) → `check_sentence` → commit, or roll back: **allow** keeps the
sentence up to the claim and constrains the claim span to the repair's candidates (rejected value excluded);
**ban** restarts at the sentence's first non-space token with that token banned (bans accumulate per position).
Each point gets at most `max_rollbacks` (3) retries: allow when the rejected draft has a same-type repair, ban
otherwise (so a failed allow retry whose frame is wrong is followed by a ban retry). The third retry failing, or
a retry that produces nothing → the refusal sentence, and the answer goes on to the next point; past
`max_total_rollbacks` discarded drafts the answer ends with it (`stop_reason "rollback_budget"`). A sentence's
`rollbacks` counts its discarded drafts (a refused point after three retries shows 4).
**inject** (stop 27; reverses plan decision 6 for this mode only): on a rollback the windows the verifier aligned
the rejected sentence to (at most `inject_windows`, each once per answer, cut at `inject_max_tokens`) are written
into the context with `inject_template`, and the sentence is regenerated from its start, unconstrained. The source
stays in the context (cached like any prefix) but never in the answer; with no new window, the retry is a ban.

`SGLangBackend.connect(url, model_path, revision=…)` (`legal_rag_verifier.backends.sglang`, stdlib HTTP client;
tokenizer via `transformers`, the `[sglang]` extra): each call resubmits `committed` as `input_ids` to `/generate`
and records `meta_info.cached_tokens` as `prefix_cache_hit_tokens`. Constraints run one token per request through
a server-side logit mask (server flag `--enable-custom-logit-processor`), then one plain request with the stops.
The mask (`allow`, `ban`) is built on the client by `legal_rag_verifier.backends._sglang_mask`, which imports
`torch` and `sglang`; the `[sglang]` extra installs neither, and `inject` needs neither. Without them,
`processor()` raises an `ImportError` naming three options: install them (`pip install torch sglang`); build the
mask string where they are installed, e.g. on the server, with `MaskProcessor().to_str()` and pass it as
`SGLangBackend(url, tokenizer, model_id=…, eos=…, processor=…)` (constructor only: `connect()` has no
`processor=`); or use `steering="inject"`.

Trace: `backend, model, verifier{config, nli}, engine{…}, prompt_tokens, answer_tokens, sentences[{text,
outcome emitted|refused, rollbacks, recovered_by allow|ban|inject|null, attempts[{verdict, steering, constraint,
injected{windows, tokens}|null, tokens, tokens_reused, tokens_discarded, decode_calls, prefix_cache_hit_tokens,
decode_latency_ns}]}], totals{…, recovered_by_inject, injections, tokens_injected}, stop_reason`.

`HFBackend` keeps a `DynamicCache` aligned to the last sequence decoded; `extend` keeps the longest shared prefix,
crops the rest (rollback) and re-feeds the last committed token (the cache holds keys/values, not logits).
On MPS it sets `HF_DEACTIVATE_ASYNC_LOAD=1` (transformers 5.18's threaded loader segfaults copying to MPS).

## 5. Names to confirm (⛔)

1. **Reason codes**: `GROUNDED CONNECTIVE UNGROUNDED_FIGURE UNGROUNDED_CITATION UNGROUNDED_INSTRUMENT
   FIGURE_MISALIGNED QUALIFIER_DROPPED DEONTIC_SHIFT NLI_CONTRADICTION NLI_NOT_ENTAILED NEUTRAL_STRICT`.
   Vault 04 used `UNGROUNDED_CLAIM` and `DEONTIC_DOWNGRADE`; these are split by claim kind, and
   `DEONTIC_SHIFT` covers upgrades (may→must) as well as downgrades.
2. **`GroundedBy`**: `window premise fact metadata query` (trace field `grounded_by`).
3. **`align_ratio=0.5`**: new parameter (not in the plan).
4. **Verdict names** `EMIT` / `ROLLBACK` (as in 04).
5. **Module names**: `premise`, `verifier`, `claims`, `citations`, `deontic`, `qualifiers`, `segmenter`, `index`,
   `align`, `corpus`, `numbers`. Vault 05's imports (`nli.SentenceNLIVerifier`, `engine.InFlightGenerator`) landed in M2/M3; vault 05
   constructs the generator from `model_path=…`, the plan (and this API) from a backend: vault correction pending your go.
6. **Judge names** (stop 77, confirmed at the H1 review, 2026-11-02): module `judge`; `OpenAIChat`, `Judge`,
   `JudgedVerifier`, `PRESETS`; one preset key, `"qwen27-ar4"` (the name in `modal_distill.py` and the label
   files); `Judge.from_preset`, a classmethod rather than a new top-level name. No FP8 preset.

## 6. Known limits (measured in M2, not fixed by guesswork)

- Lexical alignment is a stand-in until the NLI head ranks windows.
- Bare numbers are claims ("3 conditions" with a premise listing (a)–(c) and no "3" is ungrounded).
- "working days" vs "days" are not distinguished; durations compare number + unit only.
- Epistemic "may" ("you may be entitled") counts as PERMISSION; "may be able / wish / want" does not.
- French figure formats (stop 75): a comma before exactly 3 digits is a thousands separator, so a French
  "1,234 kg" reads as 1234, except after a lone "0" ("0,965 kWh" is 0.965); a comma before 1 or 2 digits is a decimal point, so "pages 18,19 and 20" reads
  as 18.19 and 20 (a citation, "paragraphs 18,19", is read first). A plain space groups digits only before
  a decimal comma or a currency ("5 000 mAh" is 5 and 0; a no-break space groups always). Currency codes
  are read after the number only, and only after a space: "EUR 279,99" is the bare number 279.99,
  "279,99EUR" is not money. Only "€" is read after a number; a trailing "£" or "$" is not ("279,99 £" is
  the bare number 279.99). A comma is not a decimal point in a chemical locant (primed, bracketed, or
  before a dash and a letter), but a list without a space ("Units 1,2 and 3") or glued table cells
  ("Ra-2260,04") still read as decimals. "an" after a number is a year only when no word follows it
  ("Garantie 1 an", "1 an de garantie"; not "1 an environ" or "2 An “term” is"): before the end of a
  line, ". , ; : )" or "de" / "d’", and not after a hyphen. French number words, modal verbs and
  qualifiers are not read. Measured on the corpus in stop 75.
- Totals (stop 76, `totals="line"`): the total of any one offer in the source grounds the figure, not only
  that of the shop the sentence names (prices have the same limit, an offer list being one window). A right
  total in a wrong claim ("the cheapest is Shop B at €105.98" when Shop A is cheaper) is kept. On
  legislation a window is one line, so `"line"` would ground the sum of any two amounts in a provision; it
  is off by default and was not measured there.
- Judge (§2b): with the source in the generator's prompt, the judge scored below no auditor, 88.9 % vs 94.4 % on
  the second fresh test's 72 sentences written with the source (stop 73). Seed 0 does not make labels repeatable:
  the scored requests ran 16 at a time at temperature 0.7, and stop 48 found 14 of 323 labels changed on a second
  sample of the same prompt (the FP8 model; no repeat was measured on the 4-bit preset). A judge that cannot be
  reached rolls back every sentence under `STRICT_FIGURES`.
