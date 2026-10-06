"""Seal the held-out battery before it runs (plan R1): hash everything the result depends on.

Usage: uv run python batteries/verifier/seal.py --id heldout-YYYY-MM-DD
Writes ``batteries/verifier/seals/<id>.json`` and renames nothing; ``scripts/run_battery.py``
refuses a held-out battery unless its sha256 matches a seal, and refuses to run it twice.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_rag_verifier import __version__  # noqa: E402
from legal_rag_verifier.enrichment import load  # noqa: E402

SEALS = HERE / "seals"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True)
    parser.add_argument(
        "--enrichment", type=Path, default=ROOT / "enrichment/gemini-3.8-flash-high"
    )
    args = parser.parse_args()
    battery = HERE / "heldout_draft.jsonl"
    commit = subprocess.run(  # noqa: S603
        ["/usr/bin/git", "-C", str(ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    dirty = subprocess.run(  # noqa: S603
        ["/usr/bin/git", "-C", str(ROOT), "status", "--porcelain", "--", "src", "batteries"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if dirty:
        raise SystemExit(f"commit src/ and batteries/ before sealing:\n{dirty}")
    seal = {
        "id": args.id,
        "sealed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "verifier_version": __version__,
        "verifier_commit": commit,
        "battery": {"file": battery.name, "sha256": sha256(battery)},
        "rows_source": {"file": "heldout_rows.toml", "sha256": sha256(HERE / "heldout_rows.toml")},
        "anchors": {"file": "anchors.toml", "sha256": sha256(HERE / "anchors.toml")},
        "enrichment_layer": load(args.enrichment).layer_id,
        "rows": sum(1 for _ in battery.open(encoding="utf-8")),
    }
    SEALS.mkdir(exist_ok=True)
    out = SEALS / f"{args.id}.json"
    if out.exists():
        raise SystemExit(f"{out} exists: a seal is never overwritten")
    out.write_text(json.dumps(seal, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(seal, indent=2))


if __name__ == "__main__":
    main()
