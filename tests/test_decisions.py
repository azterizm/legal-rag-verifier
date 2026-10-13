"""Stop 66: the decision APIs' requests, replies and the threshold reading (no network)."""

from __future__ import annotations

from scripts import auditor_judge as aj
from scripts import decisions as d

CLAUSE = ("The limit is 20.", ("The limit is 30.", "It applies to all."), "It is a rule.")


def test_both_requests_carry_the_same_text_and_questions() -> None:
    luna, jev = d.body(d.LUNA, *CLAUSE), d.body(d.JEV, *CLAUSE)
    assert luna["input"] == jev["state"] == d.state(*CLAUSE)
    assert "[2] It applies to all." in luna["input"]
    assert "Labels:" not in luna["input"]
    assert "Return JSON" not in luna["input"]
    label, passage = luna["questions"]
    assert [c["value"] for c in label["choices"]] == list(aj.LABELS)
    assert {c["value"]: c["description"] for c in label["choices"]} == jev["questions"]["label"][
        "criteria"
    ]
    assert [c["value"] for c in passage["choices"]] == ["0", "1", "2"]
    assert list(jev["questions"]["passage"]["criteria"]) == ["0", "1", "2"]
    assert jev["provider"] == {"data_collection": "deny"}


def test_the_label_definitions_are_the_prompt_s_own() -> None:
    for label, text in d.descriptions().items():
        assert f'- "{label}": {text}' in aj.USER.replace("\\\n", "")


def test_replies_parse_to_one_shape() -> None:
    luna = {
        "answers": [
            {
                "type": "choice",
                "name": "label",
                "choice": "contradicted",
                "probabilities": [
                    {"value": "supported", "probability": 0.1},
                    {"value": "contradicted", "probability": 0.7},
                    {"value": "not_stated", "probability": 0.2},
                ],
                "confidence": 0.6,
            },
            {"type": "choice", "name": "passage", "choice": "1"},
        ]
    }
    jev = {
        "answers": {
            "label": {
                "type": "choice",
                "choice": "contradicted",
                "probabilities": {"supported": 0.1, "contradicted": 0.7, "not_stated": 0.2},
                "confidence": 0.6,
            },
            "passage": {"type": "choice", "choice": "1"},
        }
    }
    assert d.parse(d.LUNA, luna) == d.parse(d.JEV, jev)
    assert d.parse(d.JEV, jev)["label"] == "contradicted"
    assert d.parse(d.JEV, jev)["passage"] == 1
    assert d.parse(d.JEV, jev)["probabilities"]["contradicted"] == 0.7


def test_a_refused_label_is_a_refusal_and_a_refused_passage_is_zero() -> None:
    refused = {"answers": [{"type": "refusal", "name": "label"}]}
    assert d.parse(d.LUNA, refused)["label"] == "refusal"
    half = {
        "answers": {
            "label": {"type": "choice", "choice": "supported"},
            "passage": {"type": "refusal"},
        }
    }
    assert d.parse(d.JEV, half)["label"] == "supported"
    assert d.parse(d.JEV, half)["passage"] == 0


def test_the_threshold_moves_only_the_supported_label() -> None:
    labels = {
        "a": {
            "label": "supported",
            "probabilities": dict(zip(aj.LABELS, (0.6, 0.3, 0.1), strict=True)),
        },
        "b": {
            "label": "not_stated",
            "probabilities": dict(zip(aj.LABELS, (0.4, 0.1, 0.5), strict=True)),
        },
    }
    assert {k: v["label"] for k, v in d.at_threshold(labels, 0.7).items()} == {
        "a": "contradicted",
        "b": "not_stated",
    }
    assert {k: v["label"] for k, v in d.at_threshold(labels, 0.4).items()} == {
        "a": "supported",
        "b": "supported",
    }


def test_the_chosen_threshold_is_the_most_accurate_then_the_nearest_to_a_half() -> None:
    assert d.chosen_threshold({"0.30": 0.9, "0.45": 0.92, "0.60": 0.92, "0.90": 0.8}) == 0.45
    assert d.chosen_threshold({"0.40": 0.9, "0.60": 0.9}) == 0.4
