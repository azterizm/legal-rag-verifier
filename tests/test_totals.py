"""Stop 76: a money figure equal to two figures on one line of the source (``totals="line"``).

Offer lines are written to the product test's format (``product-answer-checks`` METHOD §2), with
values made up here, not taken from any battery row.
"""

from __future__ import annotations

from typing import Any

from legal_rag_verifier.index import build_index
from legal_rag_verifier.premise import Premise
from legal_rag_verifier.verifier import GroundedBy, Reason, Verdict, Verifier, VerifierConfig

NBSP = "\u00a0"
LISTING = "Acme Kettle 1.7 L\nPower: 2200 W\nCapacity: 1.7 L"


def offer_en(shop: str, price: str, shipping: str, rest: str) -> str:
    return f"Shop {shop} — Price: {price} — Shipping: {shipping} — Estimated delivery {rest}"


def offer_fr(shop: str, price: str, shipping: str, rest: str) -> str:
    return (
        f"Boutique {shop} — Prix{NBSP}: {price} — Livraison{NBSP}: {shipping} — Livraison "
        f"estimée le {rest}"
    )


OFFERS_EN = "\n".join(
    [
        "Offers as of Monday 2 November 2026:",
        offer_en("A", "€903.99", "€4.99", "Thursday 5 November 2026 — Returns within 30 days"),
        offer_en("B", "€279.99 (was €329.99)", "€6.49", "Monday 9 November 2026 — In stock"),
        offer_en("C", "€311.00", "€4.99", "Friday 6 November 2026 — Returns within 60 days"),
        offer_en("D", "€247.99", "free", "Friday 6 November 2026 — Out of stock"),
    ]
)
OFFERS_FR = "\n".join(
    [
        f"Offres relevées le lundi 2 novembre 2026{NBSP}:",
        offer_fr("A", f"903,99{NBSP}€", f"4,99{NBSP}€", "jeudi 5 novembre 2026 — En stock"),
        offer_fr(
            "B",
            f"279,99{NBSP}€ (au lieu de 329,99{NBSP}€)",
            f"6,49{NBSP}€",
            "lundi 9 novembre 2026 — Retours sous 14 jours — En stock",
        ),
    ]
)
EN = Premise.from_text(f"{LISTING}\n\n{OFFERS_EN}")
FR = Premise.from_text(f"{LISTING}\n\n{OFFERS_FR}")
TOTALS = Verifier(config=VerifierConfig(totals="line"))
DEFAULT = Verifier()


def check(sentence: str, premise: Premise = EN, verifier: Verifier = TOTALS) -> Any:
    return verifier.check_sentence(premise, sentence)


def rolled_back_on_figure(verdict: Any) -> bool:
    return bool(verdict.verdict is Verdict.ROLLBACK and Reason.UNGROUNDED_FIGURE in verdict.reasons)


def test_one_offers_price_plus_shipping_is_grounded() -> None:
    v = check("Shop A comes to a total of €908.98 delivered.")
    assert v.verdict is Verdict.EMIT
    assert v.reasons == (Reason.GROUNDED,)
    total = next(r for r in v.claims if r.claim.value == "EUR:908.98")
    assert total.grounded_by is GroundedBy.WINDOW
    assert any("€908.98 is the sum of two figures on one line" in d for d in v.details)


def test_the_addition_written_out_is_grounded() -> None:
    v = check("At Shop A it is €903.99 + €4.99 shipping = €908.98.")
    assert v.verdict is Verdict.EMIT


def test_off_by_default() -> None:
    assert VerifierConfig().totals == "off"
    assert VerifierConfig().to_dict()["totals"] == "off"
    assert VerifierConfig(totals="line").to_dict()["totals"] == "line"
    assert rolled_back_on_figure(check("Shop A comes to €908.98.", verifier=DEFAULT))


def test_a_wrong_total_still_rolls_back() -> None:
    # €311.00 + €4.99 is €315.99.
    assert check("At Shop C it is €315.99 in total.").verdict is Verdict.EMIT
    assert rolled_back_on_figure(check("The total cost would be €316.99 (€311.00 + €4.99)."))


def test_an_old_price_in_brackets_is_not_added() -> None:
    assert check("Shop B comes to €286.48 with shipping.").verdict is Verdict.EMIT
    assert rolled_back_on_figure(check("Shop B comes to €336.48 with shipping."))


def test_figures_from_two_offers_are_not_added() -> None:
    # Shop A's price plus Shop B's shipping.
    assert rolled_back_on_figure(check("Shop A comes to €910.48."))


def test_figures_from_two_windows_are_not_added() -> None:
    blocks = [
        (
            "Product 1\nAcme Kettle\n\nOffers as of Monday 2 November 2026:\nShop A — Price: "
            "€59.99 — Shipping: €3.99 — Returns within 30 days — In stock"
        ),
        (
            "Product 2\nBrio Kettle\n\nOffers as of Monday 2 November 2026:\nShop B — Price: "
            "€64.00 — Shipping: €7.49 — Returns within 30 days — In stock"
        ),
    ]
    premise = Premise.from_text("\n\n".join(blocks))
    assert check("Product 1 costs €63.98 delivered.", premise).verdict is Verdict.EMIT
    assert rolled_back_on_figure(check("Product 1 costs €67.48 delivered.", premise))


def test_three_figures_are_not_added() -> None:
    premise = Premise.from_text(
        "Offers as of Monday 2 November 2026:\n"
        "Shop E — Price: €100.00 — Shipping: €5.00 — Gift wrap: €2.50 — In stock"
    )
    assert check("Shop E comes to €105.00.", premise).verdict is Verdict.EMIT
    assert rolled_back_on_figure(check("Shop E comes to €107.50.", premise))


def test_another_currency_is_not_the_same_sum() -> None:
    assert rolled_back_on_figure(check("Shop A comes to £908.98."))
    assert rolled_back_on_figure(check("Shop A comes to $908.98."))


def test_a_french_listing_grounds_an_english_total() -> None:
    assert check("Boutique A comes to €908.98.", FR).verdict is Verdict.EMIT
    assert check("Boutique B comes to €286.48.", FR).verdict is Verdict.EMIT
    assert rolled_back_on_figure(check("Boutique B comes to €336.48.", FR))


def test_free_shipping_needs_no_sum() -> None:
    for verifier in (DEFAULT, TOTALS):
        v = check("Shop D costs €247.99 with free shipping.", verifier=verifier)
        assert v.verdict is Verdict.EMIT


def test_the_index_holds_each_lines_sums() -> None:
    offers = build_index(EN).windows[1]
    assert {"EUR:908.98", "EUR:286.48", "EUR:315.99"} <= offers.sums
    assert "EUR:336.48" not in offers.sums  # the old price is in brackets
    assert "EUR:910.48" not in offers.sums  # two lines
    assert build_index(EN).windows[0].sums == frozenset()


def test_the_default_path_does_not_read_the_sums() -> None:
    premise = Premise.from_text(f"{OFFERS_EN}\nShop Z — Price: €1.00 — Shipping: €2.00")
    check("Shop A comes to €908.98.", premise, DEFAULT)
    assert all("sums" not in vars(w) for w in build_index(premise).windows)
    check("Shop A comes to €908.98.", premise, TOTALS)
    assert any("sums" in vars(w) for w in build_index(premise).windows)
