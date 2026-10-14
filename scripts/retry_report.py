"""Stop 67 readings (docs/GRID.md § Stop 67).

  uv run --extra hf python scripts/retry_report.py mechanics   # no grade needed; the sheet to grade
  uv run --extra hf python scripts/retry_report.py report      # after the grades → report.json

``mechanics`` writes ``results/retry/mechanics.json`` (counts only), and ``sheet.md``, ``key.json``
and ``grades.csv`` for the retries no earlier sheet graded (the sheet and key are git-ignored).
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import sys
from collections.abc import Mapping, Sequence
from math import comb
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "batteries/verifier"))

import retry_states as rs  # type: ignore[import-not-found]  # noqa: E402

from legal_rag_verifier.segmenter import split_sentences  # noqa: E402

SETS = ("fresh", "fresh2")
ARMS = ("B", "T", "P", "K", "K-far", "KA")
CONDITIONS = ("closed", "source")
# Sheets whose grades a word-for-word equal retry keeps: the 7B's two tests and the 27B's answers.
SHEETS = ("fresh", "fresh2", "fresh2-q27", "fresh2-live", "fresh2-short-live")
COMPARISONS = (("K", "T"), ("KA", "T"), ("KA", "K"), ("K", "K-far"), ("P", "T"), ("T", "B"))
ALPHA = 0.05
BOOST_SHARE = 2 / 3
SHEET_SEED = 20261015


# ---------------------------------------------------------------------- statistics


def mcnemar(only_a: int, only_b: int) -> float:
    """Exact two-sided McNemar p-value from the discordant pairs (also the exact sign test)."""
    n = only_a + only_b
    if n == 0:
        return 1.0
    tail = sum(comb(n, k) for k in range(min(only_a, only_b) + 1)) / float(2**n)
    return min(1.0, 2 * tail)


def holm(p: Mapping[str, float]) -> dict[str, float]:
    """Holm-adjusted p-values (step-down, monotone)."""
    order = sorted(p, key=lambda k: p[k])
    out: dict[str, float] = {}
    running = 0.0
    for i, key in enumerate(order):
        running = max(running, min(1.0, (len(order) - i) * p[key]))
        out[key] = running
    return out


def _p50(values: Sequence[float]) -> float | None:
    return round(statistics.median(values), 3) if values else None


def _mean(values: Sequence[float]) -> float | None:
    return round(statistics.fmean(values), 4) if values else None


# ---------------------------------------------------------------------- data


def load() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, str]]:
    """States, retries by state hash, and the judge's verdict on every retry and follow-on."""
    states: list[dict[str, Any]] = []
    retries: dict[str, dict[str, Any]] = {}
    verdicts: dict[str, str] = {}
    for name in SETS:
        s = rs.read_jsonl(rs.OUT / f"states.{name}.jsonl")
        r = rs.read_jsonl(rs.OUT / f"retries.{name}.jsonl")
        labels = {x["sha"]: x for x in rs.read_jsonl(rs.labels_path(name))}
        verdicts |= rs.verdicts(rs.sentence_units(s, r), rs.premises_for(s), labels)
        states += s
        retries |= {x["hash"]: x for x in r}
    return states, retries, verdicts


def carried() -> dict[tuple[str, str], str]:
    """(question id, sentence) → yes / no / unsure from every earlier sheet; a sentence two sheets
    grade differently is left out."""
    seen: dict[tuple[str, str], set[str]] = {}
    for name in SHEETS:
        folder = ROOT / "results" / name
        key = json.loads((folder / "key.json").read_text(encoding="utf-8"))
        with (folder / "grades.csv").open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                k = key[row["item"]]
                grade = row["correct"].strip().lower()
                seen.setdefault((k["id"], k["text"].strip()), set()).add(grade)
    return {k: next(iter(v)) for k, v in seen.items() if len(v) == 1}


def condition(state: Mapping[str, Any]) -> str:
    return str(state["mode"])


def primary(state: Mapping[str, Any]) -> bool:
    return bool(state["x_grade"] == "no")


# ---------------------------------------------------------------------- mechanics


