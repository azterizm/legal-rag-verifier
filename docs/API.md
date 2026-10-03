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

## 3. Order of checks

1. **Grounding** over the whole premise, declared metadata and the query. Miss → rollback, NLI not run.
2. **Alignment**: top-k windows (lexical now; NLI best-entailed in M2), floor `align_ratio`, plus one hop of
   windows they cite ("subsection (1ZA)" pulls in (1ZA)).
3. **Window checks**: value swap (R3), dropped qualifier (R2, provision windows only, not facts), deontic shift.
4. **NLI** (M2): contradiction > 0.40 → rollback; entailment ≤ 0.70 → rollback if the sentence has a claim or a
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

## 5. Names to confirm (⛔)

1. **Reason codes**: `GROUNDED CONNECTIVE UNGROUNDED_FIGURE UNGROUNDED_CITATION UNGROUNDED_INSTRUMENT
   FIGURE_MISALIGNED QUALIFIER_DROPPED DEONTIC_SHIFT NLI_CONTRADICTION NLI_NOT_ENTAILED NEUTRAL_STRICT`.
   Vault 04 used `UNGROUNDED_CLAIM` and `DEONTIC_DOWNGRADE`; these are split by claim kind, and
   `DEONTIC_SHIFT` covers upgrades (may→must) as well as downgrades.
2. **`GroundedBy`**: `window premise fact metadata query` (trace field `grounded_by`).
3. **`align_ratio=0.5`**: new parameter (not in the plan), see ROADMAP stop 1.
4. **Verdict names** `EMIT` / `ROLLBACK` (as in 04).
5. **Module names**: `premise`, `verifier`, `claims`, `citations`, `deontic`, `qualifiers`, `segmenter`, `index`,
   `align`, `corpus`, `numbers`. Vault 05's imports (`nli.SentenceNLIVerifier`, `engine.InFlightGenerator`) land in M2/M3.

## 6. Known limits (measured in M2, not fixed by guesswork)

- Lexical alignment is a stand-in until the NLI head ranks windows.
- Bare numbers are claims ("3 conditions" with a premise listing (a)–(c) and no "3" is ungrounded).
- "working days" vs "days" are not distinguished; durations compare number + unit only.
- Epistemic "may" ("you may be entitled") counts as PERMISSION; "may be able / wish / want" does not.
