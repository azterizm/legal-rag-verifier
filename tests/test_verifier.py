"""Golden tests for the claim check (plan M1) on the real ERA 1996 s.124 text."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import pytest

from legal_rag_verifier.premise import PassageKind, Premise
from legal_rag_verifier.verifier import GroundedBy, Reason, Verdict, Verifier, VerifierConfig

V = Verifier()
QUERY = "My salary is £40,000 a year. What is the most I can get for unfair dismissal?"


def check(premise: Premise, sentence: str, query: str | None = None) -> Any:
    return V.check_sentence(premise, sentence, query=query)


# ---------------------------------------------------------------- premise assembly (R10)
def test_windows_follow_the_provision_tree(s124: Premise) -> None:
    provisions = [p for p in s124.passages if p.kind is PassageKind.PROVISION]
    by_tail = {p.tail: p.text for p in provisions}
    assert list(by_tail) == ["s124/1", "s124/1ZA", "s124/1A", "s124/3", "s124/4", "s124/5"]
    assert by_tail["s124/1ZA"] == (
        "(1ZA) The amount specified in this subsection is the lower of— (a) £123,543, and "
        "(b) 52 multiplied by a week’s pay of the person concerned."
    )
    assert by_tail["s124/1"].endswith("shall not exceed the amount specified in subsection (1ZA).")
    assert "s124/2" not in by_tail  # repealed: dot run dropped
    assert {"s124", "s124/1ZA/a", "s124/1ZA/b"} <= s124.citations
    assert "s124/2" not in s124.citations


def test_from_provision_linearises_temporal_metadata() -> None:
    premise = Premise.from_provision(
        "£123,543, and",
        "uk/ukpga/1996/18/s124/1ZA/a",
        "Employment Rights Act 1996",
        in_force_from=date(2026, 4, 6),
        amended_by="Employment Rights (Increase of Limits) Order 2026 (S.I. 2026/310)",
        previous_text="£118,223, and",
    )
    facts = [p.text for p in premise.facts]
    assert facts[0] == (
        "Employment Rights Act 1996, section 124(1ZA)(a) has had its current text since "
        "6 April 2026, as amended by the Employment Rights (Increase of Limits) Order 2026 "
        "(S.I. 2026/310)."
    )
    assert facts[1].startswith("Before 6 April 2026")
    verdict = check(premise, "Since 6 April 2026 the figure has been £123,543 under S.I. 2026/310.")
    assert verdict.verdict is Verdict.EMIT
    assert check(premise, "Before 6 April 2026 the figure was £118,223.").verdict is Verdict.EMIT


# ---------------------------------------------------------------- vault 04 §6 tests, rebuilt
def test_04_grounded_figure_emits(premise_04: Premise) -> None:
    verdict = check(premise_04, "The statutory cap on the compensatory award is set at £68,400.")
    assert verdict.verdict is Verdict.EMIT
    assert verdict.reasons == (Reason.GROUNDED,)


def test_04_hallucinated_figure_rolls_back(premise_04: Premise) -> None:
    verdict = check(
        premise_04, "The statutory cap on the compensatory award is £85,000 under the 1996 Act."
    )
    assert verdict.verdict is Verdict.ROLLBACK
    assert verdict.reasons == (Reason.UNGROUNDED_FIGURE,)
    assert verdict.ungrounded == ["£85,000"]
    assert verdict.repair is not None
    assert verdict.repair.mode == "allow"
    assert verdict.repair.candidates == ("£68,400",)
    assert verdict.text[verdict.repair.offset :].startswith("£85,000")


def test_04_connective_prose_emits(premise_04: Premise) -> None:
    verdict = check(premise_04, "The position is as follows:")
    assert verdict.verdict is Verdict.EMIT
    assert verdict.reasons == (Reason.CONNECTIVE,)


def test_04_deontic_shift_shall_to_may() -> None:
    premise = Premise.from_text("The employer shall provide written reasons.")
    verdict = check(premise, "The employer may provide written reasons.")
    assert verdict.reasons == (Reason.DEONTIC_SHIFT,)
    assert verdict.repair is not None
    assert verdict.repair.candidates == ("must", "shall")
    assert verdict.repair.rejected == "may"


def test_figure_surface_forms_are_equal(premise_04: Premise) -> None:
    assert check(premise_04, "Under s. 124 the cap is £68.4k.").verdict is Verdict.EMIT
    assert check(premise_04, "Under s.124 the cap is £68400.").verdict is Verdict.EMIT


def test_section_and_s_dot_are_the_same_citation(premise_04: Premise) -> None:
    for sentence in ("Section 124 sets the limit.", "s.124 sets the limit.", "s 124 sets it."):
        assert check(premise_04, sentence).verdict is Verdict.EMIT, sentence


# ---------------------------------------------------------------- s.124 goldens
def test_full_statement_of_the_cap_emits(s124: Premise) -> None:
    verdict = check(
        s124, "The compensatory award is capped at the lower of £123,543 and 52 weeks' pay."
    )
    assert verdict.verdict is Verdict.EMIT
    money = next(c for c in verdict.claims if c.claim.kind.value == "MONEY")
    assert money.grounded_by is GroundedBy.WINDOW


def test_dropped_qualifier(s124: Premise) -> None:
    verdict = check(s124, "The cap is £123,543.")
    assert verdict.verdict is Verdict.ROLLBACK
    assert verdict.reasons == (Reason.QUALIFIER_DROPPED,)
    assert verdict.repair is not None
    assert verdict.repair.mode == "ban"


def test_qualifier_kept_in_other_words(s124: Premise) -> None:
    for sentence in (
        "The limit is £123,543 or 52 weeks' pay, whichever is lower.",
        "The award cannot be more than the lesser of £123,543 and a year's pay.",
    ):
        assert check(s124, sentence).verdict is Verdict.EMIT, sentence


def test_wrong_figure_gets_premise_figure_as_candidate(s124: Premise) -> None:
    verdict = check(s124, "The compensatory award cannot exceed £85,000.")
    assert verdict.reasons == (Reason.UNGROUNDED_FIGURE,)
    assert verdict.repair is not None
    assert verdict.repair.candidates == ("£123,543",)


def test_parent_and_child_citations(s124: Premise) -> None:
    for sentence in (
        "Section 124 limits the compensatory award.",
        "Under s.124(1ZA)(a) the figure is the lower of £123,543 and a week's pay times 52.",
        "Subsection (1ZA) sets the lower of two amounts.",
    ):
        assert check(s124, sentence).verdict is Verdict.EMIT, sentence


def test_unknown_subsection_is_ungrounded(s124: Premise) -> None:
    verdict = check(s124, "Under section 124(9) the limit may be exceeded.")
    assert verdict.reasons == (Reason.UNGROUNDED_CITATION,)
    assert verdict.repair is not None
    assert verdict.repair.rejected == "section 124(9)"
    assert all(c.startswith("section 124(") for c in verdict.repair.candidates)


def test_wrong_instrument_marchwood(s124: Premise) -> None:
    verdict = check(
        s124,
        "Under the Marchwood Commercial Arbitration Order 2022 the limit is the lower of "
        "£123,543 and 52 weeks' pay.",
    )
    assert verdict.reasons == (Reason.UNGROUNDED_INSTRUMENT,)
    assert verdict.repair is not None
    assert verdict.repair.candidates[0] == "Employment Rights Act 1996"


def test_named_instruments_ground(s124: Premise) -> None:
    for sentence in (
        "The Employment Rights Act 1996 sets the limit.",
        "The ERA 1996 sets the limit.",
        "S.I. 2026/310 raised the limit.",
    ):
        assert check(s124, sentence).verdict is Verdict.EMIT, sentence
    # Neither s.124A nor the 1992 Act is in this premise.
    verdict = check(
        s124,
        "Section 124A refers to the Trade Union and Labour Relations (Consolidation) Act 1992.",
    )
    assert set(verdict.reasons) == {Reason.UNGROUNDED_CITATION, Reason.UNGROUNDED_INSTRUMENT}


def test_temporal_fact_grounds_the_date(s124: Premise) -> None:
    verdict = check(
        s124, "Since 6 April 2026 the limit has been the lower of £123,543 and 52 weeks' pay."
    )
    assert verdict.verdict is Verdict.EMIT
    date_claim = next(c for c in verdict.claims if c.claim.kind.value == "DATE")
    assert date_claim.grounded_by in {GroundedBy.FACT, GroundedBy.WINDOW}


def test_ungrounded_date(s124: Premise) -> None:
    verdict = check(
        s124, "Since 1 April 2025 the limit has been the lower of £123,543 and a year's pay."
    )
    assert verdict.reasons == (Reason.UNGROUNDED_FIGURE,)


def test_modal_shift_against_aligned_window(s124: Premise) -> None:
    ok = check(s124, "The limit may be exceeded to reflect an award under section 114(2)(a).")
    assert ok.verdict is Verdict.EMIT
    shifted = check(s124, "The limit must be exceeded to reflect an award under section 114(2)(a).")
    assert shifted.reasons == (Reason.DEONTIC_SHIFT,)
    assert shifted.repair is not None
    assert shifted.repair.candidates == ("may",)


def test_prohibition_restated_is_not_a_shift(s124: Premise) -> None:
    verdict = check(s124, "The compensatory award must not exceed the amount in subsection (1ZA).")
    assert verdict.verdict is Verdict.EMIT


def test_query_figure_is_grounded(s124: Premise) -> None:
    verdict = check(
        s124,
        "On a salary of £40,000 the cap is the lower of £123,543 and 52 weeks' pay.",
        query=QUERY,
    )
    assert verdict.verdict is Verdict.EMIT
    salary = next(c for c in verdict.claims if c.claim.value == "GBP:40000")
    assert salary.grounded_by is GroundedBy.QUERY
    assert check(s124, "On a salary of £40,000 you get less.").verdict is Verdict.ROLLBACK


def test_value_swap_is_caught() -> None:
    premise = Premise.from_text(
        "The compensatory award shall not exceed £123,543.\n\n"
        "The basic award shall not be less than £9,157 where the dismissal is for trade union "
        "reasons.\n\n"
        "A week's pay is calculated under Chapter II of Part XIV.\n\n"
        "The tribunal may make a reinstatement order."
    )
    verdict = check(premise, "The compensatory award shall not exceed £9,157.")
    assert verdict.reasons == (Reason.FIGURE_MISALIGNED,)
    assert verdict.repair is not None
    assert verdict.repair.candidates == ("£123,543",)


def test_check_text_splits_and_offsets(s124: Premise) -> None:
    text = (
        "The position is as follows:\nThe cap is £123,543. "
        "Under s. 124 it is the lower of £123,543 and 52 weeks' pay."
    )
    verdicts = V.check_text(s124, text)
    assert [v.verdict for v in verdicts] == [Verdict.EMIT, Verdict.ROLLBACK, Verdict.EMIT]
    for v in verdicts:
        assert text[v.start : v.end] == v.text


def test_to_dict_is_json_ready(s124: Premise) -> None:
    verdict = check(s124, "The compensatory award cannot exceed £85,000.")
    payload = json.dumps(verdict.to_dict(), sort_keys=True)
    assert '"UNGROUNDED_FIGURE"' in payload


@pytest.mark.parametrize("policy", ["connective", "strict"])
def test_config_round_trips(policy: str) -> None:
    config = VerifierConfig(neutral_policy=policy)  # type: ignore[arg-type]
    assert config.to_dict()["neutral_policy"] == policy
