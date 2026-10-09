"""Stop 42 on Modal: Qwen3.8-27B as the auditor's judge, and the entailment models' score tables
(paid: run only on a go).

  uv run --with modal modal run scripts/modal_auditor_judge.py::download    # CPU: weights
  uv run --with modal modal run scripts/modal_auditor_judge.py::pilot       # H100: 5 dev texts
  uv run --with modal modal run scripts/modal_auditor_judge.py::judge       # H100: every clause
  uv run --with modal modal run scripts/modal_auditor_judge.py::classify    # L4: v0, controls

Sends judge prompts (a clause, its candidate passages, the answer so far) and (candidate, clause)
pairs. No grade, label or recorded verdict leaves this machine. Scoring is offline:
``scripts/auditor_judge.py report``.
"""

# No `from __future__ import annotations`: Modal reads function annotations at runtime.
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

import modal

ROOT = Path(__file__).resolve().parent.parent
SGLANG_IMAGE = "lmsysorg/sglang:v0.5.21"
PORT = 30000
WORKERS = 16
SEQUENTIAL = 20  # Part A prompts re-run one at a time per effort, for single-stream latency

judge_image = (
    modal.Image.from_registry(SGLANG_IMAGE)
    .env({"PYTHONPATH": "/app/src:/app/scripts", "HF_HOME": "/hf"})
    .add_local_dir(ROOT / "src", "/app/src")
    .add_local_file(ROOT / "scripts/auditor_judge.py", "/app/scripts/auditor_judge.py")
)
classifier_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("torch==2.14.1", "transformers==5.18.0")
    .env({"PYTHONPATH": "/app/src:/app/scripts", "HF_HOME": "/hf"})
    .add_local_dir(ROOT / "src", "/app/src")
    .add_local_file(ROOT / "scripts/auditor_judge.py", "/app/scripts/auditor_judge.py")
)
weights = modal.Volume.from_name("legal-rag-verifier-hf", create_if_missing=True)
app = modal.App("legal-rag-verifier-auditor-judge")


@app.function(image=classifier_image, timeout=3600, volumes={"/hf": weights})
def download() -> dict[str, str]:
    from auditor_judge import CLASSIFIERS, QWEN, QWEN_REVISION  # noqa: PLC0415
    from huggingface_hub import snapshot_download  # noqa: PLC0415

    snapshot_download(QWEN, revision=QWEN_REVISION)
    for spec in CLASSIFIERS.values():
        snapshot_download(spec["model"], revision=spec["revision"])
    weights.commit()
    return {QWEN: QWEN_REVISION, **{s["model"]: s["revision"] for s in CLASSIFIERS.values()}}


def _server() -> subprocess.Popen[bytes]:
    from auditor_judge import QWEN, QWEN_REVISION  # noqa: PLC0415

    return subprocess.Popen(  # noqa: S603
        [
            sys.executable, "-m", "sglang.launch_server",
            "--model-path", QWEN, "--revision", QWEN_REVISION,
            "--port", str(PORT), "--reasoning-parser", "qwen3",
            "--context-length", "65536", "--mem-fraction-static", "0.85",
        ]
    )  # fmt: skip


def _wait(server: subprocess.Popen[bytes]) -> str:
    url = f"http://127.0.0.1:{PORT}"
    deadline = time.time() + 1500
    while True:
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=5) as r:  # noqa: S310
                if r.status == 200:  # noqa: PLR2004
                    return url
        except OSError:
            pass
        if server.poll() is not None or time.time() > deadline:
            raise RuntimeError("SGLang server did not come up")
        time.sleep(5)


@app.function(image=judge_image, gpu="H100", timeout=4 * 3600, volumes={"/hf": weights})
def qwen_judge(runs: list[dict[str, Any]], sequential: dict[str, str]) -> dict[str, dict[str, Any]]:
    """Each run ``{name, effort, seed, requests: {sha: user prompt}}``, 16 at a time; then
    ``sequential`` one at a time per effort, for latency only."""
    from auditor_judge import judge_all, qwen_chat  # noqa: PLC0415

    gpu = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    server = _server()
    out: dict[str, dict[str, Any]] = {}
    try:
        url = _wait(server)
        efforts = []
        for run in runs:
            t0 = time.time()
            chat = qwen_chat(url, run["effort"], run["seed"])
            labels = judge_all(run["requests"], chat, WORKERS)
            out[run["name"]] = {"labels": labels, "seconds": time.time() - t0, "gpu": gpu}
            print(f"{run['name']}: {len(labels)} in {time.time() - t0:.0f} s", flush=True)
            if run["effort"] not in efforts:
                efforts.append(run["effort"])
        for effort in efforts if sequential else []:
            chat = qwen_chat(url, effort, 0)
            labels = judge_all(sequential, chat, 1)
            out[f"sequential-{effort}"] = {"labels": labels, "gpu": gpu}
    finally:
        server.terminate()
        server.wait(timeout=120)
    return out


