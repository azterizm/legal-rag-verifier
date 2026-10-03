from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from legal_rag_verifier.premise import Premise

FIXTURES = Path(__file__).parent / "fixtures"
DATA = Path(__file__).parent.parent / "data"

# S.I. 2026/310 art. 1(2) and Schedule: the s.124(1ZA)(a) limit rose from £118,223 to £123,543.
SI_2026_310 = "Employment Rights (Increase of Limits) Order 2026 (S.I. 2026/310)"
S124_FACTS = (
    (
        "Section 124(1ZA)(a) of the Employment Rights Act 1996 has specified £123,543 since "
        "6 April 2026, as amended by the Employment Rights (Increase of Limits) Order 2026 "
        "(S.I. 2026/310)."
    ),
)


def load_fixture(name: str) -> list[dict[str, Any]]:
    with (FIXTURES / name).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


@pytest.fixture(scope="session")
def s124_records() -> list[dict[str, Any]]:
    return load_fixture("era1996_s124.jsonl")


@pytest.fixture(scope="session")
def s124(s124_records: list[dict[str, Any]]) -> Premise:
    """ERA 1996 s.124 as in force (real text), with the 2026 uprating as a fact window."""
    return Premise.from_records(s124_records, facts=S124_FACTS, extra_titles=[SI_2026_310])


@pytest.fixture(scope="session")
def premise_04() -> Premise:
    """The premise of vault 04 §6's test (illustrative figure £68,400)."""
    return Premise.from_text(
        "Under section 124 of the Employment Rights Act 1996, the limit of the compensatory "
        "award is £68,400.",
        citations=["uk/ukpga/1996/18/s124"],
        titles=["Employment Rights Act 1996"],
    )
