# Fresh test (stop 43)

80 questions written for the fresh blind test of the auditor's judge; see `docs/GRID.md` § Stops 43 to 47. Nothing
is tuned on them, and they do not change after the commit that adds them.

- `software.jsonl`: 40 questions, 8 per area (web, databases, languages, architecture, ai), on documentation pages
  not used by `batteries/software/test.jsonl`. Same row format. Each passage is quoted from the page at `source_url`
  as retrieved on 2026-10-09, except for whitespace, RFC page headers and footers inside a quote, typographic quotes
  written as plain quotes, table rows written one per line with commas (`fs-13`), parameter names separated from
  their types by a space (`fs-36`, `fs-37`, `fs-39`, `fs-40`) and one formula written as `1/(1-p)` (`fs-34`).
  Licences as in `batteries/software/README.md`.
- `statutes.jsonl`: 40 questions in plain words, about 3 per area of the grid battery, each on one UK provision from
  the copied corpus that is in no other battery (grid dev and test, verifier dev and held-out, anchors). The
  premise is the provision as run, with its enrichment layer. No statute text is stored here.
