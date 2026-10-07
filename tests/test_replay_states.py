"""Stop 29: the first-rollback states arms A and B share, extracted from scripted traces."""

from __future__ import annotations

from typing import Any

import pytest

from scripts.replay_states import committed_text, downstream, mcnemar, paired, shared_states


def attempt(text: str, verdict: str, **extra: Any) -> dict[str, Any]:
    return {"verdict": {"text": text, "verdict": verdict}, **extra}


def sentence(text: str, *attempts: dict[str, Any]) -> dict[str, Any]:
    tried = list(attempts) or [attempt(text, "EMIT")]
    return {"text": text, "rollbacks": len(tried) - 1, "attempts": tried}


def record(key: str, answer: str, *sentences: dict[str, Any]) -> dict[str, Any]:
    return {"id": key, "answer": answer, "trace": {"sentences": list(sentences)}}


def test_committed_text_keeps_the_answer_up_to_the_last_sentence() -> None:
    answer = "The cap is £1. It applies. More."
    assert committed_text(answer, ["The cap is £1.", "It applies."]) == "The cap is £1. It applies."
    assert committed_text(answer, []) == ""
    with pytest.raises(ValueError, match="not in answer"):
        committed_text(answer, ["Absent."])


def test_shared_states_pair_the_first_retries_from_one_state() -> None:
    bad = attempt("The cap is £9.", "ROLLBACK")
    a = {
        "q1": record(
            "q1",
            "Intro. The cap is £1.",
            sentence("Intro."),
            sentence("The cap is £1.", bad, attempt("The cap is £1.", "EMIT", steering="allow")),
        ),
        "q2": record("q2", "Clean.", sentence("Clean.")),
        "q3": record("q3", "X.", sentence("X.", attempt("Y.", "ROLLBACK"), attempt("X.", "EMIT"))),
    }
    b = {
        "q1": record(
            "q1",
            "Intro. The cap is £1.",
            sentence("Intro."),
            sentence("The cap is £1.", bad, attempt("The cap is £1.", "EMIT", injected={"w": 1})),
        ),
        "q2": record("q2", "Clean.", sentence("Clean.")),
        "q3": record("q3", "X.", sentence("X.", attempt("Z.", "ROLLBACK"), attempt("X.", "EMIT"))),
    }
    states, diverged = shared_states(a, b)
    assert diverged == ["q3"]  # different rejected drafts: not one state
    [state] = states
    assert (state.id, state.point, state.committed, state.rejected) == (
        "q1",
        1,
        "Intro.",
        "The cap is £9.",
    )
    assert paired(states)["both"] == 1
    assert paired(states)["b_retries_injected"] == 1


def test_mcnemar_is_exact_and_two_sided() -> None:
    assert mcnemar(0, 0) == 1.0
    assert mcnemar(3, 3) == 1.0
    assert mcnemar(1, 21) == pytest.approx(2 * 23 / 2**22)


def test_downstream_counts_first_drafts_after_the_first_rollback() -> None:
    records = {
        "q": record(
            "q",
            "",
            sentence("A."),
            sentence("B.", attempt("b", "ROLLBACK"), attempt("B.", "EMIT")),
            sentence("C."),
            sentence("D.", attempt("d", "ROLLBACK"), attempt("D.", "EMIT")),
        )
    }
    assert downstream(records, ["q"]) == {"sentences": 2, "first_draft_passed": 1}


def test_holm_steps_down_and_stops_at_the_first_failure() -> None:
    from scripts.replay_report import holm  # noqa: PLC0415

    out = holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert out["a"] == {"p": 0.01, "holm_p": 0.03, "holds": True}
    assert out["c"]["holm_p"] == pytest.approx(0.06)
    assert not out["c"]["holds"]
    assert not out["b"]["holds"]  # 0.04 alone would pass, but Holm stops at c


def test_sign_test_drops_ties() -> None:
    from scripts.replay_report import sign_test  # noqa: PLC0415

    out = sign_test([(2.0, 1.0), (3.0, 1.0), (1.0, 1.0), (0.0, 1.0)])
    assert (out["first_higher"], out["first_lower"], out["states"]) == (2, 1, 4)
