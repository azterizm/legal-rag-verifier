"""Stop 45: training data for the student judge (docs/GRID.md § Stop 45). Every step is resumable.

  uv run python scripts/distill_data.py pool         # sources disjoint from every test set
  uv run python scripts/enrich_premises.py results/distill/pool_statutes.jsonl --workers 6
  uv run python scripts/distill_data.py questions    # Gemini: 3 questions per source
  uv run --with modal modal run scripts/modal_distill.py::pool_answers   # L4, both prompts
  uv run python scripts/distill_data.py record       # clauses that reach the entailment check
  uv run python scripts/distill_data.py label        # Gemini + Opus 4.6, Opus 5.5 on disagreements
  uv run python scripts/distill_data.py dataset      # consensus labels → train / validation

Pool text, prompts and units quote statute text from ``data/`` and are git-ignored; ids, splits,
labels by prompt hash and the ledgers are committed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import threading
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "batteries/verifier"))

import auditor_judge as aj  # type: ignore[import-not-found]  # noqa: E402
import router  # type: ignore[import-not-found]  # noqa: E402

from legal_rag_verifier.premise import Passage, Premise  # noqa: E402
from legal_rag_verifier.segmenter import split_sentences  # noqa: E402

OUT = ROOT / "results/distill"
POOL = OUT / "pool.jsonl"
POOL_STATUTES = OUT / "pool_statutes.jsonl"
QUESTIONS = OUT / "questions.jsonl"
ANSWERS = OUT / "answers.jsonl"
UNITS = OUT / "units.jsonl"
SEED = 20261009
N_STATUTES = 250
N_SOFTWARE = 60
PER_ACT = 6
PER_PAGE = 5
VALIDATION = 0.1  # share of sources held out, by source
# Pages for the software pool: none is used by batteries/software or batteries/fresh (checked).
PAGES = {
    "https://docs.python.org/3/library/collections.html": "PSF-2.0",
    "https://docs.python.org/3/library/itertools.html": "PSF-2.0",
    "https://docs.python.org/3/library/datetime.html": "PSF-2.0",
    "https://docs.python.org/3/library/pathlib.html": "PSF-2.0",
    "https://docs.python.org/3/library/functools.html": "PSF-2.0",
    "https://www.postgresql.org/docs/17/sql-select.html": "PostgreSQL Licence",
    "https://www.postgresql.org/docs/17/indexes-types.html": "PostgreSQL Licence",
    "https://www.postgresql.org/docs/17/sql-insert.html": "PostgreSQL Licence",
    "https://www.sqlite.org/lang_createtable.html": "public domain",
    "https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/": "CC BY 4.0",
    "https://kubernetes.io/docs/concepts/workloads/controllers/daemonset/": "CC BY 4.0",
    "https://git-scm.com/docs/git-rebase": "GPL-2.0",
    "https://git-scm.com/docs/git-merge": "GPL-2.0",
    "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise": (
        "CC BY-SA 2.5"
    ),
    "https://doc.rust-lang.org/book/ch04-02-references-and-borrowing.html": "MIT OR Apache-2.0",
    "https://go.dev/doc/effective_go": "CC BY 4.0",
    "https://www.rfc-editor.org/rfc/rfc6750": "IETF Trust (BCP 78), excerpt",
    "https://www.rfc-editor.org/rfc/rfc9457": "IETF Trust (BCP 78), excerpt",
    "https://numpy.org/doc/stable/reference/generated/numpy.linspace.html": "BSD-3-Clause",
    "https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.groupby.html": "BSD-3-Clause",
    "https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GridSearchCV.html": (
        "BSD-3-Clause"
    ),
    "https://docs.pytorch.org/docs/2.7/generated/torch.nn.LSTM.html": "BSD-3-Clause",
    "https://prometheus.io/docs/prometheus/latest/querying/functions/": "Apache-2.0",
}
QUESTION_SYSTEM = (
    "You write questions that people ask about software documentation or UK legislation. Use only "
    "the text given. Reply with a single JSON object."
)
QUESTION_USER = """Text:
<<<
{source}
>>>

