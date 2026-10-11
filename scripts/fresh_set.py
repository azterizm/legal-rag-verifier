"""Stop 56: build a second fresh test with no hand-written question (docs/GRID.md § Stop 56).

Sources are drawn by seed: statute provisions no battery, test or training pool uses, and one
section from each of a fixed list of documentation pages none of them uses. Gemini writes three
questions per source with stop 45's prompt and one is drawn by the same seed.

  uv run python scripts/fresh_set.py sources     # → results/fresh2/sources.jsonl (no model call)
  uv run python scripts/fresh_set.py questions   # router, Gemini 3.8 Flash; then writes the rows
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "batteries/verifier"))

import auditor_judge as aj  # type: ignore[import-not-found]  # noqa: E402
import distill_data as dd  # type: ignore[import-not-found]  # noqa: E402

NAME = "fresh2"
SEED = 20261011
N_STATUTES = 20  # one per Act
N_SOFTWARE = 20  # one per page
BATTERY = ROOT / "batteries" / NAME
OUT = ROOT / "results" / NAME
SOURCES = OUT / "sources.jsonl"
QUESTIONS = OUT / "questions.jsonl"
# Pages used by no battery, by the first fresh test or by the training pool. Fixed before any fetch.
PAGES = {
    "https://docs.python.org/3/library/re.html": "PSF-2.0",
    "https://docs.python.org/3/library/subprocess.html": "PSF-2.0",
    "https://docs.python.org/3/library/logging.html": "PSF-2.0",
    "https://docs.python.org/3/library/argparse.html": "PSF-2.0",
    "https://www.postgresql.org/docs/17/sql-update.html": "PostgreSQL Licence",
    "https://www.postgresql.org/docs/17/sql-delete.html": "PostgreSQL Licence",
    "https://www.sqlite.org/lang_conflict.html": "public domain",
    "https://www.sqlite.org/lang_createindex.html": "public domain",
    "https://kubernetes.io/docs/concepts/workloads/controllers/job/": "CC BY 4.0",
    "https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/": "CC BY 4.0",
    "https://git-scm.com/docs/git-cherry-pick": "GPL-2.0",
    "https://git-scm.com/docs/git-reset": "GPL-2.0",
    "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Map": (
        "CC BY-SA 2.5"
    ),
    "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Set": (
        "CC BY-SA 2.5"
    ),
    "https://doc.rust-lang.org/book/ch06-01-defining-an-enum.html": "MIT OR Apache-2.0",
    "https://www.rfc-editor.org/rfc/rfc7617": "IETF Trust (BCP 78), excerpt",
    "https://www.rfc-editor.org/rfc/rfc6902": "IETF Trust (BCP 78), excerpt",
    "https://numpy.org/doc/stable/reference/generated/numpy.arange.html": "BSD-3-Clause",
    "https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.sort_values.html": (
        "BSD-3-Clause"
    ),
    "https://scikit-learn.org/stable/modules/generated/sklearn.svm.SVC.html": "BSD-3-Clause",
    "https://docs.pytorch.org/docs/2.7/generated/torch.nn.Linear.html": "BSD-3-Clause",
    "https://prometheus.io/docs/prometheus/latest/querying/operators/": "Apache-2.0",
}


def taken_coordinates() -> set[str]:
    """Every provision a battery, the first fresh test or the training pool uses."""
    lines = dd.POOL_STATUTES.read_text(encoding="utf-8").splitlines()
    return set(dd.used_coordinates()) | {json.loads(x)["premise"][0] for x in lines}


def taken_pages() -> set[str]:
    return set(dd.used_pages()) | {u.split("#")[0] for u in dd.PAGES}


def statutes(rng: random.Random) -> list[dict[str, Any]]:
    """One provision per Act, 400 to 6,000 characters as rendered (stop 45's bounds)."""
    import premises  # noqa: PLC0415
    from grid_cells import render_premise  # type: ignore[import-not-found]  # noqa: PLC0415

    taken = taken_coordinates()
    candidates = [c for c in dd.statute_candidates() if not dd.overlaps(c, taken)]
    rng.shuffle(candidates)
    acts: set[str] = set()
    out: list[dict[str, Any]] = []
    for c in candidates:
        act = "/".join(c.split("/")[:4])
        if act in acts:
            continue
        try:
            built, _ = premises.build({"id": c, "premise": [c]}, ROOT / "data")
        except (KeyError, FileNotFoundError):
            continue
        if not 400 <= len(render_premise(built)) <= 6000:  # noqa: PLR2004
            continue
        acts.add(act)
        out.append({"id": f"gl-{len(out) + 1:02d}", "domain": "legal", "premise": [c]})
        if len(out) == N_STATUTES:
            break
    return out


def software(rng: random.Random) -> list[dict[str, Any]]:
    """One section per page, 300 to 2,500 characters (``page_sections``), pages in seeded order."""
    from page_sections import sections  # type: ignore[import-not-found]  # noqa: PLC0415

    taken = taken_pages()
    urls = [u for u in PAGES if u.split("#")[0] not in taken]
    if len(urls) != len(PAGES):
        raise RuntimeError("a page of the list is already used")
    rng.shuffle(urls)
    out: list[dict[str, Any]] = []
    for url in urls:
        try:
            found = sections(url)
        except OSError as exc:
            print(f"skipped {url}: {exc!r}"[:200], flush=True)
            continue
        if not found:
            print(f"skipped {url}: no section", flush=True)
            continue
        raw_heading, text = rng.choice(found)
        page = url.rstrip("/").split("/")[-1].removesuffix(".html")
        heading = page + raw_heading if raw_heading.startswith(", ") else raw_heading
        out.append(
            {
                "id": f"gs-{len(out) + 1:02d}",
                "domain": "software",
                "passages": [{"heading": heading, "text": text}],
                "source_url": url,
                "licence": PAGES[url],
            }
        )
        if len(out) == N_SOFTWARE:
            break
    return out


def build_sources() -> list[dict[str, Any]]:
    rng = random.Random(SEED)  # noqa: S311 - a sample, not a secret
    rows = statutes(rng) + software(rng)
    dd.check_disjoint(rows)
    taken, pages = taken_coordinates(), taken_pages()
    for r in rows:
        if r["domain"] == "legal" and dd.overlaps(r["premise"][0], taken):
            raise RuntimeError(f"{r['id']} is in the training pool")
        if r["domain"] == "software" and r["source_url"].split("#")[0] in pages:
            raise RuntimeError(f"{r['id']} is on a training page")
    OUT.mkdir(parents=True, exist_ok=True)
    SOURCES.write_text("".join(json.dumps(r, ensure_ascii=False) + "\\n" for r in rows), "utf-8")
    return rows


def sources() -> list[dict[str, Any]]:
    return [json.loads(x) for x in SOURCES.read_text(encoding="utf-8").splitlines()]


def write_questions() -> None:
    """Three questions per source from Gemini (stop 45's prompt, unchanged); a rerun asks only
    the sources not done. Then one question per source is drawn and the battery rows written."""
    import router  # type: ignore[import-not-found]  # noqa: PLC0415

    done = {}
    if QUESTIONS.exists():
        done = {q["source"]: q for q in map(json.loads, QUESTIONS.read_text("utf-8").splitlines())}
    for row in sources():
        if row["id"] in done:
            continue
        user = dd.QUESTION_USER.format(source=dd.source_text(row))
        messages = [
            {"role": "system", "content": dd.QUESTION_SYSTEM},
            {"role": "user", "content": user},
        ]
        for _ in range(3):
            try:
                reply = aj.extract_json(router.chat(router.GEMINI, messages)["content"])
            except (ValueError, json.JSONDecodeError, router.RouterError):
                continue
            asked = [q for q in reply.get("questions", []) if isinstance(q, str) and q.strip()]
            if asked:
                done[row["id"]] = {"source": row["id"], "questions": asked[:3]}
                with QUESTIONS.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(done[row["id"]], ensure_ascii=False) + "\\n")
                break
    missing = [r["id"] for r in sources() if r["id"] not in done]
    if missing:
        raise SystemExit(f"no questions yet for {missing}; rerun")
    rng = random.Random(SEED + 1)  # noqa: S311 - a draw, not a secret
    BATTERY.mkdir(parents=True, exist_ok=True)
    files: dict[str, list[str]] = {"statutes": [], "software": []}
    for row in sources():
        asked = done[row["id"]]["questions"]
        pick = rng.randrange(len(asked))
        base = {"id": row["id"], "query": asked[pick], "question_index": pick}
        base |= {"expects_abstention": False}
        if row["domain"] == "legal":
            line = {**base, "premise": row["premise"], "split": NAME}
            files["statutes"].append(json.dumps(line, ensure_ascii=False))
        else:
            line = {**base, "passages": row["passages"], "source_url": row["source_url"]}
            line |= {"licence": row["licence"], "retrieved": "2026-10-11"}
            files["software"].append(json.dumps(line, ensure_ascii=False))
    for name, lines in files.items():
        (BATTERY / f"{name}.jsonl").write_text("\\n".join(lines) + "\\n", encoding="utf-8")
    print({k: len(v) for k, v in files.items()})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["sources", "questions"])
    command = parser.parse_args().command
    if command == "sources":
        rows = build_sources()
        chars = [len(dd.source_text(r)) for r in rows]
        acts = Counter("/".join(r["premise"][0].split("/")[:4]) for r in rows if "premise" in r)
        print(
            json.dumps(
                {
                    "sources": len(rows),
                    "acts": len(acts),
                    "chars_p50": sorted(chars)[len(chars) // 2],
                }
            )
        )
    else:
        write_questions()


if __name__ == "__main__":
    main()