def mechanics(
    states: Sequence[Mapping[str, Any]],
    retries: Mapping[str, Mapping[str, Any]],
    verdicts: Mapping[str, str],
) -> dict[str, Any]:
    out: dict[str, Any] = {"states": {}, "arms": {}, "checks": {}}
    groups = {
        f"{'primary' if p else 'secondary'} {c}": [
            s for s in states if primary(s) is p and condition(s) == c and s["hash"] in retries
        ]
        for p in (True, False)
        for c in CONDITIONS
    }
    out["states"] = {g: len(v) for g, v in groups.items()}
    for g, group in groups.items():
        out["arms"][g] = {}
        for arm in ARMS:
            rows = [(s, retries[s["hash"]]["arms"][arm]) for s in group]
            base = [retries[s["hash"]]["arms"]["B"]["logp_x"] for s, _ in rows]
            key = [f"{s['hash']}:{arm}" for s, _ in rows]
            out["arms"][g][arm] = {
                "retries": len(rows),
                "empty": sum(not r["retry"] for _, r in rows),
                "judge_passed": sum(verdicts.get(f"{k}:retry") == "EMIT" for k in key),
                "copied": sum(rs.copies(r["retry"], s["passage_text"]) for s, r in rows),
                "same_as_x": sum(r["retry"] == s["x_text"].strip() for s, r in rows),
                "follow_empty": sum(not r["follow"] for _, r in rows),
                "follow_judge_passed": sum(verdicts.get(f"{k}:follow") == "EMIT" for k in key),
                "follow_copied": sum(rs.copies(r["follow"], s["passage_text"]) for s, r in rows),
                "share_mean": _mean([r["share"] for _, r in rows if r["share"] is not None]),
                "logp_x_change_mean": _mean(
                    [r["logp_x"] - b for (_, r), b in zip(rows, base, strict=True)]
                ),
                "seconds_p50": _p50([r["prepare_seconds"] + r["retry_seconds"] for _, r in rows]),
                "computed_mean": _mean([r["computed"] for _, r in rows]),
            }
    ran = [s for s in states if s["hash"] in retries]
    shares = [
        (retries[s["hash"]]["arms"]["KA"]["share"], retries[s["hash"]]["arms"]["K"]["share"])
        for s in ran
    ]
    shares = [(a, b) for a, b in shares if a is not None and b is not None]
    above = sum(a > b for a, b in shares)
    out["checks"]["boost_acted"] = {
        "states": len(shares),
        "ka_share_above_k": above,
        "acted": bool(shares) and above >= BOOST_SHARE * len(shares),
    }
    near: dict[str, Any] = {}
    for c in CONDITIONS:
        pairs = [
            (
                retries[s["hash"]]["arms"]["K"]["logp_x"],
                retries[s["hash"]]["arms"]["K-far"]["logp_x"],
            )
            for s in ran
            if primary(s) and condition(s) == c
        ]
        lower, higher = sum(a < b for a, b in pairs), sum(a > b for a, b in pairs)
        near[c] = {
            "states": len(pairs),
            "x_less_likely_near": lower,
            "x_less_likely_far": higher,
            "sign_p": round(mcnemar(lower, higher), 6),
        }
    out["checks"]["nearness_logp_x"] = near
    out["checks"]["parity"] = {
        "states": len(ran),
        "first_token": sum(retries[s["hash"]]["parity"]["first_token"] for s in ran),
        "same_text": sum(retries[s["hash"]]["parity"]["same_text"] for s in ran),
    }
    out["checks"]["missing_states"] = [s["hash"] for s in states if s["hash"] not in retries]
    return out


# ---------------------------------------------------------------------- grades


