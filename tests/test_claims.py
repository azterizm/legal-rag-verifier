from __future__ import annotations

import pytest

from legal_rag_verifier.citations import (
    coordinate_tail,
    find_citations,
    render_citation,
    resolve_relative,
)
from legal_rag_verifier.claims import ClaimKind, extract_claims, instrument_acronym
from legal_rag_verifier.deontic import Deontic, find_deontics
from legal_rag_verifier.qualifiers import Qualifier, find_bound_qualifier, sentence_qualifiers


def values(text: str, kind: ClaimKind) -> list[str]:
    return [c.value for c in extract_claims(text) if c.kind is kind]


@pytest.mark.parametrize(
    "text",
    ["£68,400", "£68400", "£68.4k", "£68.4 thousand", "68,400 pounds", "£ 68,400.00"],
)
def test_money_forms_normalise_to_one_value(text: str) -> None:
    assert values(f"The cap is {text}.", ClaimKind.MONEY) == ["GBP:68400"]


def test_money_magnitudes_and_currencies() -> None:
    assert values("£1.2m and €5bn and $30", ClaimKind.MONEY) == [
        "GBP:1200000",
        "EUR:5000000000",
        "USD:30",
    ]


@pytest.mark.parametrize("text", ["5%", "5 per cent", "five per cent", "5 percent", "5.0%"])
def test_percent_forms(text: str) -> None:
    assert values(f"a rate of {text}", ClaimKind.PERCENT) == ["5"]


@pytest.mark.parametrize(
    "text",
    [
        "6 April 2026",
        "6th April 2026",
        "April 6, 2026",
        "06/04/2026",
        "2026-04-06",
        "6 of April 2026",
    ],
)
def test_date_forms_normalise_to_iso(text: str) -> None:
    assert values(f"from {text}", ClaimKind.DATE) == ["2026-04-06"]


def test_month_year_and_may_month() -> None:
    assert values("since April 2026", ClaimKind.DATE) == ["2026-04"]
    assert values("on 1 May 2026", ClaimKind.DATE) == ["2026-05-01"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("three months", "3:month"),
        ("3 months", "3:month"),
        ("3 calendar months", "3:month"),
        ("fifty-two weeks", "52:week"),
        ("52 weeks'", "52:week"),
        ("two years", "2:year"),
        ("14 days", "14:day"),
    ],
)
def test_durations(text: str, expected: str) -> None:
    assert values(f"within {text} of the date", ClaimKind.DURATION) == [expected]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("section 124(1ZA)(a)", ["s124/1ZA/a"]),
        ("s.124(1ZA)(a)", ["s124/1ZA/a"]),
        ("s. 124 (1ZA) (a)", ["s124/1ZA/a"]),
        ("s124(1ZA)", ["s124/1ZA"]),
        ("section 117(1) and (2)", ["s117/1", "s117/2"]),
        ("s.124(1ZA)(a) and (b)", ["s124/1ZA/a", "s124/1ZA/b"]),
        ("sections 100, 103A, 105(3) or 105(6A)", ["s100", "s103A", "s105/3", "s105/6A"]),
        ("paragraph (a) of subsection (3) of section 117", ["s117/3/a"]),
        ("paragraph 3 of Schedule 2", ["sch2/para3"]),
        ("art. 6(1)(f)", ["art6/1/f"]),
        ("regulation 4(2)", ["reg4/2"]),
        ("subsection (1ZA)", ["~/1ZA"]),
        ("Part 12", ["pt12"]),
    ],
)
def test_citations_normalise(text: str, expected: list[str]) -> None:
    assert [c.canonical for c in find_citations(text)] == expected


def test_citation_false_friends() -> None:
    assert find_citations("it's 5 o'clock") == []
    assert find_citations("the employer's duties") == []


def test_relative_resolution_and_rendering() -> None:
    assert coordinate_tail("uk/ukpga/1996/18/s124/1ZA") == "s124/1ZA"
    assert coordinate_tail("uk/ukpga/Vict/24-25/100/s20") == "s20"
    assert coordinate_tail("uk/ukpga/1996/18") == ""
    assert resolve_relative("~/1ZA", "s124/1") == "s124/1ZA"
    assert resolve_relative("~/a", "s124/1ZA") == "s124/1ZA/a"
    assert resolve_relative("~/a", "s124") == "s124/a"
    assert resolve_relative("s5", "s124") == "s5"
    assert render_citation("s124/1ZA/a") == "section 124(1ZA)(a)"
    assert render_citation("s124/1ZA/a", style="s.") == "s.124(1ZA)(a)"
    assert render_citation("sch2/para3") == "Schedule 2(para3)"


