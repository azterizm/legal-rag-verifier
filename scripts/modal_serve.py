"""Stop 78: serve the qwen27-ar4 judge on Modal for the live check.

Paid run: run only on a go. Run as:
  LIVE_JUDGE_API_KEY=... uv run --with modal==1.2.6 modal serve scripts/modal_serve.py

Guards against runaway spend:
- exactly one container (max_containers=1);
- idle scale-down after 120 seconds (scaledown_window=120);
- pre-cached weights on product-answer-checks-hf volume with HF_HUB_OFFLINE=1 (no downloads);
- the operator runs under a wall-clock limit (45 minutes, checked in modal_ledger) and stops the
  server immediately after the live check and smoke runs finish.
"""

import os
import subprocess
import sys

import modal

# Model and revision from scripts/modal_distill.py:244-247 (QUANT["qwen27-ar4"])
MODEL = "Vishva007/Qwen3.8-27B-W4A16-AutoRound-GPTQ"
REVISION = "1b9d56b428e9f841d7ad566f87660b5f47553c97"
PORT = 30000

if modal.is_local():
    key = os.environ.get("LIVE_JUDGE_API_KEY", "").strip()
    if not key:
        sys.exit("Error: LIVE_JUDGE_API_KEY environment variable is not set or empty")
    try:
        from legal_rag_verifier.judge import PRESETS

        assert PRESETS["qwen27-ar4"].model == MODEL  # noqa: S101
        assert PRESETS["qwen27-ar4"].revision == REVISION  # noqa: S101
    except ImportError:
        pass

app = modal.App("legal-rag-verifier-live78")
image = modal.Image.from_registry("lmsysorg/sglang:v0.5.21").env(
    {"HF_HOME": "/hf", "HF_HUB_OFFLINE": "1"}
)
weights = modal.Volume.from_name("product-answer-checks-hf")
secret = modal.Secret.from_dict({"LIVE_JUDGE_API_KEY": os.environ.get("LIVE_JUDGE_API_KEY", "")})


@app.function(
    image=image,
    volumes={"/hf": weights},
    gpu="L40S",
    max_containers=1,
    scaledown_window=120,
    secrets=[secret],
)
@modal.web_server(port=PORT, startup_timeout=1500)
@modal.concurrent(max_inputs=100)
def serve() -> None:
    subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            "-m",
            "sglang.launch_server",
            "--model-path",
            MODEL,
            "--revision",
            REVISION,
            "--port",
            str(PORT),
            "--mem-fraction-static",
            "0.85",
            "--reasoning-parser",
            "qwen3",
            "--context-length",
            "65536",
            "--host",
            "0.0.0.0",  # noqa: S104
            "--api-key",
            os.environ["LIVE_JUDGE_API_KEY"],
        ]
    )
