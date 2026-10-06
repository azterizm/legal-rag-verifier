"""Build the enrichment layer for every premise of a battery (accuracy plan step 2).

Usage: uv run python scripts/enrich_premises.py batteries/verifier/dev.jsonl [--dry-run]

One unit per provision (or dated version) in the battery's premises; each unit's text is sent
once to ``gemini-3.8-flash-high`` through the user's local router (``/v1/chat/completions`` only —
no other endpoint, no other model). Only public statute text is sent. Replies are audited
(``legal_rag_verifier.enrichment.audit_entry``) and cached under ``enrichment/<model>/``, keyed by
the source text's sha256, so a unit is never paid for twice. Paid calls approved 2026-10-06.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "batteries/verifier"))

import premises  # noqa: E402

from legal_rag_verifier.citations import render_citation  # noqa: E402
from legal_rag_verifier.enrichment import audit_entry  # noqa: E402
from legal_rag_verifier.premise import PassageKind, Premise  # noqa: E402

ROUTER_URL = "http://localhost:8317/v1/chat/completions"
MODEL = "gemini-3.8-flash-high"
OUT = ROOT / "enrichment" / MODEL
KEY_FILE = ROOT / ".router_key"  # git-ignored, mode 600

SYSTEM = (
    "You are a senior UK lawyer writing a public practice manual. Use ONLY the statutory text "
    "you are given. Reply with a single JSON object."
)
USER = """Provision: {citation} of the {title}{version}.
<<<
{text}
>>>

Return JSON with keys:
  "elements": every rule, condition, exception and definition the text states, each
     {{"requirement": one standalone plain-English sentence that names who or what it applies to
       (never "this section" or "the person" without saying who) and keeps every qualifier,
       limit and condition, "quote": a short phrase copied EXACTLY from the text that supports it}},
  "thresholds": every amount, period, age, count, percentage or date in the text, each
     {{"what": what the figure is for, "value": the figure exactly as written in the text,
       "quote": a phrase copied EXACTLY from the text that contains the figure}}."""
PROMPT_SHA = hashlib.sha256((SYSTEM + USER).encode()).hexdigest()


def _key() -> str:
    return os.environ.get("LLM_ROUTER_KEY") or KEY_FILE.read_text(encoding="utf-8").strip()


def _extract_json(text: str) -> dict[str, Any]:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in output")
    parsed: dict[str, Any] = json.loads(text[start : end + 1])
    return parsed


def _chat(messages: list[dict[str, str]]) -> str:
    body = json.dumps({"model": MODEL, "messages": messages, "temperature": 0}).encode()
    request = urllib.request.Request(
        ROUTER_URL,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {_key()}"},
    )
    with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310
        content: str = json.loads(response.read())["choices"][0]["message"]["content"]
    return content


def ask(user: str) -> tuple[dict[str, Any], int]:
    """One JSON reply; re-asks (at most twice) only when the reply is not JSON."""
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    out = ""
    for attempt in range(1, 4):
        out = _chat(messages)
        try:
            return _extract_json(out), attempt
        except ValueError:
            messages = [
                *messages[:2],
                {"role": "assistant", "content": out},
                {"role": "user", "content": "Reply with ONLY the JSON object."},
            ]
    raise ValueError(f"no JSON after 3 attempts: {out[:200]!r}")


def units(premise: Premise) -> dict[str, dict[str, Any]]:
    """Provision windows grouped by section coordinate and version."""
    groups: dict[str, dict[str, Any]] = {}
    for passage in premise.passages:
        if passage.kind is PassageKind.FACT or not passage.coordinate:
            continue
        parts = passage.coordinate.split("/")
        section = "/".join(parts[: len(parts) - len(passage.tail.split("/")) + 1])
        version = passage.valid_from.isoformat() if passage.valid_from else "current"
        key = f"{section}@{version}"
        unit = groups.setdefault(
            key,
            {"section": section, "version": version, "heading": passage.heading or "", "texts": []},
        )
        unit["texts"].append(passage.text)
    return groups


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("battery", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="list units, call nothing")
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.battery.read_text(encoding="utf-8").splitlines()]
    todo: dict[str, dict[str, Any]] = {}
    for row in rows:
        premise, _ = premises.build(row, ROOT / "data")
        title = premise.titles[0] if premise.titles else ""
        for key, unit in units(premise).items():
            todo.setdefault(key, {**unit, "title": title})
    OUT.mkdir(parents=True, exist_ok=True)
    calls = cached = 0
    for key, unit in sorted(todo.items()):
        text = "\n".join(unit["texts"])
        sha = hashlib.sha256(text.encode()).hexdigest()
        path = OUT / (re.sub(r"[^A-Za-z0-9]+", "_", key) + ".json")
        if path.exists() and json.loads(path.read_text(encoding="utf-8"))["source_sha256"] == sha:
            cached += 1
            continue
        if args.dry_run:
            print("would call:", key, len(text), "chars")
            continue
        tail = unit["section"].split("/")[-1]
        version = "" if unit["version"] == "current" else f", as in force from {unit['version']}"
        user = USER.format(
            citation=render_citation(tail), title=unit["title"], version=version, text=text
        )
        raw, attempts = ask(user)
        calls += attempts
        audit = audit_entry(raw, text)
        entry = {
            "key": key,
            "section": unit["section"],
            "version": unit["version"],
            "source_sha256": sha,
            "model": MODEL,
            "prompt_sha256": PROMPT_SHA,
            "attempts": attempts,
            "raw": raw,
            **audit.to_dict(),
        }
        path.write_text(json.dumps(entry, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        a = entry["audit"]
        print(
            f"{key}: elements {a['elements_verified']}/{a['elements_proposed']}, "
            f"thresholds {a['thresholds_verified']}/{a['thresholds_proposed']}",
            flush=True,
        )
    print(json.dumps({"units": len(todo), "cached": cached, "router_calls": calls}))


if __name__ == "__main__":
    main()
