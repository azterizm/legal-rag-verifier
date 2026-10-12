"""Stops 52 and 53: the claim check's false rollbacks, and a judge shown the question and the
source as written (docs/GRID.md § Stops 52 and 53). Three judges only: Opus 5.5, Gemini 3.1 Pro
and the untrained Qwen 27B.

Units are the segmenter's sentences since stop 52 (a list number stays with its item), graded
from your sheet (``fresh_eval.merged_grades``). New labels go to their own files, so the reports
of stops 47 to 51 reproduce from the files they were scored from.

  uv run python scripts/fresh_arms.py requests        # prompts per set and how many lack a label
  uv run python scripts/fresh_arms.py label opus55    # router: stop 42 prompts not yet labelled
  uv run python scripts/fresh_arms.py label pro
  uv run --with modal modal run scripts/modal_distill.py::fresh_arms   # Qwen 27B, three prompts
  uv run python scripts/fresh_arms.py report          # → results/fresh_arms/report.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import auditor_judge as aj  # type: ignore[import-not-found]  # noqa: E402
import fresh_battery as fb  # type: ignore[import-not-found]  # noqa: E402
import fresh_eval as fe  # type: ignore[import-not-found]  # noqa: E402
import fresh_report as fr  # type: ignore[import-not-found]  # noqa: E402

import legal_rag_verifier.verifier as verifier_module  # noqa: E402
from legal_rag_verifier.premise import Premise  # noqa: E402
from legal_rag_verifier.verifier import Verifier  # noqa: E402

OUT = ROOT / "results" / f"{fb.SET}_arms"
QWEN = "qwen27-nothink"
#: judge name (its label files) → the router teacher that labels it, or None for Modal.
JUDGES: dict[str, str | None] = {"opus55": "opus55", "gemini-pro-low": "pro", QWEN: None}
PROMPTS = ("p42", "view", "rule", "notes2", "notes3")  # stop 42's, stop 53's two, stop 54's two
NOTES = ("notes2", "notes3")
ARMS = ("list fix", "figures to the judge", "no claim check")
FIGURE_ONLY = frozenset({"UNGROUNDED_FIGURE"})
OPUS_STOP = 16.0  # the Opus 5.5 ledger stops here (stop 52: 13.0; stop 56: 16.0, GRID)
ALPHA = 0.05
#: Stop 55: the same Qwen 27B at three precisions (label → the name of its label files).
QUANT = {"FP8, official": QWEN, "AMD AWQ, 4-bit": "qwen27-awq4", "AutoRound, 4-bit": "qwen27-ar4"}
SEQUENTIAL = 40  # prompts timed one at a time
MARGIN = 0.015  # stop 55: a 4-bit model within this of FP8, and not told apart, costs little

_LABELS = """Labels:
- "supported": the source states the sentence, or the sentence follows from the source by \
reasoning, such as applying a default, substituting a definition, following a reference to another \
part of the source, converting units or doing arithmetic.
- "contradicted": the source states or implies something incompatible with the sentence, such as \
a different figure, condition, scope or outcome.
- "not_stated": neither. Use this when the sentence may be true but the source does not establish \
it.

"""
_RULE = (
    'Judge every claim in the sentence: it is "supported" only if all of them are. A sentence '
    'that makes no claim, such as a link, a refusal or a list number, is "supported" unless it '
    "misstates the source.\n\n"
)
VIEW_USER = """Question the answer responds to. It is context, not evidence.
<<<
{question}
>>>

Source:
{source}

Answer so far. Use it only to work out what words such as "it" or "this" refer to. It is not \
evidence.
<<<
{prefix}
>>>

Sentence to check:
<<<
{sentence}
>>>