Write 3 different questions a person could ask that this text answers, in plain words, as someone \
who has not read the text would ask them. If the text has a figure, default, limit or deadline, \
one question asks for it. One question asks about a condition or exception if the text has one. \
One asks what the text requires or allows. Return JSON {{"questions": [three strings]}}."""
QUESTION_SHA = hashlib.sha256((QUESTION_SYSTEM + QUESTION_USER).encode()).hexdigest()
_lock = threading.Lock()


# ---------------------------------------------------------------------- exclusion


def used_coordinates() -> set[str]:
    """Every provision any battery or the fresh test uses, and the anchor provisions."""
    import tomllib  # noqa: PLC0415

    used: set[str] = set()
    files = [
        "batteries/grid/test.jsonl",
        "batteries/grid/dev.jsonl",
        "batteries/verifier/dev.jsonl",
        "batteries/verifier/heldout_draft.jsonl",
        "batteries/fresh/statutes.jsonl",
    ]
    for f in files:
        for line in (ROOT / f).read_text(encoding="utf-8").splitlines():
            used.update(json.loads(line).get("premise") or [])
    anchors = tomllib.loads((ROOT / "batteries/verifier/anchors.toml").read_text(encoding="utf-8"))
    used.update(a["coordinate"] for a in anchors.values())
    return used


def used_pages() -> set[str]:
    out = set()
    for f in ("batteries/software/test.jsonl", "batteries/fresh/software.jsonl"):
        for line in (ROOT / f).read_text(encoding="utf-8").splitlines():
            out.add(json.loads(line)["source_url"].split("#")[0])
    return out


def overlaps(coordinate: str, used: Iterable[str]) -> bool:
    return any(
        u == coordinate or u.startswith(coordinate + "/") or coordinate.startswith(u + "/")
        for u in used
    )


def check_disjoint(pool: Sequence[Mapping[str, Any]]) -> None:
    """Fails if any pool source is a test source (by provision coordinate or page)."""
    used, pages = used_coordinates(), used_pages()
    bad = [
        p["id"]
        for p in pool
        if (p["domain"] == "legal" and overlaps(p["premise"][0], used))
        or (p["domain"] == "software" and p["source_url"].split("#")[0] in pages)
    ]
    if bad:
        raise RuntimeError(f"pool overlaps a test set: {bad[:5]}")


# ---------------------------------------------------------------------- pool


def statute_candidates() -> list[str]:
    """Free, in-force sections of every Act the batteries draw on."""
    from legal_rag_verifier.corpus import instrument_path  # noqa: PLC0415

    used = used_coordinates()
    acts = sorted({"/".join(c.split("/")[:4]) for c in used if c.startswith("uk/ukpga/")})
    acts = [a for a in acts if not a.split("/")[2].isalpha()]  # calendar-year Acts
    out = []
    for act in acts:
        try:
            path = instrument_path(ROOT / "data", act + "/s1")
        except FileNotFoundError:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            c = r.get("coordinate", "")
            tail = c[len(act) + 1 :]
            if not re.fullmatch(r"s\d+[A-Z]*", tail) or r.get("repealed") or r.get("prospective"):
                continue
            if not overlaps(c, used):
                out.append(c)
    return out


def statute_pool(rng: random.Random) -> list[dict[str, Any]]:
    import premises  # noqa: PLC0415
    from grid_cells import render_premise  # type: ignore[import-not-found]  # noqa: PLC0415

    candidates = statute_candidates()
    rng.shuffle(candidates)
    per_act: Counter[str] = Counter()
    out: list[dict[str, Any]] = []
    for c in candidates:
        act = "/".join(c.split("/")[:4])
        if per_act[act] >= PER_ACT:
            continue
        try:
            built, _ = premises.build({"id": c, "premise": [c]}, ROOT / "data")
        except (KeyError, FileNotFoundError):
            continue
        text = render_premise(built)
        if not 400 <= len(text) <= 6000:  # noqa: PLR2004
            continue
        per_act[act] += 1
        out.append({"id": f"pl-{len(out) + 1:03d}", "domain": "legal", "premise": [c]})
        if len(out) == N_STATUTES:
            break
    return out


def software_pool(rng: random.Random) -> list[dict[str, Any]]:
    """Sections of each page under their headings, 300 to 2,500 characters, split at blocks."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from page_sections import sections  # type: ignore[import-not-found]  # noqa: PLC0415

    pages = used_pages()
    out: list[dict[str, Any]] = []
    for url, licence in PAGES.items():
        if url.split("#")[0] in pages:
            continue
        found = sections(url)
        rng.shuffle(found)
        page = url.rstrip("/").split("/")[-1].removesuffix(".html")
        for heading, text in found[:PER_PAGE]:
            heading = heading if not heading.startswith(", ") else page + heading
            out.append(
                {
                    "domain": "software",
                    "passages": [{"heading": heading, "text": text}],
                    "source_url": url,
                    "licence": licence,
                }
            )
    rng.shuffle(out)
    return [{"id": f"ps-{n:03d}", **p} for n, p in enumerate(out[:N_SOFTWARE], 1)]


