"""Stop 29 report: placement arms and attention/likelihood, from ``results/grid/replay/``.

``sglang.jsonl`` (git-ignored) is the SGLang phase's raw output; ``arms.jsonl`` is the same without
the prompt-side token ids, and is what this report and the repository keep.

Method: ``docs/GRID.md`` § Stop 29. Primary comparisons (Holm-corrected at 0.05): R1 against R3 and
R1 against R4 (first-retry pass, exact McNemar), and, with the inserted turn against without it,
the attention share of R1's sentence on provision text, its log-probability, and the rejected
draft's log-probability (exact sign tests over states).

  uv run python scripts/replay_report.py      # → results/grid/replay/report.json
"""

from __future__ import annotations

import json
import statistics
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from replay_states import (  # type: ignore[import-not-found]  # noqa: E402
    GRID,
    load,
    mcnemar,
    shared_states,
)

OUT = GRID / "replay"
ARMS = ("R0", "R1", "R2", "R3", "R4")
LAYERS = {"all": slice(0, None), "0-8": slice(0, 9), "9-18": slice(9, 19), "19-27": slice(19, 28)}
PROVISION = ("inserted_windows", "other_windows", "inserted_copy", "top_copy")


def sig(p: float) -> float:
    """A p-value to 3 significant figures (small ones stay non-zero)."""
    return float(f"{p:.3g}")


def holm(pvalues: Mapping[str, float], alpha: float = 0.05) -> dict[str, dict[str, Any]]:
    """Holm step-down: adjusted p-values and which comparisons hold at ``alpha``."""
    ranked = sorted(pvalues.items(), key=lambda kv: kv[1])
    out: dict[str, dict[str, Any]] = {}
    running, rejecting = 0.0, True
    for i, (name, p) in enumerate(ranked):
        adjusted = min(1.0, max(running, (len(ranked) - i) * p))
        running = adjusted
        rejecting = rejecting and adjusted < alpha
        out[name] = {"p": p, "holm_p": sig(adjusted), "holds": rejecting}
    return out


def sign_test(pairs: Sequence[tuple[float, float]]) -> dict[str, Any]:
    """Exact two-sided sign test of ``first > second`` over pairs; ties dropped."""
    above = sum(a > b for a, b in pairs)
    below = sum(a < b for a, b in pairs)
    diffs = [a - b for a, b in pairs]
    return {
        "states": len(pairs),
        "first_higher": above,
        "first_lower": below,
        "median_difference": round(statistics.median(diffs), 6) if diffs else None,
        "p": sig(mcnemar(above, below)),
    }


def passed(arm: Mapping[str, Any] | None) -> bool:
    return arm is not None and arm["verdict"] == "EMIT"


def paired_arms(records: Sequence[Mapping[str, Any]], a: str, b: str) -> dict[str, Any]:
    x = [passed(r.get(a)) for r in records]
    y = [passed(r.get(b)) for r in records]
    only_a = sum(p and not q for p, q in zip(x, y, strict=True))
    only_b = sum(q and not p for p, q in zip(x, y, strict=True))
    return {
        a: sum(x),
        b: sum(y),
        f"only_{a}": only_a,
        f"only_{b}": only_b,
        "p": sig(mcnemar(only_a, only_b)),
    }


def share(part: Mapping[str, Any], spans: Sequence[str], layers: slice) -> float:
    """Mean over the layers of the summed attention share on ``spans``."""
    att: dict[str, list[float]] = part["attention"]
    depth = len(next(iter(att.values())))
    per_layer = [sum(att[s][i] for s in spans if s in att) for i in range(depth)]
    return float(statistics.mean(per_layer[layers]))


