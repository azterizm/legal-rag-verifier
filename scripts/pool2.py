"""Stop 64: a second training pool for the 1B judge (docs/GRID.md § Stop 64).

Stop 45's code (``distill_data``) with its files, sizes, seed and page list rebound to a second
pool, and with the first pool and both fresh tests added to what a source may not overlap.
Importing this module does the rebinding; every ``distill_data`` function then works on pool 2.

  uv run python scripts/pool2.py sources     # draw the sources (pages are fetched, no model call)
  uv run python scripts/pool2.py questions   # router, Gemini 3.8 Flash
  uv run --with modal modal run scripts/modal_distill.py::pool2_answers   # Qwen 2.5 7B on an L4
  uv run python scripts/pool2.py units       # the clauses that reach the entailment check
"""

# ruff: noqa: SIM905 - the page names read better as one string per site
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "batteries/verifier"))

import distill_data as dd  # type: ignore[import-not-found]  # noqa: E402
import fresh_set  # type: ignore[import-not-found]  # noqa: E402
import page_sections  # type: ignore[import-not-found]  # noqa: E402

OUT = ROOT / "results/distill/pool2"
FIRST_STATUTES = dd.POOL_STATUTES  # the first pool's provisions, before the rebinding below
FIRST_PAGES = dict(dd.PAGES)
SEED = 20261013
N_STATUTES = 900
N_SOFTWARE = 500
PER_ACT = 30
PER_PAGE = 4

_PY = "https://docs.python.org/3/library/{}.html"
_PG = "https://www.postgresql.org/docs/17/{}.html"
_SQLITE = "https://www.sqlite.org/{}.html"
_K8S = "https://kubernetes.io/docs/concepts/{}/"
_GIT = "https://git-scm.com/docs/git-{}"
_MDN = "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/{}"
_RUST = "https://doc.rust-lang.org/book/{}.html"
_RFC = "https://www.rfc-editor.org/rfc/rfc{}"
_NUMPY = "https://numpy.org/doc/stable/reference/generated/numpy.{}.html"
_PANDAS = "https://pandas.pydata.org/docs/reference/api/pandas.{}.html"
_SKLEARN = "https://scikit-learn.org/stable/modules/generated/sklearn.{}.html"
_TORCH = "https://docs.pytorch.org/docs/2.7/generated/torch.{}.html"
_PROM = "https://prometheus.io/docs/{}/"
_SITES: dict[str, tuple[str, list[str]]] = {
    "PSF-2.0": (
        _PY,
        "os.path string typing enum dataclasses asyncio-task threading sqlite3 csv shutil tempfile "
        "random statistics math heapq bisect copy pickle urllib.parse http.client unittest decimal "
        "fractions zipfile glob".split(),
    ),
    "PostgreSQL Licence": (
        _PG,
        "sql-createtable sql-altertable sql-createview sql-grant sql-copy sql-explain sql-begin "
        "sql-commit functions-aggregate functions-string indexes-unique indexes-partial "
        "queries-with ddl-partitioning datatype-datetime datatype-json explicit-locking "
        "sql-createfunction".split(),
    ),
    "public domain": (
        _SQLITE,
        "lang_select lang_insert lang_update lang_delete lang_createview lang_createtrigger "
        "lang_transaction lang_vacuum pragma lang_corefunc lang_datefunc withoutrowid "
        "partialindex isolation".split(),
    ),
    "CC BY 4.0": (
        _K8S,
        "workloads/pods workloads/controllers/replicaset services-networking/ingress "
        "storage/persistent-volumes storage/volumes configuration/secret policy/resource-quotas "
        "scheduling-eviction/taint-and-toleration workloads/autoscaling "
        "services-networking/network-policies overview/working-with-objects/labels".split(),
    ),
    "GPL-2.0": (
        _GIT,
        "commit branch checkout log diff tag fetch pull clone add revert bisect config worktree "
        "switch restore".split(),
    ),
    "CC BY-SA 2.5": (
        _MDN,
        "Global_Objects/Array/map Global_Objects/Array/reduce Global_Objects/Array/filter "
        "Global_Objects/String/replace Global_Objects/Object/assign Global_Objects/JSON/stringify "
        "Global_Objects/JSON/parse Global_Objects/Date Statements/async_function "
        "Operators/Optional_chaining Global_Objects/Promise/all Global_Objects/Number/toFixed "
        "Global_Objects/parseInt".split(),
    ),
    "MIT OR Apache-2.0": (
        _RUST,
        "ch05-01-defining-structs ch09-02-recoverable-errors-with-result ch10-01-syntax "
        "ch13-01-closures ch15-01-box ch16-01-threads ch04-01-what-is-ownership ch08-01-vectors "
        "ch08-03-hash-maps".split(),
    ),
    "IETF Trust (BCP 78), excerpt": (_RFC, "9113 8288 6238 9562 3986 7636 8628 6797 8941".split()),
    "BSD-3-Clause": (
        "{}",
        [
            *(
                _NUMPY.format(x)
                for x in "mean sum reshape concatenate argsort where dot zeros clip percentile "
                "unique".split()
            ),
            *(
                _PANDAS.format(x)
                for x in "DataFrame.fillna DataFrame.dropna DataFrame.pivot_table read_csv "
                "DataFrame.apply DataFrame.join concat DataFrame.rolling to_datetime "
                "DataFrame.astype".split()
            ),
            *(
                _SKLEARN.format(x)
                for x in "ensemble.GradientBoostingClassifier cluster.KMeans decomposition.PCA "
                "pipeline.Pipeline metrics.f1_score metrics.roc_auc_score "
                "preprocessing.OneHotEncoder linear_model.Ridge neighbors.KNeighborsClassifier "
                "tree.DecisionTreeClassifier preprocessing.MinMaxScaler".split()
            ),
            *(
                _TORCH.format(x)
                for x in "nn.Conv2d nn.BatchNorm2d optim.Adam optim.SGD nn.Embedding "
                "nn.MultiheadAttention nn.functional.softmax cat nn.GRU "
                "optim.lr_scheduler.StepLR".split()
            ),
        ],
    ),
    "Apache-2.0": (
        _PROM,
        "prometheus/latest/querying/basics concepts/data_model concepts/jobs_instances "
        "practices/naming practices/histograms prometheus/latest/configuration/recording_rules "
        "prometheus/latest/configuration/alerting_rules".split(),
    ),
}
# Fixed before any fetch. A page already used by a battery, a fresh test or the first pool is
# dropped by ``software_pool``; a page that cannot be fetched is skipped.
PAGES = {
    template.format(name): licence
    for licence, (template, names) in _SITES.items()
    for name in names
}