def build_pool() -> list[dict[str, Any]]:
    rng = random.Random(SEED)  # noqa: S311 - a sample, not a secret
    pool = statute_pool(rng) + software_pool(rng)
    check_disjoint(pool)
    _write_jsonl(POOL, pool)
    _write_jsonl(
        POOL_STATUTES,
        [{"id": p["id"], "premise": p["premise"]} for p in pool if p["domain"] == "legal"],
    )
    return pool


def pool() -> list[dict[str, Any]]:
    return [json.loads(x) for x in POOL.read_text(encoding="utf-8").splitlines()]


def premise(row: Mapping[str, Any]) -> Premise:
    if row["domain"] == "software":
        return Premise(tuple(Passage(p["text"], heading=p["heading"]) for p in row["passages"]))
    import premises  # noqa: PLC0415
    from grid_prompts import ENRICHMENT  # type: ignore[import-not-found]  # noqa: PLC0415

    built, _ = premises.build(dict(row), ROOT / "data", ENRICHMENT)
    return built


def source_text(row: Mapping[str, Any]) -> str:
    from grid_cells import render_premise  # noqa: PLC0415

    return str(render_premise(premise(row)))


# ---------------------------------------------------------------------- questions


def _read(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


def _append(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")


def write_questions(workers: int = 6) -> Counter[str]:
    done = {q["source"] for q in _read(QUESTIONS)}
    todo = [p for p in pool() if p["id"] not in done]
    print(f"questions: {len(done)} sources done, {len(todo)} to ask", flush=True)

    def one(row: Mapping[str, Any]) -> str:
        user = QUESTION_USER.format(source=source_text(row))
        messages = [
            {"role": "system", "content": QUESTION_SYSTEM},
            {"role": "user", "content": user},
        ]
        for _ in range(3):
            try:
                reply = aj.extract_json(router.chat(router.GEMINI, messages)["content"])
            except (ValueError, json.JSONDecodeError, router.RouterError):
                continue
            questions = [q for q in reply.get("questions", []) if isinstance(q, str) and q.strip()]
            if questions:
                _append(QUESTIONS, [{"source": row["id"], "questions": questions[:3]}])
                return "ok"
        return "failed"

    with ThreadPoolExecutor(workers) as pool_:
        return Counter(pool_.map(one, todo))


def requests() -> list[dict[str, Any]]:
    """Two generator requests per question: with the source and closed-book (stop 43 prompts)."""
    from fresh_battery import (  # type: ignore[import-not-found]  # noqa: PLC0415
        CLOSED,
        SOFTWARE_PROMPT,
    )

    from legal_rag_verifier.engine import SYSTEM_PROMPT  # noqa: PLC0415

    rows = {p["id"]: p for p in pool()}
    out = []
    for q in _read(QUESTIONS):
        row = rows[q["source"]]
        prompt = SOFTWARE_PROMPT if row["domain"] == "software" else SYSTEM_PROMPT
        closed = CLOSED[row["domain"]]
        for n, question in enumerate(q["questions"]):
            for mode in ("source", "closed"):
                system = prompt.format(premise=source_text(row)) if mode == "source" else closed
                out.append(
                    {
                        "key": f"{row['id']}:{n}:{mode}",
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": question},
                        ],
                    }
                )
    return out


def answers() -> dict[str, dict[str, Any]]:
    return {r["key"]: r for r in _read(ANSWERS) if r.get("text") is not None}


def append_answers(records: Sequence[Mapping[str, Any]]) -> None:
    _append(ANSWERS, records)


# ---------------------------------------------------------------------- record, label, dataset


def record_units() -> list[dict[str, Any]]:
    """Each sentence of each answer through the verifier with ``RecordingScorer``: the clauses
    that reach the entailment check, with their candidates and the answer so far."""
    rows = {p["id"]: p for p in pool()}
    questions = {q["source"]: q["questions"] for q in _read(QUESTIONS)}
    built = {i: premise(r) for i, r in rows.items()}
    out = []
    for key, a in sorted(answers().items()):
        source, n, _mode = key.split(":")
        query = questions[source][int(n)]
        done: list[str] = []
        for i, s in enumerate(split_sentences(a["text"])):
            unit = {
                "key": f"{key}:{i}",
                "id": source,
                "query": query,
                "prefix": " ".join(done),
                "sentence": s.text,
            }
            r = aj.record([unit], {unit["key"]: built[source]})[0]
            out.append({**unit, "group": key, "calls": r["calls"], "claim": r["claim_rollback"]})
            done.append(s.text)
    _write_jsonl(UNITS, out)
    return out


def units() -> list[dict[str, Any]]:
    return _read(UNITS)


def split_of(source: str) -> str:
    digest = int(hashlib.sha256(f"{SEED}:{source}".encode()).hexdigest(), 16)
    return "validation" if digest % 1000 < VALIDATION * 1000 else "train"


def label_all() -> None:
    import teachers  # type: ignore[import-not-found]  # noqa: PLC0415

    all_batches = aj.batches(units())
    teachers.label("pool-gemini", "gemini", all_batches)
    teachers.label("pool-opus46", "opus46", all_batches)
    gem = teachers.read_labels("pool-gemini")
    o46 = teachers.read_labels("pool-opus46")
    disputed = [
        b
        for b in all_batches
        if any(k in gem and k in o46 and gem[k]["label"] != o46[k]["label"] for k in b["keys"])
    ]
    print(f"{len(disputed)} batches hold a disagreement", flush=True)
    teachers.label("pool-opus55", "opus55", disputed)


def dataset() -> dict[str, Any]:
    """Consensus label per clause (or Gemini alone, if stop 44 says so) → train / validation.
    Each example is the stop 42 per-clause prompt and the teacher's JSON reply."""
    import teachers  # noqa: PLC0415

    check = json.loads((OUT / "check44.json").read_text(encoding="utf-8"))
    gem = teachers.read_labels("pool-gemini")
    o46 = teachers.read_labels("pool-opus46")
    o55 = teachers.read_labels("pool-opus55")
    stats: Counter[str] = Counter()
    rows: dict[str, list[dict[str, Any]]] = {"train": [], "validation": []}
    seen: set[str] = set()
    for u in units():
        for clause, candidates in u["calls"]:
            user = aj.user_prompt(clause, candidates, u["prefix"])
            sha = aj.prompt_key(user)
            if sha in seen:
                continue
            seen.add(sha)
            if check["students_train_on"] == "gemini alone":
                label = gem.get(sha)
                stats["gemini"] += label is not None
            elif sha in gem and sha in o46 and gem[sha]["label"] == o46[sha]["label"]:
                label = gem[sha]
                stats["agreed"] += 1
            else:
                label = o55.get(sha)
                stats["opus55" if label else "dropped"] += 1
            if label is None or label["label"] not in aj.LABELS:
                continue
            reply = {k: label[k] for k in ("label", "passage", "reason")}
            rows[split_of(u["id"])].append(
                {
                    "sha": sha,
                    "source": u["id"],
                    "messages": [
                        {"role": "system", "content": aj.SYSTEM},
                        {"role": "user", "content": user},
                        {"role": "assistant", "content": json.dumps(reply, ensure_ascii=False)},
                    ],
                }
            )
    for split, examples in rows.items():
        _write_jsonl(OUT / f"{split}.jsonl", examples)
        stats[f"{split} examples"] = len(examples)
        stats.update(
            f"{split} {json.loads(e['messages'][2]['content'])['label']}" for e in examples
        )
    (OUT / "dataset.json").write_text(json.dumps(dict(stats), indent=1) + "\n", encoding="utf-8")
    return dict(stats)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["pool", "questions", "prompts", "record", "label", "dataset"]
    )
    command = parser.parse_args().command
    if command == "pool":
        p = build_pool()
        print(json.dumps(Counter(r["domain"] for r in p)))
    elif command == "questions":
        print(json.dumps(write_questions()))
    elif command == "prompts":
        reqs = requests()
        print(json.dumps({"requests": len(reqs), "done": len(answers())}))
    elif command == "record":
        us = record_units()
        calls = sum(len(u["calls"]) for u in us)
        print(json.dumps({"sentences": len(us), "clauses": calls, "batches": len(aj.batches(us))}))
    elif command == "label":
        label_all()
    else:
        print(json.dumps(dataset(), indent=1))


if __name__ == "__main__":
    main()
