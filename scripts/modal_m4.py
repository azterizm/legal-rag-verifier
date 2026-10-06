"""M4 on Modal: SGLang + Qwen 2.5 7B on one L4, driven by the same engine (paid: run only on a go).

  uv run --with modal modal run scripts/modal_m4.py::check      # CPU: image, Python, sglang import
  uv run --with modal modal run scripts/modal_m4.py::download   # CPU: weights into the volume
  uv run --with modal modal run scripts/modal_m4.py::main       # L4, ≤ 30 min: the spike
  uv run --with modal modal run scripts/modal_m4.py::latency    # L4, ≤ 30 min: round-trip profile

Writes results/m4-sglang.json / results/m4-profile.json. Only public statute text and the demo
queries leave this machine.
"""

from __future__ import annotations

import contextlib
import json
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
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


@contextlib.contextmanager
def sglang_server(revision: str, *extra: str) -> Iterator[str]:
    server = subprocess.Popen(  # noqa: S603
        [
            sys.executable, "-m", "sglang.launch_server",
            "--model-path", MODEL, "--revision", revision,
            "--port", str(PORT), "--mem-fraction-static", "0.70",
            "--enable-custom-logit-processor", *extra,
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
        yield url
    finally:
        server.terminate()
        server.wait(timeout=120)


@app.function(gpu="L4", timeout=1800, volumes={"/hf": weights})
def spike(revision: str) -> dict[str, Any]:
    from m4_spike import run  # noqa: PLC0415

    with sglang_server(revision) as url:
        return run(url, MODEL, revision)


@app.function(gpu="L4", timeout=1800, volumes={"/hf": weights})
def profile(revision: str) -> dict[str, Any]:
    """The round trip split up, in bf16 (as M4) and with FP8 weights (L4 is Ada: native FP8)."""
    from m4_profile import profile as measure  # noqa: PLC0415

    gpu = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    out: dict[str, Any] = {"gpu": gpu, "generator": f"{MODEL}@{revision}"}
    for name, flags in (("bf16", ()), ("fp8", ("--quantization", "fp8"))):
        try:
            with sglang_server(revision, *flags) as url:
                out[name] = measure(url, MODEL, revision)
        except Exception as error:  # noqa: BLE001 - keep the other variant's numbers
            out[name] = {"error": repr(error)}
        print(name, json.dumps(out[name]), flush=True)
    return out


@app.local_entrypoint()
def check() -> None:
    print(json.dumps(probe.remote()))


@app.local_entrypoint()
def latency() -> None:
    result = profile.remote(download.remote())
    out = ROOT / "results" / "m4-profile.json"
    out.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("→", out.relative_to(ROOT))


@app.local_entrypoint()
def main() -> None:
    revision = download.remote()
    result = spike.remote(revision)
    out = ROOT / "results" / "m4-sglang.json"
    out.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result["round_trip"]), "→", out.relative_to(ROOT))
