"""Stop 69 (docs/GRID.md § Stop 69): the judge re-asked, and Opus 5.5 as a checker, on the sentences
stop 68's turn loop committed. Nothing is generated; the stop 68 grades are used as they are.

  uv run python scripts/judge69.py prompts          # counts
  uv run --with modal modal run scripts/modal_distill.py::judge69 --seed 1   # then --seed 2
  uv run python scripts/judge69.py opus             # router, Opus 5.5
  uv run python scripts/judge69.py report           # → results/judge69/report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "batteries/verifier"))

import auditor_judge as aj  # type: ignore[import-not-found]  # noqa: E402
import live68 as l68  # type: ignore[import-not-found]  # noqa: E402

from legal_rag_verifier.verifier import Verifier  # noqa: E402

OUT = ROOT / "results/judge69"
SOURCES = ("seed1", "seed2", "opus55")
RULES = {"S1": ("seed1",), "S12": ("seed1", "seed2"), "O": ("opus55",), "S12+O": SOURCES}
OPUS_STOP = 36.0  # USD, GRID § Stop 69
ALPHA = 0.05


def units() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Every sentence the turn loop committed (from the traces), with the answer so far, and the
    premise of each, keyed by the unit."""
    import live_loop as ll  # type: ignore[import-not-found]  # noqa: PLC0415

    refusal = set(ll.REFUSALS.values())
    out: list[dict[str, Any]] = []
    premises: dict[str, Any] = {}
    for gen in l68.GENERATORS:
        answers = [r for r in l68.done(gen).values() if r["arm"] == "turn" and r.get("trace")]
        for set_name in l68.SETS:
            items = {i["id"]: i for i in l68.items(set_name)}
            for r in answers:
                if r["set"] != set_name:
                    continue
                done: list[str] = []
                for s in r["trace"]["sentences"]:
                    if s["outcome"] != "emitted" or s["text"].strip() in refusal:
                        continue
                    key = f"{gen}:{r['key']}:{len(done)}"
                    out.append(
                        {
                            "key": key,
                            "gen": gen,
                            "id": r["id"],
                            "query": items[r["id"]]["query"],
                            "prefix": " ".join(done),
                            "sentence": s["text"],
                        }
                    )
                    premises[key] = items[r["id"]]["premise"]
                    done.append(s["text"])
    return out, premises


def requests(us: Sequence[Mapping[str, Any]], premises: Mapping[str, Any]) -> dict[str, str]:
    """The short-reply prompt of every call the verifier makes for these sentences."""
    out: dict[str, str] = {}
    for u, r in zip(us, aj.record(us, premises, config=aj.STRICT_FIGURES), strict=True):
        for clause, candidates in r["calls"]:
            user = aj.short_prompt(clause, candidates, u["prefix"])
            out[aj.prompt_key(user)] = user
    return out


def path(source: str) -> Path:
    return OUT / f"labels.{source}.jsonl"


def read(source: str) -> dict[str, dict[str, Any]]:
    file = path(source)
    if not file.exists():
        return {}
    rows = map(json.loads, file.read_text(encoding="utf-8").splitlines())
    return {r["sha"]: r for r in rows if r["label"] in aj.LABELS}


