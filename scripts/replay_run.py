"""Stop 29, SGLang phase (runs in the container): arms R0 to R4 from each shared rollback state.

Method: ``docs/GRID.md`` § Stop 29. Per state the server cache is flushed, the first draft is
decoded again from the committed answer and compared with the recorded rejected draft (parity),
and then:

- R0: A's recorded retry (its allow-list or ban, from the same seed tokens; where A's retry decoded
  nothing and the point was refused, that refusal is recorded, not replayed);
- R1: B's retry, the provision inserted at the cut point as a user turn, cache warm;
- R2: R1's exact tokens after the cache is flushed;
- R3: the same provision text after the query in the user turn, the committed answer re-prefilled;
- R4: R1's turn without the provision.

Each retry is audited, then (except R2) followed by ``FOLLOW_ON`` sentences decoded with no
rollback, each audited. One-token probes time the R1 input warm and cold. The token ids and the
spans the attention phase needs (provision windows in the prompt, the inserted copy, the top copy)
are returned.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from grid_qwen import (  # type: ignore[import-not-found]  # noqa: E402
    INJECT,
    INJECT_STYLE,
    MAX_NEW_TOKENS,
)

from legal_rag_verifier.backends.sglang import SGLangBackend  # noqa: E402
from legal_rag_verifier.engine import (  # noqa: E402
    Allow,
    Ban,
    Constraint,
    FinishReason,
    InFlightGenerator,
    _Draft,
    _Stream,
)
from legal_rag_verifier.premise import Premise  # noqa: E402
from legal_rag_verifier.verifier import Verifier  # noqa: E402

HEADER = "The provision for your next point:\n"
TURN: str = INJECT[INJECT_STYLE]
NO_SOURCE = TURN.replace(HEADER + "{source}\n\n", "")
FOLLOW_ON = 2
Spans = list[list[int]]  # [start, end) token ranges


def constraint_of(recorded: Mapping[str, Any]) -> Constraint:
    if "allow" in recorded:
        return Allow(tuple(tuple(int(t) for t in s) for s in recorded["allow"]))
    return Ban(frozenset(int(t) for t in recorded["ban"]))


def token_spans(offsets: Sequence[Sequence[int]], ranges: Sequence[tuple[int, int]]) -> Spans:
    """Token ranges covering the character ranges (a token counts if it overlaps one)."""
    spans: Spans = []
    for start, end in ranges:
        hit = [i for i, (s, e) in enumerate(offsets) if s < end and e > start]
        if hit:
            spans.append([hit[0], hit[-1] + 1])
    return spans


class Replayer:
    def __init__(self, url: str, model_path: str, revision: str) -> None:
        from legal_rag_verifier.nli import SentenceNLIVerifier  # noqa: PLC0415

        self.backend = SGLangBackend.connect(url, model_path, revision=revision)
        self.verifier = Verifier(
            SentenceNLIVerifier("cross-encoder/nli-deberta-v3-base", "cuda", local_files_only=False)
        )
        self.engine = InFlightGenerator(
            self.backend,
            self.verifier,
            max_new_tokens=MAX_NEW_TOKENS,
            steering="inject",
            inject_template=TURN,
        )

    # ------------------------------------------------------------------ pieces
    def _draft(
        self,
        prompt: Sequence[int],
        context: Sequence[int],
        answer: Sequence[int],
        seed: Sequence[int] = (),
        *,
        constraint: Constraint | None = None,
        end: FinishReason | None = None,
    ) -> _Draft:
        stream = _Stream(list(answer), list(context))
        return self.engine._draft(tuple(prompt), stream, list(seed), end, constraint)

    def _audit(self, item: Mapping[str, Any], tokens: Sequence[int]) -> dict[str, Any]:
        sentence = self.backend.decode(tokens).strip()
        if not sentence:
            return {"text": "", "verdict": "EMPTY", "reasons": []}
        verdict = self.verifier.check_sentence(item["premise"], sentence, query=item["query"])
        full = verdict.to_dict()
        return {"text": sentence, "verdict": full["verdict"], "reasons": full["reasons"]}

    def _arm(
        self,
        item: Mapping[str, Any],
        prompt: Sequence[int],
        context: Sequence[int],
        answer: Sequence[int],
        draft: _Draft,
        *,
        follow: bool = True,
    ) -> dict[str, Any]:
        out: dict[str, Any] = {
            "tokens": list(draft.tokens),
            **self._audit(item, draft.tokens),
            "decode_calls": draft.calls,
            "prefix_cache_hit_tokens": draft.hit_tokens,
            "decode_latency_ns": draft.latency_ns,
            "follow_on": [],
        }
        if not follow:
            return out
        context, answer = [*context, *draft.tokens], [*answer, *draft.tokens]
        seed, end = list(draft.lookahead), draft.end
        for _ in range(FOLLOW_ON * 3):  # whitespace-only drafts do not count
            if len(out["follow_on"]) == FOLLOW_ON or (end and not seed):
                break
            nxt = self._draft(prompt, context, answer, seed, end=end)
            context, answer = [*context, *nxt.tokens], [*answer, *nxt.tokens]
            seed, end = list(nxt.lookahead), nxt.end
            if self.backend.decode(nxt.tokens).strip():
                out["follow_on"].append(
                    {"tokens": list(nxt.tokens), **self._audit(item, nxt.tokens)}
                )
        return out

    def _probe(self, tokens: Sequence[int]) -> dict[str, int]:
        segment = self.backend.extend(tokens, stop=(), max_new=1, constraint=None)
        return {"latency_ns": segment.latency_ns, "hit": segment.prefix_cache_hit_tokens}

    def _spans(
        self, messages: list[dict[str, str]], premise: Premise, windows: Sequence[int]
    ) -> dict[str, Any]:
        """Token spans of the inserted windows and of the other windows in the system prompt."""
        tokenizer = self.backend.tokenizer
        text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        enc = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
        if list(enc["input_ids"]) != list(self.backend.chat(messages)):
            raise ValueError("prompt text does not re-tokenize to the prompt")
        base = text.index("Provisions:\n")
        ranges: dict[int, tuple[int, int]] = {}
        for i, p in enumerate(premise.passages):
            block = f"[{p.heading}]\n{p.text}" if p.heading else p.text
            at = text.find(block, base)
            if at >= 0:
                ranges[i] = (at, at + len(block))
        offsets = enc["offset_mapping"]
        return {
            "inserted_windows": token_spans(offsets, [ranges[i] for i in windows if i in ranges]),
            "other_windows": token_spans(
                offsets, [r for i, r in ranges.items() if i not in windows]
            ),
            "windows_found": [len(ranges), len(premise.passages)],
        }

    def _copy_span(self, text: str, tokens: Sequence[int], source: str, offset: int) -> Spans:
        """Token span of ``source`` inside ``text`` (whose tokens are ``tokens``), shifted."""
        enc = self.backend.tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
        if list(enc["input_ids"]) != list(tokens):
            raise ValueError("text does not re-tokenize to its tokens")
        at = text.index(HEADER + source) + len(HEADER)
        spans = token_spans(enc["offset_mapping"], [(at, at + len(source))])
        return [[s + offset, e + offset] for s, e in spans]

    # ------------------------------------------------------------------ one state
    def run(self, item: Mapping[str, Any]) -> dict[str, Any]:
        backend, engine, premise = self.backend, self.engine, item["premise"]
        backend.flush_cache()
        messages = engine.messages(item["query"], premise)
        prompt = list(backend.chat(messages))
        committed = list(backend.encode(item["committed"]))
        first = self._draft(prompt, committed, committed)
        rejected = backend.decode(first.tokens).strip()
        out: dict[str, Any] = {
            "id": item["id"],
            "prompt_tokens": len(prompt),
            "committed_tokens": len(committed),
            "parity": rejected == item["rejected"],
            "X": {"tokens": list(first.tokens), "text": rejected},
        }
        if not out["parity"]:
            return out

        recorded = item["a_retry"]
        if recorded is None:  # A's retry decoded nothing and the point was refused: not replayed
            out["R0"] = {"text": "", "verdict": "REFUSED", "reasons": [], "follow_on": []}
        else:
            seed = first.tokens[: recorded["tokens_reused"]]
            constraint = constraint_of(recorded["constraint"])
            d0 = self._draft(prompt, committed, committed, seed, constraint=constraint)
            out["R0"] = self._arm(item, prompt, committed, committed, d0)

        source, windows = engine._source_text(premise, item["windows"], set())
        note_text = TURN.format(source=source)
        note = list(backend.encode(note_text))
        c1 = [*committed, *note]
        out["probe_warm"] = self._probe([*prompt, *c1])
        d1 = self._draft(prompt, c1, committed)
        out["R1"] = self._arm(item, prompt, c1, committed, d1)
        out["R1"]["note_tokens"] = len(note)

        backend.flush_cache()
        out["probe_cold"] = self._probe([*prompt, *c1])
        backend.flush_cache()
        d2 = self._draft(prompt, c1, committed)
        out["R2"] = self._arm(item, prompt, c1, committed, d2, follow=False)
        out["R2"]["same_tokens_as_R1"] = list(d2.tokens) == list(d1.tokens)

        top_messages = [
            messages[0],
            {"role": "user", "content": f"{item['query']}\n\n{HEADER}{source}"},
        ]
        prompt_top = list(backend.chat(top_messages))
        d3 = self._draft(prompt_top, committed, committed)
        out["R3"] = self._arm(item, prompt_top, committed, committed, d3)

        c4 = [*committed, *backend.encode(NO_SOURCE)]
        d4 = self._draft(prompt, c4, committed)
        out["R4"] = self._arm(item, prompt, c4, committed, d4)

        top_text = backend.tokenizer.apply_chat_template(
            top_messages, tokenize=False, add_generation_prompt=True
        )
        out["replay"] = {
            "prompt": prompt,
            "committed": committed,
            "note": note,
            "prompt_top": prompt_top,
            "windows": windows,
            "spans": {
                **self._spans(messages, premise, windows),
                "inserted_copy": self._copy_span(
                    note_text, note, source, len(prompt) + len(committed)
                ),
                "top_copy": self._copy_span(top_text, prompt_top, source, 0),
            },
        }
        return out