{labels}Return JSON with keys "label" (one of the three), "passage" (0) and "reason" (one \
sentence)."""

VIEW_SHA = hashlib.sha256((aj.SYSTEM + VIEW_USER + _LABELS + _RULE).encode()).hexdigest()


def view_prompt(kind: str, sentence: str, source: str, question: str, prefix: str) -> str:
    """The judge's prompt with the question and the source as written. ``rule`` adds your
    grading rule to the labels of ``view``."""
    labels = _LABELS + (_RULE if kind == "rule" else "")
    return VIEW_USER.format(
        question=question,
        source=source,
        prefix=prefix or "(none)",
        sentence=sentence,
        labels=labels,
    )


_NOTES = """How to apply the labels:
- The passages need not repeat what any reader of them already knows. A sentence is still \
"supported" when it adds only common background, such as what a standard term means, or names what \
the passages are plainly about, such as the Act, the country, the product or the standard.
- A sentence that simplifies the passages by leaving out a condition or an exception is still \
"supported" if what it does say is correct. Use "contradicted" only when the sentence says \
something the passages make false.
"""
_HEDGE = """- A hedged or general sentence ("may", "typically", "in some cases") still needs \
support. If the passages do not establish it, it is "not_stated".
"""
NOTES_SHA = hashlib.sha256((aj.SYSTEM + aj.USER + _NOTES + _HEDGE).encode()).hexdigest()
# Stop 58: stop 53's paragraph on the stop 42 prompt ("the passages" for "the source").
_REFUSAL = _RULE.replace("misstates the source", "misstates the passages")
INSERTS = {"notes2": _NOTES, "notes3": _NOTES + _HEDGE, "refusal": _REFUSAL.rstrip("\n") + "\n"}
REFUSAL_SHA = hashlib.sha256((aj.SYSTEM + aj.USER + _REFUSAL).encode()).hexdigest()


def notes_prompt(kind: str, sentence: str, candidates: Sequence[str], prefix: str) -> str:
    """The stop 42 prompt with notes on how to apply the labels, before the reply format.
    ``notes3`` adds the note on hedged sentences to the two of ``notes2``."""
    head, tail = aj.user_prompt(sentence, candidates, prefix).rsplit("Return JSON", 1)
    return f"{head}{INSERTS[kind]}\nReturn JSON{tail}"


# Stop 61: the stop 42 prompt asking for no reason. Only its last sentence differs.
_REPLY = aj.USER[aj.USER.index("Return JSON") :]
SHORT_REPLY = (
    'Return JSON with keys "label" (one of the three) and "passage" (the number of the passage '
    "that decides it, or 0). Give no reason."
)
SHORT_SHA = hashlib.sha256((aj.SYSTEM + aj.USER.replace(_REPLY, SHORT_REPLY)).encode()).hexdigest()


def short_prompt(sentence: str, candidates: Sequence[str], prefix: str) -> str:
    head, _ = aj.user_prompt(sentence, candidates, prefix).rsplit("Return JSON", 1)
    return str(head) + SHORT_REPLY


def prompt(
    kind: str, clause: str, candidates: Sequence[str], unit: Mapping[str, Any], source: str
) -> str:
    if kind == "p42":
        return str(aj.user_prompt(clause, candidates, unit["prefix"]))
    if kind == "short":
        return short_prompt(clause, candidates, unit["prefix"])
    if kind in INSERTS:
        return notes_prompt(kind, clause, candidates, unit["prefix"])
    return view_prompt(kind, clause, source, unit["query"], unit["prefix"])


@contextmanager
def no_claims() -> Iterator[None]:
    """The verifier with the claim check off: no claim is read from the sentence or the
    question, so the sentence goes to the entailment check."""
    keep = verifier_module.__dict__["extract_claims"]
    verifier_module.__dict__["extract_claims"] = lambda _text: []
    try:
        yield
    finally:
        verifier_module.__dict__["extract_claims"] = keep


def recorded() -> dict[str, Any]:
    """Merged units, their premises, the clause calls on the normal path, and for the sentences
    the claim check rolls back: its reasons and the calls with the claim check off."""
    us, built, rec = fe.recorded(merged=True)
    held = [u for u, r in zip(us, rec, strict=True) if r["claim_rollback"]]
    reasons = {}
    for u in held:
        v = Verifier(aj.RecordingScorer()).check_sentence(
            built[u["key"]], u["sentence"], query=u["query"]
        )
        reasons[u["key"]] = sorted(r.name for r in v.reasons)
    with no_claims():
        free = aj.record(held, built)
    rows = {r["id"]: r for r in fb.rows()}
    sources = {u["key"]: fb.source_text(rows[u["id"]]) for u in us}
    return {
        "units": us,
        "built": built,
        "calls": {r["key"]: r for r in rec},
        "free": {r["key"]: r for r in free},
        "reasons": reasons,
        "sources": sources,
    }


def requests(kind: str, data: Mapping[str, Any] | None = None) -> dict[str, str]:
    """Every prompt of one kind, ``{sha: user prompt}``: the clauses on the normal path and the
    clauses of the held sentences with the claim check off."""
    data = data or recorded()
    if kind.startswith("seq"):  # an even spread of the prompts, for timing one at a time
        # "seq" and "seq-again": the stop 42 prompt; "seq-short": the same clauses, short reply
        base = "short" if kind == "seq-short" else "p42"
        items = list(requests(base, data).items())
        return dict(items[:: max(len(items) // SEQUENTIAL, 1)][:SEQUENTIAL])
    out: dict[str, str] = {}
    for u in data["units"]:
        key = u["key"]
        for r in (data["calls"][key], data["free"].get(key)):
            for clause, candidates in (r or {}).get("calls", []):
                user = prompt(kind, clause, candidates, u, data["sources"][key])
                out[aj.prompt_key(user)] = user
    if kind in ("p42", "short") or kind in INSERTS:
        fe.assert_blind(data["units"], out)
    return out


def path(judge: str, kind: str) -> Path:
    return Path(fe.LABELS) / f"{judge}.{'arms' if kind == 'p42' else kind}.jsonl"


def read(judge: str, kind: str) -> dict[str, dict[str, Any]]:
    """Valid labels of one judge for one prompt; for the stop 42 prompt, the labels of stops
    47 to 51 and the ones added here."""
    out: dict[str, dict[str, Any]] = dict(fe.read(judge)) if kind == "p42" else {}
    file = path(judge, kind)
    if file.exists():
        out |= {r["sha"]: r for r in map(json.loads, file.read_text("utf-8").splitlines())}
    return {k: v for k, v in out.items() if v["label"] in aj.LABELS}


def todo(judge: str, kind: str, asked: Mapping[str, str]) -> dict[str, str]:
    have = read(judge, kind)
    return {k: v for k, v in asked.items() if k not in have}


class Scorer:
    """A judge's labels in DeBERTa's place, for either prompt. ``unit`` is set per sentence."""

    def __init__(
        self,
        name: str,
        kind: str,
        labels: Mapping[str, Mapping[str, Any]],
        sources: Mapping[str, str],
    ) -> None:
        self.model_id = f"{name}/{kind}"
        self.kind = kind
        self.labels = labels
        self.sources = sources
        self.unit: Mapping[str, Any] = {}
        self.missing = 0

    def score(self, premises: Sequence[str], hypothesis: str) -> list[Any]:
        u = self.unit
        user = prompt(self.kind, hypothesis, premises, u, self.sources.get(u["key"], ""))
        label = self.labels.get(aj.prompt_key(user))
        if label is None:  # no valid label after the reruns: counted as not stated
            self.missing += 1
            return list(aj.one_hot("not_stated", 0, len(premises)))
        passage = label["passage"] if self.kind in ("p42", "short", *INSERTS) else 0
        return list(aj.one_hot(label["label"], passage, len(premises)))


def replay(
    us: Sequence[Mapping[str, Any]],
    built: Mapping[str, Premise],
    scorer: Scorer,
    free: frozenset[str] | set[str],
    config: Any = aj.STRICT,
) -> dict[str, dict[str, Any]]:
    """Strict placement. A sentence in ``free`` is checked with the claim check off."""
    verifier = Verifier(scorer, config)
    out = {}
    for u in us:
        scorer.unit = u
        if u["key"] in free:
            with no_claims():
                v = verifier.check_sentence(built[u["key"]], u["sentence"], query=u["query"])
        else:
            v = verifier.check_sentence(built[u["key"]], u["sentence"], query=u["query"])
        out[u["key"]] = {"verdict": v.verdict.name, "reasons": [r.name for r in v.reasons]}
    return out


def free_sets(data: Mapping[str, Any]) -> dict[str, set[str]]:
    held = data["reasons"]
    return {
        "list fix": set(),
        "figures to the judge": {k for k, rs in held.items() if set(rs) <= FIGURE_ONLY},
        "no claim check": set(held),
    }


def sign_test(only_a: int, only_b: int) -> float:
    from teacher_pro import sign_test as exact  # type: ignore[import-not-found]  # noqa: PLC0415

    return float(exact(only_a, only_b))


def paired(a: Mapping[str, bool], b: Mapping[str, bool]) -> dict[str, Any]:
    only_a = sum(a[k] and not b[k] for k in a)
    only_b = sum(b[k] and not a[k] for k in a)
    return {
        "only_first": only_a,
        "only_second": only_b,
        "p": float(f"{sign_test(only_a, only_b):.3g}"),
    }


def report() -> None:  # noqa: PLR0912 - one pass over the readings
    data = recorded()
    us, built = data["units"], data["built"]
    graded = fe.merged_grades(us)
    units = [
        {**u, "right": graded[u["key"]] == "yes", "wrong": graded[u["key"]] == "no"} for u in us
    ]
    units = [u for u in units if u["right"] or u["wrong"]]
    sets = free_sets(data)
    held = data["reasons"]
    out: dict[str, Any] = {
        "units": len(units),
        "right": sum(u["right"] for u in units),
        "wrong": sum(u["wrong"] for u in units),
        "held_by_claim_check": {
            "sentences": len(held),
            "right": sum(u["right"] for u in units if u["key"] in held),
            "wrong": sum(u["wrong"] for u in units if u["key"] in held),
            "figure_only": len(sets["figures to the judge"]),
            "figure_only_right": sum(
                u["right"] for u in units if u["key"] in sets["figures to the judge"]
            ),
            "figure_only_wrong": sum(
                u["wrong"] for u in units if u["key"] in sets["figures to the judge"]
            ),
        },
        "view_prompt_sha256": VIEW_SHA,
        "notes_prompt_sha256": NOTES_SHA,
        "arms": {},
        "held_as_judged": {},
        "no_valid_label": {},
        "paired": {},
        "latency": {},
    }
    correct: dict[str, dict[str, bool]] = {}
    for judge in JUDGES:
        for kind in PROMPTS if judge == QWEN else ("p42",):
            labels = read(judge, kind)
            asked = requests(kind, data)
            out["no_valid_label"][f"{judge} {kind}"] = sum(k not in labels for k in asked)
            for arm in ARMS:
                scorer = Scorer(judge, kind, labels, data["sources"])
                verdicts = replay(us, built, scorer, sets[arm])
                name = f"{judge} | {kind} | {arm}"
                out["arms"][name] = fr.score(units, verdicts)
                correct[name] = {
                    u["key"]: fr._rolled(verdicts[u["key"]]) == u["wrong"] for u in units
                }
                if arm == "no claim check":  # what the judge does with the held sentences
                    kept = [u for u in units if u["key"] in held]
                    out["held_as_judged"][f"{judge} | {kind}"] = {
                        "right_passed": sum(
                            u["right"] and not fr._rolled(verdicts[u["key"]]) for u in kept
                        ),
                        "wrong_caught": sum(
                            u["wrong"] and fr._rolled(verdicts[u["key"]]) for u in kept
                        ),
                    }
            if kind != "p42" or judge == QWEN:
                file = path(judge, kind)
                if file.exists():
                    rows = [json.loads(x) for x in file.read_text("utf-8").splitlines()]
                    out["latency"][f"{judge} {kind} (bulk)"] = aj.latency(rows)
    for judge in JUDGES:
        base = f"{judge} | p42 | list fix"
        for arm in ARMS[1:]:
            name = f"{judge} | p42 | {arm}"
            out["paired"][f"{name} vs list fix"] = paired(correct[name], correct[base])
    for kind in PROMPTS[1:]:
        for arm in ARMS:
            a, b = f"{QWEN} | {kind} | {arm}", f"{QWEN} | p42 | {arm}"
            out["paired"][f"{a} vs p42"] = paired(correct[a], correct[b])
    for arm in ARMS:
        a, b = f"{QWEN} | rule | {arm}", f"{QWEN} | view | {arm}"
        out["paired"][f"{a} vs view"] = paired(correct[a], correct[b])
        a, b = f"{QWEN} | notes3 | {arm}", f"{QWEN} | notes2 | {arm}"
        out["paired"][f"{a} vs notes2"] = paired(correct[a], correct[b])
    for judge in JUDGES:  # the frontier judges against the untrained Qwen 27B, same arm
        if judge == QWEN:
            continue
        for arm in ARMS[:2]:
            a, b = f"{judge} | p42 | {arm}", f"{QWEN} | p42 | {arm}"
            out["paired"][f"{a} vs {QWEN}"] = paired(correct[a], correct[b])
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: out[k] for k in ("units", "right", "wrong", "held_by_claim_check")}))
    for name, s in out["arms"].items():
        cells = "  ".join(
            f"{g}: {s[g]['false_rollbacks']}/{s[g]['caught']} {s[g]['accuracy']}"
            for g in ("software", "statutes", "source answers", "closed answers", "total")
        )
        print(f"{name:52} {cells}")
    keys = ("held_as_judged", "no_valid_label", "paired", "latency")
    print(json.dumps({k: out[k] for k in keys}, indent=1))


def quant() -> None:
    """Stop 55: each precision on the same prompts, against FP8. → results/fresh_arms/quant.json"""
    data = recorded()
    us, built = data["units"], data["built"]
    graded = fe.merged_grades(us)
    units = [
        {**u, "right": graded[u["key"]] == "yes", "wrong": graded[u["key"]] == "no"} for u in us
    ]
    units = [u for u in units if u["right"] or u["wrong"]]
    configs = {"list fix": aj.STRICT, "figures to the judge": aj.STRICT_FIGURES}
    out: dict[str, Any] = {"units": len(units), "arms": {}, "against_fp8": {}, "labels": {}}
    out |= {"no_valid_label": {}, "latency_one_at_a_time": {}}
    correct: dict[str, dict[str, bool]] = {}
    for kind in ("p42", "notes2"):
        asked = requests(kind, data)
        base = read(QWEN, kind)
        for title, name in QUANT.items():
            labels = read(name, kind)
            if not labels:  # the server could not load these weights (GRID § Stop 55)
                out["not_served"] = sorted({*out.get("not_served", []), title})
                continue
            out["no_valid_label"][f"{title} | {kind}"] = sum(k not in labels for k in asked)
            both = [k for k in asked if k in labels and k in base]
            out["labels"][f"{title} | {kind}"] = {
                "same_as_fp8": sum(labels[k]["label"] == base[k]["label"] for k in both),
                "of": len(both),
            }
            for arm, config in configs.items():
                scorer = Scorer(name, kind, labels, data["sources"])
                verdicts = replay(us, built, scorer, set(), config)
                key = f"{title} | {kind} | {arm}"
                out["arms"][key] = fr.score(units, verdicts)
                correct[key] = {
                    u["key"]: fr._rolled(verdicts[u["key"]]) == u["wrong"] for u in units
                }
        for title in list(QUANT)[1:]:
            for arm in configs:
                a, b = f"{title} | {kind} | {arm}", f"{next(iter(QUANT))} | {kind} | {arm}"
                if a not in correct:
                    continue
                test = paired(correct[a], correct[b])
                drop = out["arms"][b]["total"]["accuracy"] - out["arms"][a]["total"]["accuracy"]
                test["costs_little"] = bool(drop <= MARGIN and test["p"] >= ALPHA)
                out["against_fp8"][a] = test
    for name in [*QUANT.values(), *(f"{n}-l4" for n in list(QUANT.values())[1:])]:
        file = path(name, "seq")
        if file.exists():
            rows = [json.loads(x) for x in file.read_text("utf-8").splitlines()]
            out["latency_one_at_a_time"][name] = aj.latency(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "quant.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    for key, s in out["arms"].items():
        t = s["total"]
        print(f"{key:52} {t['false_rollbacks']}/{t['caught']} {t['accuracy']}")
    keys = ("against_fp8", "labels", "no_valid_label", "latency_one_at_a_time")
    print(json.dumps({k: out[k] for k in keys}, indent=1))


def wilson(right: int, n: int, z: float = 1.96) -> list[float]:
    """Wilson 95 % interval for a share."""
    if n == 0:
        return [0.0, 1.0]
    p = right / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / (1 + z * z / n)
    return [round(centre - half, 3), round(centre + half, 3)]


def confirm() -> None:  # noqa: PLR0915 - one pass over the readings
    """Stop 56, readings P1 to P5, scored once from the committed labels and your grades.
    → results/<set>_arms/confirm.json"""
    data = recorded()
    us, built = data["units"], data["built"]
    graded = fe.merged_grades(us)
    if any(g not in {"yes", "no", "unsure"} for g in graded.values()):
        raise SystemExit("grades.csv is not filled in yet")
    units = [
        {**u, "right": graded[u["key"]] == "yes", "wrong": graded[u["key"]] == "no"} for u in us
    ]
    units = [u for u in units if u["right"] or u["wrong"]]
    held = data["reasons"]
    out: dict[str, Any] = {
        "set": fb.SET,
        "sentences": len(us),
        "graded": len(units),
        "right": sum(u["right"] for u in units),
        "wrong": sum(u["wrong"] for u in units),
        "unsure": sum(g == "unsure" for g in graded.values()),
        "held_by_claim_check": {
            "right": sum(u["right"] for u in units if u["key"] in held),
            "wrong": sum(u["wrong"] for u in units if u["key"] in held),
        },
        "arms": {},
        "no_valid_label": {},
        "held_as_judged": {},
    }
    correct: dict[str, dict[str, bool]] = {}

    def arm(judge: str, kind: str, config: Any, name: str) -> bool:
        labels = read(judge, kind)
        missing = sum(k not in labels for k in requests(kind, data))
        if missing == len(requests(kind, data)):
            return False  # this judge did not label this prompt on this set
        out["no_valid_label"][f"{judge} {kind}"] = missing
        verdicts = replay(us, built, Scorer(judge, kind, labels, data["sources"]), set(), config)
        score = fr.score(units, verdicts)
        total = score["total"]
        hits = total["right"] - total["false_rollbacks"] + total["caught"]
        total["interval_95"] = wilson(hits, total["right"] + total["wrong"])
        out["arms"][name] = score
        correct[name] = {u["key"]: fr._rolled(verdicts[u["key"]]) == u["wrong"] for u in units}
        return True

    # P1 and P2: the configuration under test against the stop 47 configuration.
    p1 = "P1 qwen27 FP8 | notes2 | figures to the judge"
    base = "stop 47 configuration: qwen27 FP8 | stop 42 prompt | claim check"
    figures, notes = (
        "qwen27 FP8 | stop 42 prompt | figures to the judge",
        "qwen27 FP8 | notes2 | claim check",
    )
    arm(QWEN, "notes2", aj.STRICT_FIGURES, p1)
    arm(QWEN, "p42", aj.STRICT, base)
    test = paired(correct[p1], correct[base])
    gain = out["arms"][p1]["total"]["accuracy"] > out["arms"][base]["total"]["accuracy"]
    out["P2"] = {**test, "confirmed": bool(gain and test["p"] < ALPHA)}
    # P3: each change alone.
    arm(QWEN, "p42", aj.STRICT_FIGURES, figures)
    arm(QWEN, "notes2", aj.STRICT, notes)
    out["P3"] = {
        "figures to the judge alone": paired(correct[figures], correct[base]),
        "notes2 alone": paired(correct[notes], correct[base]),
    }
    # P4: the other judges in the P1 configuration, each against Qwen 27B FP8.
    out["P4"] = {}
    for judge in ("opus55", "gemini-pro-low", *list(QUANT.values())[1:]):
        name = f"{judge} | notes2 | figures to the judge"
        if arm(judge, "notes2", aj.STRICT_FIGURES, name):
            out["P4"][name] = paired(correct[name], correct[p1])
    # P5: what each judge does with the sentences the claim check holds (claim check off).
    for judge in (QWEN, "opus55", "gemini-pro-low"):
        labels = read(judge, "notes2")
        if not labels:
            continue
        scorer = Scorer(judge, "notes2", labels, data["sources"])
        verdicts = replay(us, built, scorer, set(held))
        kept = [u for u in units if u["key"] in held]
        out["held_as_judged"][judge] = {
            "right_passed": sum(u["right"] and not fr._rolled(verdicts[u["key"]]) for u in kept),
            "wrong_caught": sum(u["wrong"] and fr._rolled(verdicts[u["key"]]) for u in kept),
        }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "confirm.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    for name, s in out["arms"].items():
        cells = "  ".join(
            f"{g}: {s[g]['false_rollbacks']}/{s[g]['caught']} {s[g]['accuracy']}"
            for g in ("software", "statutes", "source answers", "closed answers", "total")
        )
        print(f"{name:66} {cells}  {s['total']['interval_95']}")
    keys = ("graded", "right", "wrong", "unsure", "held_by_claim_check", "P2", "P3", "P4")
    print(json.dumps({k: out[k] for k in (*keys, "held_as_judged", "no_valid_label")}, indent=1))


TABLE_JUDGES = (
    ("qwen27-ar4", "p42"),
    ("qwen27-ar4", "notes2"),
    ("gemini-pro-low", "notes2"),
    ("qwen27-ar4", "rule"),  # stop 58; a column is written only where the labels exist
    ("qwen27-ar4", "refusal"),
)
# A refusal or a request for context, as Qwen 27B words them closed-book. Written after stop 57's
# scoring, for the reading added there; it scores nothing by itself.
REFUSAL = re.compile(r"\b(I do not (know|have)|Please (specify|provide)|If you are asking about)\b")


def table() -> None:
    """Stop 57: one row per graded sentence of this set, with its grade and whether each judge
    rolls it back, for ``scripts/self_judge.py``. → results/<set>_arms/table.json"""
    import fresh_grader as fg  # type: ignore[import-not-found]  # noqa: PLC0415

    data = recorded()
    us, built = data["units"], data["built"]
    graded = fe.merged_grades(us)
    key = json.loads((fe.OUT / "key.json").read_text(encoding="utf-8"))
    settled = {
        f"{key[item]['id']}:{key[item]['mode']}:{key[item]['sentence']}": v.get("grade")
        for item, v in fg.consensus().items()
    }
    rows = {
        u["key"]: {
            "id": u["id"],
            "mode": u["mode"],
            "domain": u["domain"],
            "grade": graded[u["key"]],
            "refusal": bool(REFUSAL.search(u["sentence"])),
            # the two graders' grade where they settle it; your grade is used for the rest
            "graders": settled.get(u["key"]),
        }
        for u in us
    }
    missing = {}
    for judge, kind in TABLE_JUDGES:
        labels = read(judge, kind)
        if not labels:
            continue
        missing[f"{judge} {kind}"] = sum(k not in labels for k in requests(kind, data))
        for name, config in (("figures", aj.STRICT_FIGURES), ("claim", aj.STRICT)):
            scorer = Scorer(judge, kind, labels, data["sources"])
            verdicts = replay(us, built, scorer, set(), config)
            for u in us:
                rows[u["key"]][f"{judge}|{kind}|{name}"] = fr._rolled(verdicts[u["key"]])
    OUT.mkdir(parents=True, exist_ok=True)
    out = {"set": fb.SET, "no_valid_label": missing, "rows": rows}
    (OUT / "table.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"set": fb.SET, "sentences": len(rows), "no_valid_label": missing}))


def v0() -> None:
    """Stop 60: V0 (the claim check and DeBERTa) on this set, scored as in stop 47, beside the
    Qwen 27B judge. Your grades. → results/<set>_arms/v0.json"""
    graded = fe.grades()
    us, built, _ = fe.recorded()
    units = [
        {**u, "right": graded[u["key"]] == "yes", "wrong": graded[u["key"]] == "no"} for u in us
    ]
    units = [u for u in units if u["right"] or u["wrong"]]
    table = json.loads((fe.OUT / "scores/v0.json").read_text(encoding="utf-8"))
    first = aj.replay(us, built, aj.TableScorer("v0", table))
    arms: dict[str, dict[str, dict[str, Any]]] = {"V0 (claim check and DeBERTa)": first}
    arms["claim check only"] = {
        k: {"verdict": "EMIT", "reasons": []} if set(v["reasons"]) <= aj.NLI_REASONS else v
        for k, v in first.items()
    }
    arms["no auditor"] = {k: {"verdict": "EMIT", "reasons": []} for k in first}
    judges = {
        "Qwen 27B FP8, stop 47 configuration": (QWEN, aj.STRICT),
        "Qwen 27B FP8, figures to the judge": (QWEN, aj.STRICT_FIGURES),
        "Qwen 27B 4-bit, figures to the judge": ("qwen27-ar4", aj.STRICT_FIGURES),
    }
    sources: dict[str, str] = {}
    for title, (judge, config) in judges.items():
        labels = read(judge, "p42")
        if labels:
            arms[title] = replay(us, built, Scorer(judge, "p42", labels, sources), set(), config)
    correct = {
        name: {u["key"]: fr._rolled(v[u["key"]]) == u["wrong"] for u in units}
        for name, v in arms.items()
    }
    out: dict[str, Any] = {"set": fb.SET, "sentences": len(units), "arms": {}, "against_v0": {}}
    for name, verdicts in arms.items():
        score = fr.score(units, verdicts)
        total = score["total"]
        hits = total["right"] - total["false_rollbacks"] + total["caught"]
        total["interval_95"] = wilson(hits, len(units))
        out["arms"][name] = score
    base = next(iter(arms))
    for title in judges:
        if title in arms:
            test = paired(correct[title], correct[base])
            gain = out["arms"][title]["total"]["accuracy"] > out["arms"][base]["total"]["accuracy"]
            out["against_v0"][title] = {**test, "better_than_v0": bool(gain and test["p"] < ALPHA)}
    meta = fe.OUT / "scores/v0.meta.json"
    if meta.exists():
        out["v0_run"] = json.loads(meta.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "v0.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    for name, s in out["arms"].items():
        cells = "  ".join(
            f"{g}: {s[g]['false_rollbacks']}/{s[g]['caught']} {s[g]['accuracy']}"
            for g in ("software", "statutes", "source answers", "closed answers", "total")
        )
        print(f"{name:42} {cells}  {s['total']['interval_95']}")
    print(json.dumps({k: out[k] for k in ("against_v0", "v0_run") if k in out}, indent=1))


def short(judge: str = "qwen27-ar4") -> None:
    """Stop 61: the reply without a reason against the stop 42 prompt, on this set and your
    grades. → results/<set>_arms/short.json"""
    data = recorded()
    us, built = data["units"], data["built"]
    graded = fe.merged_grades(us)
    units = [
        {**u, "right": graded[u["key"]] == "yes", "wrong": graded[u["key"]] == "no"} for u in us
    ]
    units = [u for u in units if u["right"] or u["wrong"]]
    out: dict[str, Any] = {"set": fb.SET, "judge": judge, "prompt_sha256": SHORT_SHA}
    out |= {"sentences": len(units), "arms": {}, "against_stop_42_prompt": {}, "time": {}}
    labels = {kind: read(judge, kind) for kind in ("p42", "short")}
    asked = {kind: requests(kind, data) for kind in labels}
    out["no_valid_label"] = {k: sum(s not in labels[k] for s in asked[k]) for k in labels}
    pairs = list(zip(asked["p42"], asked["short"], strict=True))  # same clauses, same order
    both = [(a, b) for a, b in pairs if a in labels["p42"] and b in labels["short"]]
    out["W1_same_label"] = {
        "same": sum(labels["p42"][a]["label"] == labels["short"][b]["label"] for a, b in both),
        "of": len(both),
    }
    correct: dict[str, dict[str, bool]] = {}
    for arm, config in (("figures to the judge", aj.STRICT_FIGURES), ("claim check", aj.STRICT)):
        for kind, table in labels.items():
            scorer = Scorer(judge, kind, table, data["sources"])
            verdicts = replay(us, built, scorer, set(), config)
            name = f"{kind} | {arm}"
            out["arms"][name] = fr.score(units, verdicts)["total"]
            correct[name] = {u["key"]: fr._rolled(verdicts[u["key"]]) == u["wrong"] for u in units}
        test = paired(correct[f"short | {arm}"], correct[f"p42 | {arm}"])
        drop = out["arms"][f"p42 | {arm}"]["accuracy"] - out["arms"][f"short | {arm}"]["accuracy"]
        out["against_stop_42_prompt"][arm] = {
            **test,
            "change_in_points": round(-100 * drop, 1),
            "costs_nothing": bool(drop <= MARGIN),
        }
    for kind in ("seq-again", "seq-short"):
        file = path(judge, kind)
        if file.exists():
            rows = [json.loads(x) for x in file.read_text("utf-8").splitlines()]
            out["time"][kind] = aj.latency([r for r in rows if r["label"] in aj.LABELS])
    if len(out["time"]) == 2:  # noqa: PLR2004
        ratio = out["time"]["seq-short"]["p50_ms"] / out["time"]["seq-again"]["p50_ms"]
        out["time"]["short_over_stop_42_p50"] = round(ratio, 2)
        out["time"]["saves_time"] = bool(ratio <= 2 / 3)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "short.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1))


def label(judge: str, kind: str = "p42") -> None:
    import router  # type: ignore[import-not-found]  # noqa: PLC0415
    import teachers  # type: ignore[import-not-found]  # noqa: PLC0415

    teacher = JUDGES[judge]
    if teacher is None:
        raise SystemExit(f"{judge} is labelled on Modal")
    router.CAPS[router.OPUS55] = min(router.CAPS[router.OPUS55], OPUS_STOP)
    asked = todo(judge, kind, requests(kind))
    teachers.label_clauses(f"{judge}.{kind}", teacher, asked, path(judge, kind))
    print(json.dumps(router.ledger().get(teachers.TEACHERS[teacher], {})))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=["requests", "label", "report", "quant", "confirm", "table", "v0", "short"],
    )
    parser.add_argument("judge", nargs="?", choices=[j for j, t in JUDGES.items() if t])
    parser.add_argument("--kind", default="p42", choices=PROMPTS)
    args = parser.parse_args()
    if args.command == "report":
        report()
    elif args.command == "quant":
        quant()
    elif args.command == "confirm":
        confirm()
    elif args.command == "table":
        table()
    elif args.command == "v0":
        v0()
    elif args.command == "short":
        short()
    elif args.command == "label":
        label(args.judge, args.kind)
    else:
        data = recorded()
        for kind in PROMPTS:
            asked = requests(kind, data)
            missing = {j: len(todo(j, kind, asked)) for j in JUDGES if kind == "p42" or j == QWEN}
            print(kind, len(asked), "prompts; to label:", missing)
        sets = free_sets(data)
        print({k: len(v) for k, v in sets.items()})


if __name__ == "__main__":
    main()
