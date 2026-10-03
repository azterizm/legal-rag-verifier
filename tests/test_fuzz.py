"""Property tests: the claim check never raises, and normalisation is stable."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from legal_rag_verifier.citations import find_citations, render_citation
from legal_rag_verifier.claims import ClaimKind, extract_claims, normalise_title
from legal_rag_verifier.premise import Premise
from legal_rag_verifier.segmenter import find_boundary, split_sentences
from legal_rag_verifier.verifier import Verifier

LEGALISH = st.lists(
    st.sampled_from(
        [*"abcdefsSArtiLd .;:,()£€$%-/\n0123456789", "shall", " may ", "section ", " Act 1996"]
    ),
    max_size=80,
).map("".join)
PREMISE = Premise.from_text(
    "(1ZA) The amount specified in this subsection is the lower of— (a) £123,543, and (b) 52 "
    "multiplied by a week’s pay of the person concerned.",
    citations=["s124/1ZA"],
    titles=["Employment Rights Act 1996"],
)


@settings(max_examples=300)
@given(st.one_of(st.text(max_size=200), LEGALISH))
def test_check_text_never_raises(text: str) -> None:
    verdicts = Verifier().check_text(PREMISE, text)
    for v in verdicts:
        assert text[v.start : v.end] == v.text


@settings(max_examples=300)
@given(st.one_of(st.text(max_size=200), LEGALISH))
def test_segmenter_covers_all_content(text: str) -> None:
    sentences = split_sentences(text)
    joined = "".join(s.text for s in sentences)
    assert "".join(joined.split()) == "".join(text.split())
    assert all(s.text == s.text.strip() and s.text for s in sentences)


@given(st.text(max_size=120), st.integers(min_value=0, max_value=120))
def test_find_boundary_in_range(text: str, start: int) -> None:
    end = find_boundary(text, min(start, len(text)), final=True)
    assert end is None or min(start, len(text)) < end <= len(text)


@given(st.integers(min_value=0, max_value=10**9), st.sampled_from(["£", "€", "$"]))
def test_money_canonical_form_round_trips(amount: int, symbol: str) -> None:
    (claim,) = [c for c in extract_claims(f"{symbol}{amount:,}") if c.kind is ClaimKind.MONEY]
    _, value = claim.value.split(":")
    assert int(value) == amount
    (again,) = [c for c in extract_claims(f"{symbol}{value}") if c.kind is ClaimKind.MONEY]
    assert again.value == claim.value


@given(
    st.integers(min_value=1, max_value=999),
    st.lists(st.sampled_from(["1", "2", "1ZA", "3A", "a", "b", "i"]), max_size=3),
    st.sampled_from(["section", "s."]),
)
def test_citation_render_round_trips(number: int, labels: list[str], style: str) -> None:
    canonical = "/".join([f"s{number}", *labels])
    rendered = render_citation(canonical, style=style)
    assert [c.canonical for c in find_citations(rendered)] == [canonical]


@given(st.text(max_size=80))
def test_title_normalisation_is_idempotent(title: str) -> None:
    once = normalise_title(title)
    assert normalise_title(once) == once
