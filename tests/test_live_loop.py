"""Stop 59: the judge as the loop's scorer, the answer so far, and the arms' settings."""

from __future__ import annotations

import json
from typing import Any

from legal_rag_verifier.premise import Premise
from legal_rag_verifier.verifier import Verdict
from scripts import live_loop as ll
from tests.test_engine import PREMISE as SOURCE
from tests.test_engine import QUERY, ScriptedBackend

PREMISE = Premise.from_text(
    "The employer shall give written reasons for dismissal within fourteen days.\n\n"
    "The tribunal may order reinstatement."
)


class Chat:
    """Replies with a fixed label and keeps the prompts it was sent."""

    def __init__(self, label: str, passage: int = 1) -> None:
        self.reply = json.dumps({"label": label, "passage": passage, "reason": "r"})
        self.users: list[str] = []

    def __call__(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        self.users.append(messages[1]["content"])
        return {"content": self.reply, "ms": 12.0, "tokens": 9}


def test_the_judge_label_decides_the_sentence_and_each_call_is_recorded() -> None:
    chat = Chat("supported")
    verifier = ll.LoopVerifier(ll.LiveJudge(chat, "judge@rev"))
    v = verifier.check_sentence(PREMISE, "The employer gives written reasons.", query="q")
    assert v.verdict is Verdict.EMIT
    assert verifier.judge.calls[0]["label"] == "supported"
    assert verifier.committed == ["The employer gives written reasons."]
    verifier.judge.chat = Chat("not_stated", 0)
    v = verifier.check_sentence(PREMISE, "The employer pays a penalty.", query="q")
    assert v.verdict is Verdict.ROLLBACK
    assert verifier.committed == ["The employer gives written reasons."]


def test_the_judge_sees_only_committed_sentences_as_the_answer_so_far() -> None:
    chat = Chat("supported")
    verifier = ll.LoopVerifier(ll.LiveJudge(chat, "judge@rev"))
    verifier.check_sentence(PREMISE, "The employer gives written reasons.", query="q")
    verifier.check_sentence(PREMISE, "The tribunal may order reinstatement.", query="q")
    assert "<<<\n(none)\n>>>" in chat.users[0]
    assert "<<<\nThe employer gives written reasons.\n>>>" in chat.users[1]
    verifier.reset()
    assert verifier.committed == []
    assert verifier.judge.calls == []


def test_a_reply_that_never_parses_counts_as_not_stated() -> None:
    class Broken:
        def __call__(self, messages: list[dict[str, str]]) -> dict[str, Any]:
            return {"content": "no json here", "ms": 5.0, "tokens": 3}

    judge = ll.LiveJudge(Broken(), "judge@rev")
    probs = judge.score(["a passage"], "A sentence.")
    assert [p.neutral for p in probs] == [1.0]
    assert judge.calls[0]["label"] == "error"
    assert judge.calls[0]["attempts"] == 3


def test_the_chat_prompt_is_rendered_with_thinking_off() -> None:
    class Tokenizer:
        chat_template = "x"

        def apply_chat_template(self, messages: list[dict[str, str]], **kwargs: Any) -> Any:
            self.kwargs = kwargs
            return {"input_ids": [1, 2, 3]}

    backend = ll.ThinkingOff("http://x", Tokenizer(), model_id="m", eos=[0])
    assert backend.chat([{"role": "user", "content": "q"}]) == (1, 2, 3)
    assert backend.tokenizer.kwargs["enable_thinking"] is False
    assert backend.tokenizer.kwargs["add_generation_prompt"] is True


def test_the_two_arms_differ_only_in_prompt_and_steering() -> None:
    source = ll.engine(
        None, ll.LoopVerifier(ll.LiveJudge(Chat("supported"), "j")), "source", "legal"
    )
    closed = ll.engine(
        None, ll.LoopVerifier(ll.LiveJudge(Chat("supported"), "j")), "closed", "legal"
    )
    assert "{premise}" in source.system_prompt
    assert source.steering == "allow"
    assert "{premise}" not in closed.system_prompt
    assert closed.steering == "inject"
    assert closed.inject_template.format(query="Q?", source="S").count("<|im_start|>") == 2
    assert closed.inject_template.endswith("<think>\n\n</think>\n\n")
    assert (source.max_rollbacks, source.max_total_rollbacks) == (3, 8)
    assert source.verifier.config.ungrounded_figure == "judge"
    software = ll.engine(None, source.verifier, "closed", "software")
    assert "documentation" in software.inject_template
    assert "documentation" in software.refusal


def test_closed_arm_rolls_back_a_judged_sentence_and_regenerates_after_the_source() -> None:
    class Backend(ScriptedBackend):
        flushed = 0

        def flush_cache(self) -> None:
            self.flushed += 1

    class ByContent:
        """Supported only for the sentence that states the source's figure."""

        def __call__(self, messages: list[dict[str, str]]) -> dict[str, Any]:
            sentence = (
                messages[1]["content"].split("Sentence to check:\n<<<\n")[1].split("\n>>>")[0]
            )
            label = "supported" if "123,543" in sentence else "not_stated"
            reply = json.dumps({"label": label, "passage": 1, "reason": "r"})
            return {"content": reply, "ms": 3.0, "tokens": 5}

    verifier = ll.LoopVerifier(ll.LiveJudge(ByContent(), "judge@rev"))
    note = ll.INJECT["legal"].format(
        query=QUERY, source="The limit of a compensatory award is £123,543."
    )
    backend = Backend(["I do not know the limit.", note + "The limit is £123,543."])
    item = {"id": "x-01", "query": QUERY, "domain": "legal", "premise": SOURCE}
    out = ll.answer(backend, verifier, "closed", item)
    assert out["key"] == "x-01:closed"
    assert out["text"] == "The limit is £123,543."
    assert backend.flushed == 1
    sentence = out["trace"]["sentences"][0]
    assert [a["steering"] for a in sentence["attempts"]] == [None, "inject"]
    assert sentence["recovered_by"] == "inject"
    assert [c["label"] for c in out["judge_calls"]] == ["not_stated", "supported"]
    assert out["trace"]["verifier"]["nli"] == "judge@rev"


def test_the_judge_asks_for_the_short_reply_by_default() -> None:
    chat = Chat("supported")
    ll.LiveJudge(chat, "judge@rev").score(["a passage"], "A sentence.")
    assert chat.users[0].endswith("Give no reason.")
    assert '"reason"' not in chat.users[0]
    longer = Chat("supported")
    ll.LiveJudge(longer, "judge@rev", reply="reason").score(["a passage"], "A sentence.")
    assert longer.users[0].endswith('"reason" (one sentence).')
    assert chat.users[0].rsplit("Return JSON", 1)[0] == longer.users[0].rsplit("Return JSON", 1)[0]
