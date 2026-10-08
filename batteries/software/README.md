# Software battery (stop 37)

40 questions in software engineering, each with a short premise quoted from public documentation: web and HTTP
(RFCs), databases (PostgreSQL, SQLite), languages (Python, JavaScript, Go, Rust), architecture and operations
(Kubernetes, Docker, Git, Semantic Versioning, Prometheus) and AI and ML (PyTorch, scikit-learn, NumPy, pandas),
8 per area. It exists so the in-flight loop can be checked by a person in a domain they know; see
`docs/GRID.md` § Stop 37.

- `test.jsonl`: one row per question: `id`, `area`, `query`, `passages` (`heading`, `text`), `source_url`,
  `licence`, `retrieved`. Every question has its answer in the premise (`expects_abstention` is false).
- Each passage is quoted verbatim from the page at `source_url` as retrieved on 2026-10-08, except for
  whitespace, the margin bars of RFC notes, and one superscript written as `2^53` (row `sw-21`).
- The rows were chosen for the question, not for the auditor's patterns. Nothing is tuned on them: no threshold,
  prompt or detector setting changes because of this battery.
- Excerpts are short and keep their source's licence (column `licence`): IETF Trust (RFCs), PostgreSQL Licence,
  public domain (SQLite), PSF-2.0 (Python), CC BY-SA 2.5 (MDN), CC BY 4.0 (Go specification, Kubernetes),
  MIT OR Apache-2.0 (Rust book), Apache-2.0 (Docker, Prometheus), GPL-2.0 (Git), CC BY 3.0 (Semantic
  Versioning), BSD-3-Clause (PyTorch, scikit-learn, NumPy, pandas).
