# legal-rag-verifier

Sentence-level verification for legal RAG while the model generates: a deterministic claim check
(figures, citations, instrument titles, modal verbs, qualifiers) and an NLI head, with KV-cache rollback
of a rejected sentence. Layer 4 of the Memon Systems hosted reference architecture.

Status: pre-release (Phase 3). See `docs/ROADMAP.md` for progress and `docs/API.md` for the API.

```bash
uv sync
uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest
```

Contains public sector information licensed under the Open Government Licence v3.0 (see `NOTICE`).