_SECTIONS = page_sections.sections


def _wrapped(url: str) -> list[tuple[str, str]]:
    """A page that cannot be fetched gives no section and is skipped."""
    try:
        return list(_SECTIONS(url))
    except OSError as exc:
        print(f"skipped {url}: {exc!r}"[:160], flush=True)
        return []


def _taken_coordinates(first: Any = dd.used_coordinates) -> set[str]:
    """Stop 45's exclusions, the first pool and the second fresh test."""
    lines = FIRST_STATUTES.read_text(encoding="utf-8").splitlines()
    out = set(first()) | {json.loads(x)["premise"][0] for x in lines}
    second = ROOT / "batteries/fresh2/statutes.jsonl"
    out |= {
        c for x in second.read_text(encoding="utf-8").splitlines() for c in json.loads(x)["premise"]
    }
    return out


def _taken_pages(first: Any = dd.used_pages) -> set[str]:
    second = ROOT / "batteries/fresh2/software.jsonl"
    lines = second.read_text(encoding="utf-8").splitlines()
    out = set(first()) | {json.loads(x)["source_url"].split("#")[0] for x in lines}
    return out | {u.split("#")[0] for u in (*FIRST_PAGES, *fresh_set.PAGES)}


def activate() -> None:
    """Point ``distill_data`` at the second pool."""
    dd.OUT = OUT
    dd.POOL = OUT / "pool.jsonl"
    dd.POOL_STATUTES = OUT / "pool_statutes.jsonl"
    dd.QUESTIONS = OUT / "questions.jsonl"
    dd.ANSWERS = OUT / "answers.jsonl"
    dd.UNITS = OUT / "units.jsonl"
    dd.SEED, dd.N_STATUTES, dd.N_SOFTWARE = SEED, N_STATUTES, N_SOFTWARE
    dd.PER_ACT, dd.PER_PAGE, dd.PAGES = PER_ACT, PER_PAGE, PAGES
    dd.used_coordinates = _taken_coordinates
    dd.used_pages = _taken_pages
    page_sections.sections = _wrapped


def build() -> dict[str, Any]:
    """Draw the sources. Ids are prefixed so no id of the first pool is reused."""
    OUT.mkdir(parents=True, exist_ok=True)
    pool = dd.build_pool()
    renamed = [{**p, "id": "q" + p["id"]} for p in pool]
    dd._write_jsonl(dd.POOL, renamed)
    statutes = [{"id": p["id"], "premise": p["premise"]} for p in renamed if p["domain"] == "legal"]
    dd._write_jsonl(dd.POOL_STATUTES, statutes)
    first = {json.loads(x)["premise"][0] for x in FIRST_STATUTES.read_text("utf-8").splitlines()}
    if any(dd.overlaps(s["premise"][0], first) for s in statutes):
        raise RuntimeError("a provision of the first pool was drawn again")
    kinds = Counter(p["domain"] for p in renamed)
    acts = len({"/".join(s["premise"][0].split("/")[:4]) for s in statutes})
    pages = len({p["source_url"] for p in renamed if p["domain"] == "software"})
    return {
        "sources": len(renamed),
        **kinds,
        "acts": acts,
        "pages": pages,
        "listed_pages": len(PAGES),
    }


activate()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["sources", "questions", "units", "count"])
    command = parser.parse_args().command
    if command == "sources":
        print(json.dumps(build()))
    elif command == "questions":
        print(dict(dd.write_questions(workers=24)))  # Flash takes about 30 s a call
    elif command == "units":
        units = dd.record_units()
        print(json.dumps({"sentences": len(units), "clauses": sum(len(u["calls"]) for u in units)}))
    else:
        done = len(dd._read(dd.QUESTIONS)) if dd.QUESTIONS.exists() else 0
        print(
            json.dumps(
                {"sources": len(dd.pool()), "with_questions": done, "answers": len(dd.answers())}
            )
        )


if __name__ == "__main__":
    main()