def to_grade(
    states: Sequence[Mapping[str, Any]],
    retries: Mapping[str, Mapping[str, Any]],
    grades: Mapping[tuple[str, str], str],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Carried grades per ``hash:arm``, and the unique (state, text) items left to grade. A carried
    right grade is good unless the retry repeats a committed sentence; a carried wrong grade still
    needs "repeats X's error"."""
    carried_out: dict[str, dict[str, Any]] = {}
    items: dict[tuple[str, str], dict[str, Any]] = {}
    for s in states:
        r = retries.get(s["hash"])
        if r is None:
            continue
        committed = {x.text.strip() for x in split_sentences(s["prefix"])}
        for arm in ARMS:
            text = r["arms"][arm]["retry"]
            key = f"{s['hash']}:{arm}"
            if not text:
                carried_out[key] = {"good": False, "wrong": False, "empty": True}
                continue
            grade = grades.get((s["id"], text))
            if grade == "yes":
                carried_out[key] = {"good": text not in committed, "wrong": False, "empty": False}
                continue
            item = items.setdefault(
                (s["hash"], text),
                {"hash": s["hash"], "text": text, "arms": [], "carried": grade},
            )
            item["arms"].append(arm)
    return carried_out, list(items.values())


def sheet(states: Sequence[Mapping[str, Any]], items: Sequence[Mapping[str, Any]]) -> int:
    """The blind sheet: states in a seeded order, each state's retries shuffled and lettered."""
    import fresh_battery as fb  # type: ignore[import-not-found]  # noqa: PLC0415

    by_hash = {s["hash"]: s for s in states}
    per_state: dict[str, list[Mapping[str, Any]]] = {}
    for item in items:
        per_state.setdefault(item["hash"], []).append(item)
    rng = random.Random(SHEET_SEED)  # noqa: S311 - a shuffle, not a secret
    order = sorted(per_state)
    rng.shuffle(order)
    rows_by_set: dict[str, dict[str, Any]] = {}
    keep = fb.BATTERY
    try:
        for name in SETS:
            fb.BATTERY = ROOT / "batteries" / name
            rows_by_set[name] = {r["id"]: r for r in fb.rows()}
    finally:
        fb.BATTERY = keep
    lines = [
        "# Stop 67: retries to grade",
        "",
        (
            "Each block shows a question, its source, the answer so far, and the sentence the "
            "judge rolled back (X, graded wrong unless marked). Below it are retries written in "
            "X's place. For each retry fill `grades.csv`: `grounding` supported / unsupported / "
            "contradicted / no_claim; `on_question` yes / no; `reads_on` yes / no (a complete "
            "sentence that "
            "continues the answer so far, not a fragment, a repeat or pasted source); `same_error` "
            "yes / no (only if not supported: it makes X's wrong claim again). A retry marked "
            "(graded wrong before) needs `same_error` only."
        ),
        "",
    ]
    key: dict[str, Any] = {}
    grades = []
    for n, h in enumerate(order, 1):
        s = by_hash[h]
        row = rows_by_set[s["set"]][s["id"]]
        lines += [
            f"## S{n:03d}. {s['query']}",
            "",
            "Source:",
            "",
            "```",
            fb.source_text(row),
            "```",
            "",
            f"Answer so far: {s['prefix'] or '(none)'}",
            "",
            f"X{'' if s['x_grade'] == 'no' else ' (graded right)'}: {s['x_text']}",
            "",
        ]
        group = list(per_state[h])
        rng.shuffle(group)
        for letter, item in zip("ABCDEFGH", group, strict=False):
            code = f"S{n:03d}{letter}"
            mark = " (graded wrong before)" if item["carried"] == "no" else ""
            lines.append(f"- **{code}.**{mark} {item['text']}")
            key[code] = {"hash": h, "arms": item["arms"], "carried": item["carried"]}
            grades.append(
                {
                    "item": code,
                    "grounding": "",
                    "on_question": "",
                    "reads_on": "",
                    "same_error": "",
                    "note": "",
                }
            )
        lines.append("")
    (rs.OUT / "sheet.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (rs.OUT / "key.json").write_text(json.dumps(key, indent=1, ensure_ascii=False) + "\n", "utf-8")
    with (rs.OUT / "grades.csv").open("w", encoding="utf-8", newline="") as f:
        fields = ["item", "grounding", "on_question", "reads_on", "same_error", "note"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(grades)
    return len(grades)


def cmd_mechanics() -> None:
    states, retries, verdicts = load()
    out = mechanics(states, retries, verdicts)
    carried_out, items = to_grade(states, retries, carried())
    out["grades"] = {
        "retries": sum(len(r["arms"]) for r in retries.values()),
        "empty": sum(v["empty"] for v in carried_out.values()),
        "carried_right": sum(not v["empty"] for v in carried_out.values()),
        "items_to_grade": len(items),
        "of_which_carried_wrong": sum(i["carried"] == "no" for i in items),
    }
    out["grades"]["sheet_items"] = sheet(states, items)
    (rs.OUT / "mechanics.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1))


def outcomes(
    states: Sequence[Mapping[str, Any]], retries: Mapping[str, Mapping[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Per ``hash:arm``: good, wrong and same_error, from the carried grades and the sheet."""
    carried_out, _ = to_grade(states, retries, carried())
    key = json.loads((rs.OUT / "key.json").read_text(encoding="utf-8"))
    with (rs.OUT / "grades.csv").open(encoding="utf-8") as f:
        rows = {r["item"]: r for r in csv.DictReader(f)}
    out = {k: {**v, "same_error": False} for k, v in carried_out.items()}
    for code, item in key.items():
        g = {k: (v or "").strip().lower() for k, v in rows[code].items()}
        if item["carried"] == "no":
            wrong, good = True, False
        else:
            if g["grounding"] not in ("supported", "unsupported", "contradicted", "no_claim"):
                raise RuntimeError(f"{code}: grounding missing")
            wrong = g["grounding"] in ("unsupported", "contradicted")
            good = g["grounding"] == "supported" and g["on_question"] == g["reads_on"] == "yes"
        if wrong and g["same_error"] not in ("yes", "no"):
            raise RuntimeError(f"{code}: same_error missing")
        for arm in item["arms"]:
            out[f"{item['hash']}:{arm}"] = {
                "good": good,
                "wrong": wrong,
                "empty": False,
                "same_error": wrong and g["same_error"] == "yes",
            }
    return out


def readings(
    states: Sequence[Mapping[str, Any]], result: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for p in (True, False):
        for c in CONDITIONS:
            group = [s for s in states if primary(s) is p and condition(s) == c]
            name = f"{'primary' if p else 'secondary'} {c}"
            arms = {
                arm: {
                    "states": len(group),
                    "good": sum(result[f"{s['hash']}:{arm}"]["good"] for s in group),
                    "wrong": sum(result[f"{s['hash']}:{arm}"]["wrong"] for s in group),
                    "same_error": sum(result[f"{s['hash']}:{arm}"]["same_error"] for s in group),
                    "empty": sum(result[f"{s['hash']}:{arm}"]["empty"] for s in group),
                }
                for arm in ARMS
            }
            tests: dict[str, Any] = {}
            for a, b in COMPARISONS:
                pair: dict[str, Any] = {}
                for what in ("good", "wrong"):
                    ra = [result[f"{s['hash']}:{a}"][what] for s in group]
                    rb = [result[f"{s['hash']}:{b}"][what] for s in group]
                    only_a = sum(x and not y for x, y in zip(ra, rb, strict=True))
                    only_b = sum(y and not x for x, y in zip(ra, rb, strict=True))
                    pair[what] = {"only_a": only_a, "only_b": only_b, "p": mcnemar(only_a, only_b)}
                tests[f"{a} against {b}"] = pair
            adjusted = holm({k: v["good"]["p"] for k, v in tests.items()})
            for k, v in tests.items():
                v["good"]["holm_p"] = round(adjusted[k], 6)
                v["good"]["p"] = round(v["good"]["p"], 6)
                v["wrong"]["p"] = round(v["wrong"]["p"], 6)
            out[name] = {"arms": arms, "tests": tests}
    closed = out["primary closed"]["tests"]

    def wins(a: str, b: str) -> bool:
        t = closed[f"{a} against {b}"]
        return bool(
            t["good"]["only_a"] > t["good"]["only_b"]
            and t["good"]["holm_p"] < ALPHA
            and t["wrong"]["only_a"] <= t["wrong"]["only_b"]
        )

    out["reading"] = {
        "editing_the_cache_helps": wins("K", "T") or wins("KA", "T"),
        "nearness_by_good_retries": wins("K", "K-far"),
        "note": "closed-book primary set; with the source the counts are reported, not tested",
    }
    return out


def cmd_report() -> None:
    states, retries, verdicts = load()
    ran = [s for s in states if s["hash"] in retries]
    result = outcomes(ran, retries)
    out = {"mechanics": mechanics(states, retries, verdicts), **readings(ran, result)}
    (rs.OUT / "report.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "mechanics"}, indent=1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["mechanics", "report"])
    if parser.parse_args().command == "mechanics":
        cmd_mechanics()
    else:
        cmd_report()


if __name__ == "__main__":
    main()
