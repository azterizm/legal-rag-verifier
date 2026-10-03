from __future__ import annotations

import pytest

from legal_rag_verifier.segmenter import find_boundary, split_sentences


def texts(text: str) -> list[str]:
    return [s.text for s in split_sentences(text)]


@pytest.mark.parametrize(
    "sentence",
    [
        "Under s. 124 of the Act the limit applies.",
        "Under ss. 124 and 125 the limits apply.",
        "See art. 6(1)(f) of the GDPR.",
        "Regulation reg. 4 applies.",
        "Acme Ltd. v. Smith is binding on the tribunal.",
        "The cap is £68.4k for this year.",
        "The rate is 12.5% here.",
        "See e.g. the guidance.",
        "That is, i.e. the employer, must act.",
        "S.I. 2026/310 raised the limit.",
        "It is order No. 5 of the list.",
        "See para. 3 of Sch. 2.",
    ],
)
def test_abbreviations_and_figures_do_not_split(sentence: str) -> None:
    assert texts(sentence) == [sentence]


def test_boundaries() -> None:
    assert texts("One. Two; three\nFour") == ["One.", "Two;", "three", "Four"]
    assert texts("The position is as follows:\nThe cap applies.") == [
        "The position is as follows:",
        "The cap applies.",
    ]
    assert texts("The answer is no. Next point.") == ["The answer is no.", "Next point."]
    assert texts("Wages, holiday pay etc. The next point.") == [
        "Wages, holiday pay etc.",
        "The next point.",
    ]


def test_spans_point_into_source() -> None:
    text = "  First one.  Second one. "
    for s in split_sentences(text):
        assert text[s.start : s.end] == s.text


def test_streaming_dot_at_end_is_undecided() -> None:
    assert find_boundary("The cap is £68.") is None
    assert find_boundary("The cap is £68.4k.", final=True) == len("The cap is £68.4k.")
    assert find_boundary("Under s.") is None
    assert find_boundary("Under s. 124 the cap applies. Next") == len(
        "Under s. 124 the cap applies."
    )
    assert find_boundary("no stop yet") is None
    assert find_boundary("no stop yet", final=True) == len("no stop yet")


def test_closing_quote_kept_with_sentence() -> None:
    assert texts('He said "stop." Then left.') == ['He said "stop."', "Then left."]
