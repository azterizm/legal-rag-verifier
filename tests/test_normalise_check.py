"""Stop 41: the deterministic check on derived facts (``scripts/normalise_sources.check_fact``)."""

from __future__ import annotations

from typing import Any

from scripts.normalise_sources import check_fact, evaluate

DDOF = [
    (
        "NumPy documentation, numpy.std, parameter ddof\nMeans Delta Degrees of Freedom. "
        "The divisor used in calculations is N - ddof, where N represents the number of "
        "elements. By default ddof is zero."
    )
]
RETRY = ["RFC 9110, Retry-After\nRetry-After: 120 means the client waits 120 seconds."]


def fact(text: str, quotes: list[str], calc: str = "", passage: int = 1) -> dict[str, Any]:
    return {"fact": text, "passage": passage, "quotes": quotes, "calc": calc}


def test_a_default_applied_fact_passes() -> None:
    f = fact(
        "By default numpy.std divides by N, the number of elements, because ddof is 0.",
        ["The divisor used in calculations is N - ddof", "By default ddof is zero"],
    )
    assert check_fact(f, DDOF) is None


def test_an_invented_figure_is_dropped() -> None:
    f = fact("By default numpy.std divides by N - 1.", ["The divisor used in calculations"])
    assert check_fact(f, DDOF) == "figure"


def test_arithmetic_from_quoted_numbers_passes_and_a_wrong_result_is_dropped() -> None:
    good = fact("Retry-After: 120 means waiting 2 minutes.", ["waits 120 seconds"], "120 / 60")
    assert check_fact(good, RETRY) == "calc"  # 60 is not in the quotes
    good["quotes"] = ["waits 120 seconds"]
    good["calc"] = "120 / 2 / 30"
    assert check_fact(good, RETRY) == "calc"
    ok = fact("Retry-After: 120 means waiting 240 half-seconds.", ["waits 120 seconds"], "120+120")
    assert check_fact(ok, RETRY) is None
    wrong = fact(
        "Retry-After: 120 means waiting 250 half-seconds.", ["waits 120 seconds"], "120+120"
    )
    assert check_fact(wrong, RETRY) == "figure"


def test_calc_allows_only_arithmetic() -> None:
    assert evaluate("(120 - 20) / 4", {"120", "20", "4"}) == "25"
    assert evaluate("1 / 3", {"1", "3"}) == "0.333333"
    for bad in ("__import__('os')", "120 ** 2", "abs(120)"):
        try:
            evaluate(bad, {"120", "2"})
        except ValueError:
            continue
        raise AssertionError(bad)


def test_a_quote_not_in_the_source_is_dropped() -> None:
    f = fact("numpy.std divides by N by default.", ["The divisor is always N"])
    assert check_fact(f, DDOF) == "quote"
    short = fact("numpy.std divides by N by default.", ["ddof is"])
    assert check_fact(short, DDOF) == "quote"


def test_a_bad_shape_or_passage_is_dropped() -> None:
    assert check_fact({"fact": "x", "passage": 1, "quotes": []}, DDOF) == "shape"
    f = fact("numpy.std divides by N by default.", ["By default ddof is zero"], passage=2)
    assert check_fact(f, DDOF) == "passage"