@app.function(image=classifier_image, gpu="L4", timeout=3 * 3600, volumes={"/hf": weights})
def classifier(name: str, pairs: dict[str, list[str]]) -> dict[str, Any]:
    """``{pair_key: [premise, clause]}`` → ``{pair_key: [entailment, neutral, contradiction]}``
    with the verifier's own chunking (``SentenceNLIVerifier``) at the model's max length."""
    import torch  # noqa: PLC0415
    from auditor_judge import CLASSIFIERS  # noqa: PLC0415

    from legal_rag_verifier.nli import SentenceNLIVerifier  # noqa: PLC0415

    spec = CLASSIFIERS[name]

    class TwoWay:
        """Supported / unsupported logits with a contradiction column that softmaxes to 0."""

        def __init__(self, model: Any) -> None:
            self.model = model

        def __call__(self, **kwargs: Any) -> Any:
            logits = self.model(**kwargs).logits
            floor = torch.full_like(logits[:, :1], -1e4)
            return type("Out", (), {"logits": torch.cat([logits, floor], dim=-1)})()

    if spec["two_way"]:
        # MiniCheck's config names its labels "0" / "1": read 1 as entailment, 0 as neutral.
        from transformers import AutoConfig  # noqa: PLC0415

        config = AutoConfig.from_pretrained(spec["model"], revision=spec["revision"])
        assert config.id2label == {0: "0", 1: "1"}, config.id2label  # noqa: S101
        import transformers  # noqa: PLC0415

        original = transformers.AutoModelForSequenceClassification.from_pretrained

        def relabelled(*args: Any, **kwargs: Any) -> Any:
            model = original(*args, **kwargs)
            model.config.id2label = {0: "neutral", 1: "entailment", 2: "contradiction"}
            return model

        transformers.AutoModelForSequenceClassification.from_pretrained = relabelled
    scorer = SentenceNLIVerifier(
        spec["model"], "cuda", revision=spec["revision"], max_length=spec["max_length"]
    )
    if spec["two_way"]:
        scorer.model = TwoWay(scorer.model)
    by_clause: dict[str, list[str]] = {}
    for key, (_, clause) in pairs.items():
        by_clause.setdefault(clause, []).append(key)
    t0 = time.time()
    table: dict[str, list[float]] = {}
    for n, (clause, keys) in enumerate(by_clause.items(), 1):
        probs = scorer.score([pairs[k][0] for k in keys], clause)
        for k, p in zip(keys, probs, strict=True):
            table[k] = [round(p.entailment, 6), round(p.neutral, 6), round(p.contradiction, 6)]
        if n % 100 == 0:
            print(f"{name}: {n}/{len(by_clause)} clauses", flush=True)
    return {"model_id": scorer.model_id, "table": table, "seconds": time.time() - t0}


def _local() -> Any:
    sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT / "batteries/verifier")]
    import auditor_judge as aj  # noqa: PLC0415

    return aj


@app.local_entrypoint()
def pilot() -> None:
    """The 5 dev texts of the Gemini pilot, at each effort (not scored)."""
    aj = _local()
    asked, _ = aj.pilot_texts()
    runs = [
        {"name": f"pilot-{e}", "effort": e, "seed": 0, "requests": asked} for e in ("low", "xhigh")
    ]
    out = qwen_judge.remote(runs, {})
    path = aj.OUT / "pilot" / "qwen.json"  # git-ignored with the rest of the pilot
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for name, run in out.items():
        for r in run["labels"].values():
            print(name, r["label"], f"p{r['passage']}", f"{r['ms']:.0f} ms", r["tokens"])
            print("  ", r["reason"])


@app.local_entrypoint()
def judge() -> None:
    aj = _local()
    texts, _, recorded = aj.recorded_sets()
    asked = aj.requests(recorded)
    aj.assert_prompts_clean(texts, asked)
    part_a = aj.requests([r for r, t in zip(recorded, texts, strict=True) if t["level"] == "A"])
    runs = [
        {"name": name, "effort": effort, "seed": seed, "requests": part_a if seed else asked}
        for name, effort, seed in aj.QWEN_RUNS
    ]
    sequential = dict(list(part_a.items())[:SEQUENTIAL])
    out = qwen_judge.remote(runs, sequential)
    for name, run in out.items():
        aj.write_jsonl(
            aj.OUT / "labels" / f"{name}.jsonl",
            [{"sha": sha, **label} for sha, label in run["labels"].items()],
        )
        meta = {k: v for k, v in run.items() if k != "labels"}
        print(name, len(run["labels"]), json.dumps(meta))


@app.local_entrypoint()
def classify(only: str = "") -> None:
    aj = _local()
    _, _, recorded = aj.recorded_sets()
    rows, built = aj.dev_rows()
    wanted = aj.pairs(recorded) | aj.pairs(aj.record(rows, built, dev=True))
    names = [only] if only else list(aj.CLASSIFIERS)
    calls = {name: classifier.spawn(name, wanted) for name in names}
    for name, call in calls.items():
        out = call.get()
        path = aj.OUT / "scores" / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out["table"], sort_keys=True) + "\n", encoding="utf-8")
        meta = aj.OUT / "scores" / f"{name}.meta.json"
        meta.write_text(
            json.dumps({k: v for k, v in out.items() if k != "table"}, indent=1) + "\n",
            encoding="utf-8",
        )
        print(name, out["model_id"], len(out["table"]), f"{out['seconds']:.0f} s")
