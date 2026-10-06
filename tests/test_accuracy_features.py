"""Accuracy-plan pieces (stop 9): limbs, validity, enrichment audit, and the feature checks."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from legal_rag_verifier.enrichment import Layer, Threshold, attach, audit_entry, from_dict, load
from legal_rag_verifier.premise import Passage, PassageKind, Premise
from legal_rag_verifier.verifier import NLIProbs, Reason, Verifier, VerifierConfig

BURGLARY: list[dict[str, Any]] = [
    {"record_type": "instrument", "coordinate": "uk/ukpga/1968/60", "title": "Theft Act 1968"},
    {"coordinate": "uk/ukpga/1968/60/s9", "parent": "uk/ukpga/1968/60", "order": 0, "text": ""},
    {
        "coordinate": "uk/ukpga/1968/60/s9/3",
        "parent": "uk/ukpga/1968/60/s9",
        "number_label": "3",
        "order": 1,
        "text": (
            "A person guilty of burglary shall be liable to imprisonment for a term not exceeding—"
        ),
    },
    {
        "coordinate": "uk/ukpga/1968/60/s9/3/a",
        "parent": "uk/ukpga/1968/60/s9/3",
        "number_label": "a",
        "order": 2,
        "text": "where the building is a dwelling, fourteen years;",
    },
    {
        "coordinate": "uk/ukpga/1968/60/s9/3/b",
        "parent": "uk/ukpga/1968/60/s9/3",
        "number_label": "b",
        "order": 3,
        "text": "in any other case, ten years.",
    },
]


def test_limbs_are_standalone_statements() -> None:
    (window,) = Premise.from_records(BURGLARY).passages
    assert window.limbs == (
        (
            "A person guilty of burglary shall be liable to imprisonment for a term not exceeding "
            "where the building is a dwelling, fourteen years."
        ),
        (
            "A person guilty of burglary shall be liable to imprisonment for a term not exceeding "
            "in any other case, ten years."
        ),
    )


def test_limb_check_catches_a_same_window_swap() -> None:
    premise = Premise.from_records(BURGLARY)
    sentence = "Burglary of a dwelling carries a maximum of ten years' imprisonment."
    # Both figures are in the one window; only the list items tell them apart.
    assert Verifier().check_sentence(premise, sentence).reasons == (Reason.FIGURE_MISALIGNED,)
    right = "Burglary of a dwelling carries a maximum of fourteen years' imprisonment."
    assert Verifier().check_sentence(premise, right).emitted


def _dated_premise() -> Premise:
    return Premise(
        (
            Passage(
                "The amount of a week's pay shall not exceed £751.",
                "uk/ukpga/1996/18/s227/1",
                PassageKind.PROVISION,
                valid_from=date(2026, 4, 6),
            ),
            Passage(
                "From 6 April 2014 until it was replaced on 6 April 2016, the amount of a week's "
                "pay shall not exceed £464.",
                None,
                PassageKind.FACT,
                valid_from=date(2014, 4, 6),
                valid_to=date(2016, 4, 6),
            ),
        )
    )


def test_as_at_check_uses_the_sentence_or_query_date() -> None:
    verifier = Verifier()
    premise = _dated_premise()
    query = "As at 1 June 2014, what was the maximum amount of a week's pay?"
    wrong = verifier.check_sentence(
        premise, "As at 1 June 2014, a week's pay was capped at £751.", query=query
    )
    assert Reason.VERSION_MISMATCH in wrong.reasons
    assert wrong.repair is not None
    assert wrong.repair.candidates == ("£464",)
    by_query = verifier.check_sentence(
        premise, "The cap on a week's pay was £751.", query="As at 1 June 2014, what was the cap?"
    )
    assert Reason.VERSION_MISMATCH in by_query.reasons
    assert verifier.check_sentence(
        premise, "As at 1 June 2014 the cap was £464.", query=query
    ).emitted
    assert verifier.check_sentence(premise, "The cap is currently £751.").emitted


class Scripted:
    model_id = "scripted"

    def __init__(self) -> None:
        self.hypotheses: list[str] = []

    def score(self, premises: Sequence[str], hypothesis: str) -> list[NLIProbs]:
        self.hypotheses.append(hypothesis)
        return [NLIProbs(0.95, 0.04, 0.01) for _ in premises]


def test_clauses_drop_denials_before_nli() -> None:
    scorer = Scripted()
    premise = Premise.from_text(
        "An employer shall give notice.", titles=["Employment Rights Act 1996"], citations=["s86"]
    )
    verdict = Verifier(scorer).check_sentence(
        premise, "There is no Family Rights Act 1996; notice is governed by section 86."
    )
    assert verdict.emitted
    assert scorer.hypotheses == ["notice is governed by section 86."]


def test_audit_keeps_only_verbatim_quotes_and_figures_in_quotes() -> None:
    source = "A person guilty of burglary shall be liable to imprisonment not exceeding ten years."
    audit = audit_entry(
        {
            "elements": [
                {
                    "requirement": "Burglary is punishable by up to ten years.",
                    "quote": "not exceeding ten years",
                },
                {"requirement": "Invented.", "quote": "a fine of £5,000"},
            ],
            "thresholds": [
                {
                    "what": "maximum sentence",
                    "value": "ten years",
                    "quote": "not exceeding ten years",
                },
                {"what": "fine", "value": "£5,000", "quote": "not exceeding ten years"},
            ],
        },
        source,
    )
    assert audit.elements == (
        ("Burglary is punishable by up to ten years.", "not exceeding ten years"),
    )
    assert audit.thresholds == (
        Threshold("maximum sentence", "ten years", "not exceeding ten years"),
    )
    assert audit.to_dict()["audit"] == {
        "elements_proposed": 2,
        "elements_verified": 1,
        "thresholds_proposed": 2,
        "thresholds_verified": 1,
    }
    assert from_dict(audit.to_dict()) == audit


def test_layer_attaches_elements_and_is_named(tmp_path: Path) -> None:
    premise = Premise.from_records(BURGLARY)
    source = premise.passages[0].text
    audit = audit_entry(
        {
            "elements": [
                {
                    "requirement": "Burglary of a dwelling is punishable by up to fourteen years.",
                    "quote": "where the building is a dwelling, fourteen years",
                }
            ]
        },
        source,
    )
    entry = {"section": "uk/ukpga/1968/60/s9", "model": "m", **audit.to_dict()}
    (tmp_path / "s9.json").write_text(json.dumps(entry), encoding="utf-8")
    layer = load(tmp_path)
    assert layer.layer_id.startswith("m@")
    enriched = attach(premise, layer)
    assert enriched.enrichment == layer.layer_id
    assert enriched.passages[0].elements == (
        "Burglary of a dwelling is punishable by up to fourteen years.",
    )
    assert attach(premise, Layer("x@0", ())).passages[0].elements == ()


class Verdictless:
    model_id = "scripted"

    def score(self, premises: Sequence[str], hypothesis: str) -> list[NLIProbs]:
        return [NLIProbs(0.2, 0.75, 0.05) for _ in premises]


@pytest.mark.parametrize(("policy", "emitted"), [("emit", True), ("rollback", False)])
def test_neutral_with_grounded_claim_policy(policy: str, emitted: bool) -> None:
    premise = Premise.from_text("A complaint must be presented within three months.")
    config = VerifierConfig(neutral_with_grounded_claim=policy)  # type: ignore[arg-type]
    verdict = Verifier(Verdictless(), config).check_sentence(
        premise, "You have three months to present it."
    )
    assert verdict.emitted is emitted
    assert config.to_dict()["neutral_with_grounded_claim"] == policy


def test_before_a_date_means_the_day_before() -> None:
    premise = _dated_premise()
    assert Verifier().check_sentence(premise, "Before 6 April 2016 the cap was £464.").emitted
    assert (
        not Verifier().check_sentence(premise, "Since 6 April 2026 the cap has been £464.").emitted
    )


def test_empty_premise_skips_nli_and_grounds_nothing() -> None:
    scorer = Scripted()
    verdict = Verifier(scorer).check_sentence(Premise(()), "The penalty is £30,000.")
    assert verdict.reasons == (Reason.UNGROUNDED_FIGURE,)
    assert Verifier(scorer).check_sentence(Premise(()), "I cannot find that Act.").emitted
    assert scorer.hypotheses == []
