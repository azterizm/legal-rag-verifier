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

OUT = ROOT / "results/fresh_arms"
QWEN = "qwen27-nothink"
#: judge name (its label files) → the router teacher that labels it, or None for Modal.
JUDGES: dict[str, str | None] = {"opus55": "opus55", "gemini-pro-low": "pro", QWEN: None}
PROMPTS = ("p42", "view", "rule")  # the stop 42 prompt and the two of stop 53
ARMS = ("list fix", "figures to the judge", "no claim check")
FIGURE_ONLY = frozenset({"UNGROUNDED_FIGURE"})
OPUS_STOP = 13.0  # the Opus 5.5 ledger stops here for stop 52 (GRID)
ALPHA = 0.05

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
    out: dict[str, str] = {}
    for u in data["units"]:
        key = u["key"]
        for r in (data["calls"][key], data["free"].get(key)):
            for clause, candidates in (r or {}).get("calls", []):
                if kind == "p42":
                    user = aj.user_prompt(clause, candidates, u["prefix"])
                else:
                    user = view_prompt(kind, clause, data["sources"][key], u["query"], u["prefix"])
                out[aj.prompt_key(user)] = user
    if kind == "p42":
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
        if self.kind == "p42":
            user = aj.user_prompt(hypothesis, premises, u["prefix"])
        else:
            user = view_prompt(
                self.kind, hypothesis, self.sources[u["key"]], u["query"], u["prefix"]
            )
        label = self.labels.get(aj.prompt_key(user))
        if label is None:  # no valid label after the reruns: counted as not stated
            self.missing += 1
            return list(aj.one_hot("not_stated", 0, len(premises)))
        passage = label["passage"] if self.kind == "p42" else 0
        return list(aj.one_hot(label["label"], passage, len(premises)))


def replay(
    us: Sequence[Mapping[str, Any]],
    built: Mapping[str, Premise],
    scorer: Scorer,
    free: frozenset[str] | set[str],
) -> dict[str, dict[str, Any]]:
    """Strict placement. A sentence in ``free`` is checked with the claim check off."""
    verifier = Verifier(scorer, aj.STRICT)
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


def report() -> None:
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
    for kind in ("view", "rule"):
        for arm in ARMS:
            a, b = f"{QWEN} | {kind} | {arm}", f"{QWEN} | p42 | {arm}"
            out["paired"][f"{a} vs p42"] = paired(correct[a], correct[b])
    for arm in ARMS:
        a, b = f"{QWEN} | rule | {arm}", f"{QWEN} | view | {arm}"
        out["paired"][f"{a} vs view"] = paired(correct[a], correct[b])
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


def label(judge: str) -> None:
    import router  # type: ignore[import-not-found]  # noqa: PLC0415
    import teachers  # type: ignore[import-not-found]  # noqa: PLC0415

    teacher = JUDGES[judge]
    if teacher is None:
        raise SystemExit(f"{judge} is labelled on Modal")
    router.CAPS[router.OPUS55] = min(router.CAPS[router.OPUS55], OPUS_STOP)
    asked = todo(judge, "p42", requests("p42"))
    teachers.label_clauses(f"{judge}.arms", teacher, asked, path(judge, "p42"))
    print(json.dumps(router.ledger().get(teachers.TEACHERS[teacher], {})))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["requests", "label", "report"])
    parser.add_argument("judge", nargs="?", choices=[j for j, t in JUDGES.items() if t])
    args = parser.parse_args()
    if args.command == "report":
        report()
    elif args.command == "label":
        label(args.judge)
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
