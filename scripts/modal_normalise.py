"""Stop 41 on Modal: the auditor's three arms on one L4 (paid: run only on a go).

  uv run --with modal modal run scripts/modal_normalise.py      # → results/normalise/audit.jsonl

Sends the software battery's documentation, the kept facts and the texts to audit. No grade and
no recorded verdict leave this machine. Scoring is offline: ``scripts/nli_normalised.py``.
"""

# No `from __future__ import annotations`: Modal reads function annotations at runtime.
import json
import sys
from pathlib import Path
from typing import Any

import modal

ROOT = Path(__file__).resolve().parent.parent

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("torch==2.14.1", "transformers==5.18.0")
    .env({"PYTHONPATH": "/app/src:/app/scripts", "HF_HOME": "/hf"})
    .add_local_dir(ROOT / "src", "/app/src")
    .add_local_file(ROOT / "scripts/nli_normalised.py", "/app/scripts/nli_normalised.py")
)
weights = modal.Volume.from_name("legal-rag-verifier-hf", create_if_missing=True)
app = modal.App("legal-rag-verifier-normalise", image=image)


@app.function(gpu="L4", timeout=3600, volumes={"/hf": weights})
def audit(
    items: list[dict[str, Any]], sources: dict[str, Any], facts: dict[str, Any]
) -> list[dict[str, Any]]:
    from huggingface_hub import snapshot_download  # noqa: PLC0415
    from nli_normalised import NLI_MODEL  # noqa: PLC0415
    from nli_normalised import audit as run  # noqa: PLC0415

    snapshot_download(NLI_MODEL)  # already in the volume (modal_m4.download); a no-op then
    return run(items, sources, facts)


@app.local_entrypoint()
def main() -> None:
    sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT / "batteries/verifier")]
    from nli_normalised import OUT, assert_prompts_clean, blind, inputs  # noqa: PLC0415

    items, sources, facts = inputs()
    assert_prompts_clean(items)
    records = audit.remote(blind(items), sources, facts)
    path = OUT / "audit.jsonl"
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8"
    )
    print(f"{len(records)} texts → {path.relative_to(ROOT)}")