def append(source: str, labels: Mapping[str, Mapping[str, Any]]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with path(source).open("a", encoding="utf-8") as f:
        for sha, row in labels.items():
            f.write(json.dumps({"sha": sha, **row}, ensure_ascii=False) + "\n")


def opus() -> None:
    import router  # type: ignore[import-not-found]  # noqa: PLC0415
    import teachers  # type: ignore[import-not-found]  # noqa: PLC0415

    router.CAPS[router.OPUS55] = OPUS_STOP
    us, premises = units()
    asked = requests(us, premises)
    have = read("opus55")
    todo = {k: v for k, v in asked.items() if k not in have}
    print(f"opus55: {len(asked)} prompts, {len(todo)} to ask", flush=True)
    aj.judge_all(
        todo,
        teachers.router_chat(router.OPUS55),
        teachers.WORKERS["opus55"],
        lambda sha, row: append("opus55", {sha: row}),
    )
    print(json.dumps({"ledger": router.ledger().get(router.OPUS55, {})}))


class Labels:
    """Recorded short-reply labels in the entailment check's place; a prompt with no valid label
    counts as not stated."""

    def __init__(self, labels: Mapping[str, Mapping[str, Any]]) -> None:
        self.model_id = "recorded"
        self.labels = labels
        self.prefix = ""
        self.missing = 0

    def score(self, premises: Sequence[str], hypothesis: str) -> list[Any]:
        label = self.labels.get(aj.prompt_key(aj.short_prompt(hypothesis, premises, self.prefix)))
        if label is None:
            self.missing += 1
            return list(aj.one_hot("not_stated", 0, len(premises)))
        return list(aj.one_hot(label["label"], int(label.get("passage") or 0), len(premises)))


def rolled(
    us: Sequence[Mapping[str, Any]], premises: Mapping[str, Any], source: str
) -> tuple[set[str], int]:
    """Units the verifier rolls back with ``source``'s labels, and how many prompts had none."""
    scorer = Labels(read(source))
    verifier = Verifier(scorer, aj.STRICT_FIGURES)
    out = set()
    for u in us:
        scorer.prefix = u["prefix"]
        v = verifier.check_sentence(premises[u["key"]], u["sentence"], query=u["query"])
        if v.verdict.name != "EMIT":
            out.add(u["key"])
    return out, scorer.missing


def covered_by(
    us: Sequence[Mapping[str, Any]], premises: Mapping[str, Any], labels: Mapping[str, Any]
) -> set[str]:
    """Units whose every judge prompt has a label in ``labels`` (a unit with no call counts)."""
    out = set()
    for u, r in zip(us, aj.record(us, premises, config=aj.STRICT_FIGURES), strict=True):
        keys = [aj.prompt_key(aj.short_prompt(c, cands, u["prefix"])) for c, cands in r["calls"]]
        if all(k in labels for k in keys):
            out.add(u["key"])
    return out


def sign_p(gains: int, losses: int) -> float:
    from retry_report import mcnemar  # type: ignore[import-not-found]  # noqa: PLC0415

    return float(mcnemar(gains, losses))


def tally(
    us: Sequence[Mapping[str, Any]], grade: Mapping[str, str], dropped: set[str]
) -> dict[str, Any]:
    gains = sum(u["key"] in dropped and grade[u["key"]] == "no" for u in us)
    losses = sum(u["key"] in dropped and grade[u["key"]] == "yes" for u in us)
    kept = [u for u in us if u["key"] not in dropped and grade[u["key"]] in ("yes", "no")]
    right_kept = sum(grade[u["key"]] == "yes" for u in kept)
    return {
        "sentences": len(us),
        "wrong": sum(grade[u["key"]] == "no" for u in us),
        "dropped": sum(u["key"] in dropped for u in us),
        "wrong_dropped": gains,
        "right_dropped": losses,
        "unsure_dropped": sum(u["key"] in dropped and grade[u["key"]] == "unsure" for u in us),
        "kept_accuracy": round(right_kept / len(kept), 4) if kept else None,
        "sign_p": round(sign_p(gains, losses), 6),
    }


def report() -> dict[str, Any]:
    import live68_grade as lg  # type: ignore[import-not-found]  # noqa: PLC0415

    us, premises = units()
    by_sentence = lg.grades_by_sentence()
    graded = [u for u in us if (u["id"], u["sentence"].strip()) in by_sentence]
    ungraded = len(us) - len(graded)
    us = graded  # a trace sentence the answer's segmenter split differently has no grade
    grade = {u["key"]: by_sentence[(u["id"], u["sentence"].strip())] for u in us}
    drops: dict[str, set[str]] = {}
    out: dict[str, Any] = {"missing_labels": {}, "rules": {}, "ungraded_left_out": ungraded}
    for source in SOURCES:
        drops[source], out["missing_labels"][source] = rolled(us, premises, source)
    # Opus 5.5 stopped at its ledger stop (your choice of 2026-10-15): rules with it are read on the
    # sentences whose prompts all have its label, and the seed rules are read there too.
    covered = covered_by(us, premises, read("opus55"))
    out["opus_covered_sentences"] = len(covered)
    scopes = {"all": us, "opus_covered": [u for u in us if u["key"] in covered]}
    for scope, group in scopes.items():
        for rule, sources in RULES.items():
            if scope == "all" and "opus55" in sources:
                continue
            dropped = set().union(*(drops[s] for s in sources))
            name = rule if scope == "all" else f"{rule} (Opus-covered)"
            out["rules"][name] = {"total": tally(group, grade, dropped)}
            for gen in l68.GENERATORS:
                part = [u for u in group if u["gen"] == gen]
                out["rules"][name][gen] = tally(part, grade, dropped)
            t = out["rules"][name]["total"]
            t["passes"] = bool(t["wrong_dropped"] > t["right_dropped"] and t["sign_p"] < ALPHA)
    out["baseline"] = {
        gen: tally([u for u in us if u["gen"] == gen], grade, set()) for gen in l68.GENERATORS
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prompts", "opus", "report"])
    command = parser.parse_args().command
    if command == "prompts":
        us, premises = units()
        print(json.dumps({"sentences": len(us), "prompts": len(requests(us, premises))}))
    elif command == "opus":
        opus()
    else:
        out = report()
        print(json.dumps({r: v["total"] for r, v in out["rules"].items()}, indent=1))


if __name__ == "__main__":
    main()