def test_instruments() -> None:
    assert values(
        "Under the Employment Rights Act 1996 and the Marchwood Commercial Arbitration Order 2022",
        ClaimKind.INSTRUMENT,
    ) == ["employment rights act 1996", "marchwood commercial arbitration order 2022"]
    assert values("see S.I. 2026/310 and SI 2026/0310", ClaimKind.INSTRUMENT) == [
        "si:2026/310",
        "si:2026/310",
    ]
    assert values("ERA 1996 s.98", ClaimKind.INSTRUMENT) == ["acr:ERA1996"]
    assert instrument_acronym("Trade Union and Labour Relations (Consolidation) Act 1992") == (
        "TULRA1992"
    )


def test_no_double_counting_inside_citations_titles_and_dates() -> None:
    claims = extract_claims(
        "Under section 124 of the Employment Rights Act 1996, from 6 April 2026."
    )
    assert [c.kind for c in claims] == [ClaimKind.CITATION, ClaimKind.INSTRUMENT, ClaimKind.DATE]


def test_bare_numbers_are_claims() -> None:
    assert values("52 multiplied by a week's pay", ClaimKind.NUMBER) == ["52"]
    assert values("item (1) applies", ClaimKind.NUMBER) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("The employer shall provide reasons.", [Deontic.OBLIGATION]),
        ("The employer must provide reasons.", [Deontic.OBLIGATION]),
        ("The employer is required to provide reasons.", [Deontic.OBLIGATION]),
        ("The employer may provide reasons.", [Deontic.PERMISSION]),
        ("The employee is entitled to reasons.", [Deontic.PERMISSION]),
        ("The employer need not provide reasons.", [Deontic.PERMISSION]),
        ("The employer is not required to provide reasons.", [Deontic.PERMISSION]),
        ("The award shall not exceed the limit.", [Deontic.PROHIBITION]),
        ("The award cannot exceed the limit.", [Deontic.PROHIBITION]),
        ("The award may not exceed the limit.", [Deontic.PROHIBITION]),
        ("You may be able to claim.", []),
        ("It ended on 1 May 2026.", []),
    ],
)
def test_deontic_classes(text: str, expected: list[Deontic]) -> None:
    assert [d.deontic for d in find_deontics(text)] == expected


def test_qualifier_binds_figure_in_s124_1za() -> None:
    window = (
        "(1ZA) The amount specified in this subsection is the lower of— (a) £123,543, and (b) 52"
    )
    start = window.index("£123,543")
    bound = find_bound_qualifier(window, start, start + len("£123,543"))
    assert bound is not None
    assert bound.qualifier is Qualifier.COMPARATIVE


def test_qualifier_scope_stops_at_clause_break() -> None:
    window = "Subject to subsection (3), this applies. The amount is £500."
    start = window.index("£500")
    assert find_bound_qualifier(window, start, start + 4) is None


def test_sentence_qualifier_classes() -> None:
    assert Qualifier.COMPARATIVE in sentence_qualifiers("the lower of £123,543 and a year's pay")
    assert Qualifier.COMPARATIVE not in sentence_qualifiers("The cap is £123,543.")
    assert Qualifier.UPPER_LIMIT in sentence_qualifiers("The cap is £123,543.")


def test_huge_numbers_do_not_overflow() -> None:
    assert values("10000000000000000000000000000", ClaimKind.NUMBER) == [
        "10000000000000000000000000000"
    ]
    assert values("£1.20m", ClaimKind.MONEY) == ["GBP:1200000"]


def test_title_with_a_listed_comma_is_kept_whole() -> None:
    text = "It was superseded by the Companies, Partnerships and Groups (Accounts and Reports) "
    text += "Regulations 2015, so the figure changed."
    assert values(text, ClaimKind.INSTRUMENT) == [
        "companies, partnerships and groups (accounts and reports) regulations 2015"
    ]
    assert values("Furthermore, Employment Rights Act 1996 applies.", ClaimKind.INSTRUMENT) == [
        "employment rights act 1996"
    ]
    assert values(
        "The Equality Act 2010, Employment Rights Act 1996 and Children Act 1989 apply.",
        ClaimKind.INSTRUMENT,
    ) == ["equality act 2010", "employment rights act 1996", "children act 1989"]


def test_a_label_number_is_not_a_claim() -> None:
    assert values("See item 7 of the table: 3 conditions apply.", ClaimKind.NUMBER) == ["3"]
