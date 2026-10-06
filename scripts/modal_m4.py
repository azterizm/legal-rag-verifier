"""M4 on Modal: SGLang + Qwen 2.5 7B on one L4, driven by the same engine (paid: run only on a go).

  uv run --with modal modal run scripts/modal_m4.py::probe      # CPU: image, Python, sglang import
  uv run --with modal modal run scripts/modal_m4.py::download   # CPU: weights into the volume
  uv run --with modal modal run scripts/modal_m4.py             # L4, ≤ 30 min: the spike

Writes results/m4-sglang.json. Only public statute text and the demo queries leave this machine.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

import modal

ROOT = Path(__file__).resolve().parent.parent
MODEL = "Qwen/Qwen2.5-7B-Instruct"
SGLANG_IMAGE = "lmsysorg/sglang:v0.5.21"
PORT = 30000

image = (
    modal.Image.from_registry(SGLANG_IMAGE)
    .pip_install("pytest")  # tests/conftest.py (fixture loader) imports it
    .env({"PYTHONPATH": "/app/src:/app/scripts:/app/tests", "HF_HOME": "/hf"})
    .add_local_dir(ROOT / "src", "/app/src")
    .add_local_dir(ROOT / "scripts", "/app/scripts")
    .add_local_dir(ROOT / "tests", "/app/tests")
)
weights = modal.Volume.from_name("legal-rag-verifier-hf", create_if_missing=True)
app = modal.App("legal-rag-verifier-m4", image=image)


@app.function(timeout=600)
def probe() -> dict[str, Any]:
    """Python version, sglang version, and that our mask processor imports in the image."""
    import importlib.metadata  # noqa: PLC0415

    from legal_rag_verifier.backends._sglang_mask import MaskProcessor  # noqa: PLC0415

    return {
        "python": sys.version,
        "sglang": importlib.metadata.version("sglang"),
        "processor_bytes": len(MaskProcessor().to_str()),
    }


@app.function(timeout=1800, volumes={"/hf": weights})
def download() -> str:
    from huggingface_hub import model_info, snapshot_download  # noqa: PLC0415

    sha = str(model_info(MODEL).sha)
    snapshot_download(MODEL, revision=sha, allow_patterns=["*.json", "*.safetensors", "*.txt"])
    snapshot_download("cross-encoder/nli-deberta-v3-base")
    weights.commit()
    return sha


@app.function(gpu="L4", timeout=1800, volumes={"/hf": weights})
def spike(revision: str) -> dict[str, Any]:
    server = subprocess.Popen(  # noqa: S603
        [
            sys.executable, "-m", "sglang.launch_server",
            "--model-path", MODEL, "--revision", revision,
            "--port", str(PORT), "--mem-fraction-static", "0.70",
            "--enable-custom-logit-processor",
        ]
    )  # fmt: skip
    url = f"http://127.0.0.1:{PORT}"
    try:
        deadline = time.time() + 900
        while True:
            try:
                with urllib.request.urlopen(f"{url}/health", timeout=5) as r:  # noqa: S310
                    if r.status == 200:  # noqa: PLR2004
                        break
            except OSError:
                pass
            if server.poll() is not None or time.time() > deadline:
                raise RuntimeError("SGLang server did not come up")
            time.sleep(5)
        from m4_spike import run  # noqa: PLC0415

        return run(url, MODEL, revision)
    finally:
        server.terminate()


@app.local_entrypoint()
def main() -> None:
    revision = download.remote()
    result = spike.remote(revision)
    out = ROOT / "results" / "m4-sglang.json"
    out.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result["round_trip"]), "→", out.relative_to(ROOT))
