# `legal-rag-verifier` API (M1, for review ⛔)

Everything below is stdlib-only (core wheel, zero runtime deps). M2 adds `legal_rag_verifier.nli`
(`[nli]` extra), M3 adds `legal_rag_verifier.engine` and `legal_rag_verifier.backends` (`[hf]`).

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
               neutral_policy="connective" | "strict", top_k=2, align_ratio=0.5)
```

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
    steering="allow",  # or "ban"
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

`SGLangBackend.connect(url, model_path, revision=…)` (`legal_rag_verifier.backends.sglang`, stdlib HTTP client;
tokenizer via `transformers`, the `[sglang]` extra): each call resubmits `committed` as `input_ids` to `/generate`
and records `meta_info.cached_tokens` as `prefix_cache_hit_tokens`. Constraints run one token per request through
a server-side logit mask (server flag `--enable-custom-logit-processor`), then one plain request with the stops.

Trace: `backend, model, verifier{config, nli}, engine{…}, prompt_tokens, answer_tokens, sentences[{text,
outcome emitted|refused, rollbacks, recovered_by allow|ban|null, attempts[{verdict, steering, constraint,
tokens, tokens_reused, tokens_discarded, decode_calls, prefix_cache_hit_tokens, decode_latency_ns}]}],
totals{…}, stop_reason`.

`HFBackend` keeps a `DynamicCache` aligned to the last sequence decoded; `extend` keeps the longest shared prefix,
crops the rest (rollback) and re-feeds the last committed token (the cache holds keys/values, not logits).
On MPS it sets `HF_DEACTIVATE_ASYNC_LOAD=1` (transformers 5.18's threaded loader segfaults copying to MPS).

## 5. Names to confirm (⛔)

1. **Reason codes**: `GROUNDED CONNECTIVE UNGROUNDED_FIGURE UNGROUNDED_CITATION UNGROUNDED_INSTRUMENT
   FIGURE_MISALIGNED QUALIFIER_DROPPED DEONTIC_SHIFT NLI_CONTRADICTION NLI_NOT_ENTAILED NEUTRAL_STRICT`.
   Vault 04 used `UNGROUNDED_CLAIM` and `DEONTIC_DOWNGRADE`; these are split by claim kind, and
   `DEONTIC_SHIFT` covers upgrades (may→must) as well as downgrades.
2. **`GroundedBy`**: `window premise fact metadata query` (trace field `grounded_by`).
3. **`align_ratio=0.5`**: new parameter (not in the plan), see ROADMAP stop 1.
4. **Verdict names** `EMIT` / `ROLLBACK` (as in 04).
5. **Module names**: `premise`, `verifier`, `claims`, `citations`, `deontic`, `qualifiers`, `segmenter`, `index`,
   `align`, `corpus`, `numbers`. Vault 05's imports (`nli.SentenceNLIVerifier`, `engine.InFlightGenerator`) landed in M2/M3; vault 05
   constructs the generator from `model_path=…`, the plan (and this API) from a backend: vault correction pending your go.

## 6. Known limits (measured in M2, not fixed by guesswork)

- Lexical alignment is a stand-in until the NLI head ranks windows.
- Bare numbers are claims ("3 conditions" with a premise listing (a)–(c) and no "3" is ungrounded).
- "working days" vs "days" are not distinguished; durations compare number + unit only.
- Epistemic "may" ("you may be entitled") counts as PERMISSION; "may be able / wish / want" does not.
