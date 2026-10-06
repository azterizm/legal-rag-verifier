# Verifier detector batteries (plan R1)

The detector (claim check + NLI) is shared by every cell of the 2×2 grid (vault 07 §5), so its own accuracy is
measured, not assumed. Each row is one sentence an answer might contain, judged against one real premise.

## Files

| File | What |
|---|---|
| `dev_rows.toml`, `heldout_rows.toml` | Hand-written rows (source of truth). |
| `build_dev.py [--split dev\|heldout]` | Builds `dev.jsonl` / `heldout_draft.jsonl`: checks each excerpt is verbatim in its premise, fills `source_url`. Never runs the verifier. |
| `premises.py` | Builds a row's premise (corpus provisions, an anchor version, or an anchor timeline); shared with `scripts/run_battery.py`. |
| `anchors.toml`, `clml.py` | Point-in-time anchors and the CLML → records converter for their dated versions (`anchors_xml/`, git-ignored). |
| `review_sheet.py` → `dev_review.md`, `heldout_review.md` | Rows grouped by premise, for label review. |

## Method

- **Prompts (R11):** each row's query and premise come from the router's concept battery **`dev`** split
  (`batteries/router/concept/uk.jsonl`, seal `concept-seal-2026-09-29`): the query plus its gold provisions,
  assembled into premise windows by `Premise.from_records` from the real corpus (R9, R10). Two rows use a
  citation-form query from the router's batteries (`uk-informal-0009` "tulrca s.188",
  `uk-false_abstention-0019` "Companies Act 2006 Pt 10 Ch 2") over the same dev-split premise. No prompt from the
  `test` split is used; the held-out battery will use the `test` split only.
- **Rows** were written against the provision text, as an answer would phrase them, independently of the
  checker's patterns (paraphrase, number words, "magistrate" for "justice of the peace", ordinal dates, cross-section
  reasoning). The builder never runs the verifier, and the verifier has **not** been run on these rows.
- **Labels** are judged against the premise, not the law at large: a sentence true in law but not supported by the
  premise (e.g. the s.20 OAPA penalty, whose text is repealed in the premise) is `unsupported_plausible` →
  ROLLBACK, with a note.
- **Excerpts** are short verbatim quotes of the provision the label relies on, each with its coordinate and
  `source_url` (OGL v3.0, see `NOTICE`).

- **Anchors** (`anchors.toml`) come from legal-rag-audit's point-in-time anchors (`external/anchors.py`): the
  same provision at two dates, with a figure stated in one version only. Each anchor gives three premises — each
  dated version (official CLML in `anchors_xml/`, supplied 2026-10-05) with a fact window for its validity range,
  and a *timeline* (current text from the corpus plus every dated version as a fact window, the shape a temporal
  resolver returns). Queries are the anchor questions. era-124 is excluded (s.124 is in the tests and the demo).
- **Mode C / Mode A** rows come from rag-security-probes (`rag_probes_mode_c.jsonl`, `rag_probes.jsonl`,
  `schemas/no_upload_examples.json`): the probe query, the real governing provision from the corpus as premise,
  the probe's indicative bad outputs or worked fabrication (ROLLBACK), the correction (EMIT) and a grounded
  answer (EMIT). FAB-004 is not used (no governing provision to serve as premise). FAB-002's worked abstention
  cites HA 1996 s.81 for a commercial tenant, which s.81(4)(a) excludes; it is labelled ROLLBACK here.
- **Split by provision** (stop 5): dev = concept `dev` split, anchors era-227 and era-186, Mode C CHIM-001,
  CHIM-002, OOB-001, Mode A FAB-001–003; held-out = anchors ca-465 and ca-382, Mode C CHIM-003, DEVOLV-001,
  REPEAL-001, Mode A FAB-005–006 (and, later, rows from the concept `test` split).

## Classes

| Class | Expected | Meaning |
|---|---|---|
| `grounded_paraphrase` | EMIT | Restates the premise correctly in other words. Headline: its false-rollback rate. |
| `connective` | EMIT | Prose with no claim ("The position is as follows:"). |
| `wrong_figure` | ROLLBACK | A figure, date or period the premise does not state. |
| `wrong_citation` | ROLLBACK | A provision that does not exist, or a real one misattributed. |
| `wrong_instrument` | ROLLBACK | The wrong Act/SI (title or year). |
| `modal_shift` | ROLLBACK | Changes the duty: shall ↔ may, must ↔ need not. |
| `dropped_qualifier` | ROLLBACK | Drops a qualifier that changes the claim: a cap ("not exceeding"), a comparative ("the lower of"), a condition or scope. A minimum stated as the threshold ("four weeks' notice" for "not less than 4 weeks") is not dropped (stop 6). |
| `value_swap` | ROLLBACK | A figure that is in the premise, attached to the wrong limb or case. |
| `version_swap` | ROLLBACK | The figure of another version of the same provision, for the date asked about. |
| `premise_correction` | EMIT | Rejects a false premise in the query (an Act or section that does not exist, a repealed Act) and points to the real provision. Names the false premise in order to deny it. |
| `unsupported_plausible` | ROLLBACK | A plausible claim the premise does not support (or contradicts), no wrong figure needed. |

## Dev split

- 2026-10-05, stop 3: 233 rows from the concept `dev` split; labels reviewed and approved (stop 4).
- 2026-10-05, stop 6: two rows relabelled `dropped_qualifier` → `grounded_paraphrase` (minimum stated as the
  threshold; your go) and 38 rows added from the anchors and Mode C / Mode A — **⛔ awaiting your review**.
- Now 271 rows over 66 premises: grounded_paraphrase 125, connective 10, premise_correction 6, wrong_figure 24,
  wrong_citation 15, wrong_instrument 16, modal_shift 17, dropped_qualifier 9, value_swap 8, version_swap 8,
  unsupported_plausible 33.
- `dev.jsonl` sha256 `3f524a8809a80ec55089e1264e3a7da0197b0373726d8e993875f7097eb760d0`
- Not run. No threshold is calibrated until the new rows are reviewed; dev rows are not sealed.

## Held-out draft

- 346 rows over 102 premises (`heldout_draft.jsonl`, sha256 `1df51b991128c317225d58e340f89532fd9cec149adbfb8bec34d5a6a9bb05b9`):
  312 rows from 91 queries of the router's concept `test` split (stop 12), plus 34 anchor/probe rows (stop 6).
  grounded_paraphrase 179, connective 7, premise_correction 5, wrong_figure 37, wrong_citation 9,
  wrong_instrument 15, modal_shift 16, dropped_qualifier 18, value_swap 11, version_swap 8, unsupported_plausible 41.
- No provision, query or sentence is shared with dev. The six probe queries used in dev (uk-concept-0204, 0205,
  0206, 0210, 0211, 0213) are excluded from held-out (split leak found at stop 12; FAB-004/0207 has no premise).
- **Status: ⛔ awaiting your label review** (`heldout_review.md`). Then: enrichment built for its premises with the
  same pipeline → `seal.py --id heldout-…` (hashes battery, rows, anchors, enrichment layer, verifier commit) →
  `scripts/run_battery.py` runs it once; a second run of the same seal is refused.
