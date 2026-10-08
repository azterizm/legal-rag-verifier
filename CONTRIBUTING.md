# Contributing

Thank you for helping. Bug reports, sentences the verifier misjudges, and fixes are all welcome.

## Reporting a misjudged sentence

Open an issue with the sentence, the premise text it was checked against (or its coordinate),
what the verifier returned (`verdict`, `reasons`, `ungrounded`), what you expected, and the
package version. Security issues go by email, never as an issue: see [SECURITY.md](SECURITY.md).

## Making a change

```bash
uv sync
uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest
```

All four must pass. The rules the checks enforce, and a few they can't:

- **No runtime dependencies in the core.** Code under `src/` uses the standard library only,
  except `nli.py` and `backends/hf.py`, which import torch and transformers lazily behind the
  `[nli]` and `[hf]` extras.
- **Batteries are written independently of the checker's patterns.** Thresholds are calibrated
  on the dev split only.
- **Sealed batteries and results never change.** Files covered by a seal are fixed. A correction
  is a new seal and a new run, published beside the old one.
- **Methods are fixed before a run.** A new experiment gets its method in `docs/GRID.md` before
  it runs; changes after the run are recorded there with the reason.
- **No corpus data in the repository.** `data/` and the scraped source data are never committed.
  Committed battery rows quote only short excerpts, each with its coordinate and source URL.
- **Public API changes are discussed first.** The stable surface is the API in `docs/API.md`,
  the verdict and reason names and the trace format.

## Licence of contributions

The project is licensed under AGPL-3.0-only. By submitting a contribution you agree that it is
licensed under the same terms.