def arms_report(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ok = [r for r in records if r.get("parity")]
    states, _ = shared_states(load(GRID / "4B.jsonl"), load(GRID / "4B-inject.jsonl"))
    recorded = {s.id: s for s in states}
    follow = {
        arm: [f["verdict"] == "EMIT" for r in ok for f in r[arm]["follow_on"]]
        for arm in ARMS
        if arm != "R2"
    }
    warm = [r["probe_warm"]["latency_ns"] / 1e6 for r in ok]
    cold = [r["probe_cold"]["latency_ns"] / 1e6 for r in ok]
    return {
        "states": len(records),
        "parity": f"{len(ok)}/{len(records)}",
        "R0_matches_recorded_A": sum(
            r["R0"]["text"] == (recorded[r["id"]].a_retry or {}).get("verdict", {}).get("text")
            for r in ok
        ),
        "R1_matches_recorded_B": sum(
            r["R1"]["text"] == (recorded[r["id"]].b_retry or {}).get("verdict", {}).get("text")
            for r in ok
        ),
        "first_retry_passed": {arm: sum(passed(r[arm]) for r in ok) for arm in ARMS},
        "R1_vs_R3": paired_arms(ok, "R1", "R3"),
        "R1_vs_R4": paired_arms(ok, "R1", "R4"),
        "R1_vs_R0": paired_arms(ok, "R1", "R0"),
        "R2_same_tokens_as_R1": sum(r["R2"]["same_tokens_as_R1"] for r in ok),
        "R1_input_one_token_ms_median": {
            "warm": round(statistics.median(warm), 1) if warm else None,
            "cold": round(statistics.median(cold), 1) if cold else None,
        },
        "follow_on_first_draft_passed": {a: f"{sum(v)}/{len(v)}" for a, v in follow.items()},
    }


def attention_report(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    def pairs(
        get: Callable[[Mapping[str, Any]], tuple[float, float] | None],
    ) -> list[tuple[float, float]]:
        return [p for r in rows if (p := get(r)) is not None]

    def fidelity(context: str, part: str) -> str:
        hit = sum(r[context][part]["top1_match"] for r in rows)
        total = sum(r[context][part]["tokens"] for r in rows)
        return f"{hit}/{total} ({hit / total:.1%})" if total else "0/0"

    out: dict[str, Any] = {
        "states": len(rows),
        "replay_fidelity": {
            "X_after_committed": fidelity("none", "X"),
            "S_after_inserted_turn": fidelity("inserted", "S"),
            "N_after_inserted_turn": fidelity("inserted", "N"),
        },
        "logP_S_inserted_vs_none": sign_test(
            pairs(lambda r: (r["inserted"]["S"]["logp"], r["none"]["S"]["logp"]))
        ),
        "logP_X_inserted_vs_none": sign_test(
            pairs(lambda r: (r["inserted"]["X"]["logp"], r["none"]["X"]["logp"]))
        ),
        "logP_S_inserted_vs_top": sign_test(
            pairs(lambda r: (r["inserted"]["S"]["logp"], r["top"]["S"]["logp"]))
        ),
    }
    for part in ("S", "N"):
        for name, layers in LAYERS.items():

            def get(
                r: Mapping[str, Any], p: str = part, ly: slice = layers, other: str = "none"
            ) -> tuple[float, float] | None:
                if not r["inserted"][p]["attention"]:
                    return None
                return share(r["inserted"][p], PROVISION, ly), share(r[other][p], PROVISION, ly)

            out[f"provision_share_{part}_inserted_vs_none_layers_{name}"] = sign_test(pairs(get))
        components = {
            f"{ctx}:{span}": statistics.median(
                share(r[ctx][part], [span], LAYERS["all"])
                for r in rows
                if r[ctx][part]["attention"]
            )
            for ctx, span in (
                ("none", "inserted_windows"),
                ("inserted", "inserted_windows"),
                ("inserted", "inserted_copy"),
                ("none", "other_windows"),
                ("inserted", "other_windows"),
                ("top", "top_copy"),
            )
            if any(r[ctx][part]["attention"] for r in rows)
        }
        out[f"median_share_{part}_by_span"] = {k: round(v, 6) for k, v in components.items()}
    out["provision_share_S_inserted_vs_top_layers_all"] = sign_test(
        pairs(
            lambda r: (
                share(r["inserted"]["S"], PROVISION, LAYERS["all"]),
                share(r["top"]["S"], PROVISION, LAYERS["all"]),
            )
        )
    )
    return out


def strip(record: dict[str, Any]) -> dict[str, Any]:
    """The record without the prompt-side token ids (they encode statute text from ``data/``)."""
    replay = record.get("replay")
    if not replay:
        return record
    dropped = {"prompt", "committed", "note", "prompt_top"}
    kept = {k: v for k, v in replay.items() if k not in dropped}
    return {**record, "replay": kept}


def main() -> None:
    raw = OUT / "sglang.jsonl"  # git-ignored: full token ids, needed only by the attention phase
    if raw.exists():
        lines = raw.read_text(encoding="utf-8").splitlines()
        stripped = (json.dumps(strip(json.loads(x)), ensure_ascii=False) + "\n" for x in lines)
        (OUT / "arms.jsonl").write_text("".join(stripped), encoding="utf-8")
    records = [json.loads(x) for x in (OUT / "arms.jsonl").read_text(encoding="utf-8").splitlines()]
    report: dict[str, Any] = {"arms": arms_report(records)}
    attention_path = OUT / "attention.jsonl"
    if attention_path.exists():
        rows = [json.loads(x) for x in attention_path.read_text(encoding="utf-8").splitlines()]
        report["attention"] = attention_report(rows)
        att = report["attention"]
        report["primary"] = holm(
            {
                "R1_vs_R3": report["arms"]["R1_vs_R3"]["p"],
                "R1_vs_R4": report["arms"]["R1_vs_R4"]["p"],
                "provision_share_S": att["provision_share_S_inserted_vs_none_layers_all"]["p"],
                "logP_S": att["logP_S_inserted_vs_none"]["p"],
                "logP_X": att["logP_X_inserted_vs_none"]["p"],
            }
        )
    (OUT / "report.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
