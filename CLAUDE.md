# Working rules for this repository

- **Progress and decisions live in `docs/ROADMAP.md`** (§S Status, stop log). Read §S first; update it
  at every stop. Never keep progress in assistant memory.
- The build follows `docs/PLAN.md` (Phase 3 plan) and the vault specs it cites (04, 05, 07 §5, 10).
  **Halt and ask** before any change to the public API, verdict/reason names, trace format or battery
  methodology beyond what the plan specifies, and at every ⛔ halt point in the roadmap.
- Git: local commits only, one per milestone. Never create a remote, push, tag a release, publish to
  PyPI, make paid API calls (Modal, Gemini) or edit the vault without an explicit go.
- English only in 0.1.0 (plan R8). Spanish follows the router's Stage C.
- `uk_scrap_data/` and `data/` are copied from `legal-rag-router`: read-only, git-ignored, never
  published. Committed battery rows quote only short excerpts, each with its coordinate and `source_url`.
- Battery rows are written independently of the checker's patterns; thresholds are calibrated on the dev
  split only; the held-out split is sealed before it runs (plan R1).
- Checks: `uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest`.
  The core wheel has zero runtime dependencies (stdlib only under `src/`, except `nli.py` and
  `backends/hf.py`, which import torch/transformers lazily behind the `[nli]` / `[hf]` extras).
