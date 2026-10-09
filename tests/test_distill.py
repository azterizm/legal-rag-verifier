"""Stops 43 to 47: batching, reply parsing, budget caps and the pool's disjointness check."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts import auditor_judge as aj
from scripts import modal_ledger, router
from scripts.page_sections import _pieces


def test_batches_keep_each_clause_under_its_single_prompt_key() -> None:
    units = [
        {"group": "a", "prefix": "", "calls": [["First.", ["p1", "p2"]]]},
        {
            "group": "a",
            "prefix": "First.",
            "calls": [["Second.", ["p1", "p2"]], ["Third.", ["p1", "p2"]]],
        },
        {"group": "b", "prefix": "", "calls": [["Other.", ["p1", "p2"]]]},
    ]
    out = aj.batches(units)
    assert [b["clauses"] for b in out] == [["First.", "Second.", "Third."], ["Other."]]
    assert out[0]["keys"][1] == aj.prompt_key(aj.user_prompt("Second.", ["p1", "p2"], "First."))
    assert "[3] Third." in out[0]["user"]
    assert "[1] p1" in out[0]["user"]


def test_batched_replies_must_cover_every_clause() -> None:
    good = json.dumps(
        {"results": [{"sentence": 1, "label": "supported", "passage": 2, "reason": "r"}] * 2}
    )
    assert [r["label"] for r in aj.parse_batch(good, 2)] == ["supported", "supported"]
    with pytest.raises(ValueError, match="expected 3"):
        aj.parse_batch(good, 3)


def test_k2_reply_after_a_mismatched_close_tag_is_recovered() -> None:
    reasoning = 'Supported.</ifm|think>{"label":"supported","passage":1,"reason":"x"}'
    reply = aj.CLOSE_THINK.split(reasoning)[-1]
    assert aj.parse_reply(reply)["label"] == "supported"


def test_router_refuses_a_call_that_could_pass_the_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(router, "LEDGER", tmp_path / "ledger.json")
    messages = [{"role": "user", "content": "x" * 4000}]
    router._record(router.OPUS55, messages, {"prompt_tokens": 1000, "completion_tokens": 500}, "")
    assert router.ledger()[router.OPUS55]["usd"] == pytest.approx(0.014)
    monkeypatch.setattr(router, "CAPS", {router.OPUS55: 0.1})
    with pytest.raises(router.BudgetExceededError):
        router._reserve(router.OPUS55, messages)
    with pytest.raises(ValueError, match="not a router model"):
        router.chat("gpt-oss-120b-medium", messages)


def test_modal_ledger_refuses_a_run_past_its_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(modal_ledger, "LEDGER", tmp_path / "modal.json")
    modal_ledger.record("run", "H100", 3600)
    assert modal_ledger.spent() == pytest.approx(3.95 * 1.15)
    monkeypatch.setattr(modal_ledger, "CAP", 5.0)
    with pytest.raises(modal_ledger.ModalBudgetError):
        modal_ledger.check("H100", 3600)


def test_long_sections_split_at_blocks() -> None:
    body = ["a" * 800, "b" * 800, "c" * 800, "d" * 800]
    pieces = _pieces("H", body)
    assert [len(t) for _, t in pieces] == [1601, 1601]
    assert _pieces("H", ["short"]) == []


@pytest.mark.full_data
def test_the_pool_is_disjoint_from_every_test_set() -> None:
    from scripts import distill_data  # noqa: PLC0415 - needs data/

    if not distill_data.POOL.exists():
        pytest.skip("pool not built")
    pool: list[dict[str, Any]] = distill_data.pool()
    distill_data.check_disjoint(pool)
    with pytest.raises(RuntimeError, match="overlaps"):
        distill_data.check_disjoint(
            [{"id": "x", "domain": "legal", "premise": ["uk/ukpga/1996/18/s92"]}]
        )
