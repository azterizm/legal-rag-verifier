"""M4 on Modal: SGLang + Qwen 2.5 7B on one L4, driven by the same engine (paid: run only on a go).

  uv run --with modal modal run scripts/modal_m4.py::check      # CPU: image, Python, sglang import
  uv run --with modal modal run scripts/modal_m4.py::download   # CPU: weights into the volume
  uv run --with modal modal run scripts/modal_m4.py::main       # L4, ≤ 30 min: the spike
  uv run --with modal modal run scripts/modal_m4.py::latency    # L4, ≤ 30 min: round-trip profile
  uv run --with modal modal run scripts/modal_m4.py::grid       # L4: grid cells 4B and 4D
  uv run --with modal modal run scripts/modal_m4.py::grid --cells 4B-inject   # stop 27 A/B

Writes results/m4-sglang.json / results/m4-profile.json. Only public statute text and the demo
queries leave this machine.
"""

# No `from __future__ import annotations`: Modal reads class parameter types at runtime.
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


@app.cls(gpu="L4", timeout=3600, volumes={"/hf": weights}, scaledown_window=600)
class Grid:
    """One SGLang server for all of 4B and 4D; called a chunk at a time so the run can resume."""

    revision: str = modal.parameter()

    @modal.enter()
    def start(self) -> None:
        from grid_qwen import QwenCells  # noqa: PLC0415

        self._server = sglang_server(self.revision)
        url = self._server.__enter__()
        self.cells = QwenCells(url, MODEL, self.revision)

    @modal.exit()
    def stop(self) -> None:
        self._server.__exit__(None, None, None)

    @modal.method()
    def run(self, cell: str, items: list[tuple[str, str, Any]]) -> list[dict[str, Any]]:
        generator = f"{MODEL}@{self.revision}"
        return [
            {"cell": cell, "id": i, "generator": generator, **self.cells.run(cell, query, premise)}
            for i, query, premise in items
        ]


@app.local_entrypoint()
def grid(
    cells: str = "4B,4D", limit: int = 0, chunk: int = 8, split: str = "test", tag: str = ""
) -> None:
    """``--split dev`` writes under results/grid/dev/; ``--tag`` suffixes the file name (a
    re-run of a cell that already has results, e.g. ``--cells 4B --limit 10 --tag=-parity``)."""
    sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT / "batteries/verifier")]
    from grid_gemini import OUT, done_ids  # noqa: PLC0415
    from grid_prompts import premise, rows  # noqa: PLC0415

    selected = rows(split)[: limit or None]
    out = OUT if split == "test" else OUT / split
    revision = download.remote()
    runner = Grid(revision=revision)
    out.mkdir(parents=True, exist_ok=True)
    for cell in cells.split(","):
        path = out / f"{cell}{tag}.jsonl"
        todo = [r for r in selected if r["id"] not in done_ids(path)]
        for start in range(0, len(todo), chunk):
            items = [(r["id"], r["query"], premise(r)) for r in todo[start : start + chunk]]
            records = runner.run.remote(cell, items)
            with path.open("a", encoding="utf-8") as f:
                f.writelines(json.dumps(rec, ensure_ascii=False) + "\n" for rec in records)
            print(f"{cell}: {start + len(items)}/{len(todo)}", flush=True)


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
