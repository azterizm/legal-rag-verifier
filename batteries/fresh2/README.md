# Second fresh test (stop 56)

40 questions for the confirmation run of the auditor's judge; see `docs/GRID.md` § Stop 56. Nothing is tuned on
them, and they do not change after the commit that adds them.

No question is written or picked by hand. `scripts/fresh_set.py` draws the sources with seed 20261011. Gemini 3.8
Flash writes three questions per source with the stop 45 question prompt, and one is drawn with seed 20261012
(`question_index`).

- `software.jsonl`: 20 questions, each on one section of one documentation page that no battery, the first fresh
  test or the training pool uses. Sections are cut by `scripts/page_sections.py` from the page at `source_url` as
  retrieved on 2026-10-11, without selection, so a few are thin (a site menu, an RFC title page, a list of
  links). Licences as in `batteries/software/README.md`.
- `statutes.jsonl`: 20 questions, each on one UK provision from the copied corpus, one per Act, used by no battery,
  the first fresh test or the training pool. The premise is the provision as run. No statute text is stored here.

Answers, the grading sheet and its key are in `results/fresh2/` and are not committed (they quote statute text);
`results/fresh2/seal.json` keeps their sha256.
