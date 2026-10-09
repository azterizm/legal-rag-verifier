"""Stops 43 to 47 on Modal (paid: run only on a go). Every entrypoint is resumable: results are
written locally per chunk as they return, and a rerun skips what is done.

  uv run --with modal modal run scripts/modal_distill.py::fresh_answers    # L4: stop 43 answers

Sends prompts only (questions and sources). No grade or label leaves this machine.
"""

# No `from __future__ import annotations`: Modal reads function annotations at runtime.
import json
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import modal

ROOT = Path(__file__).resolve().parent.parent
SGLANG_IMAGE = "lmsysorg/sglang:v0.5.21"
GENERATOR = "Qwen/Qwen2.5-7B-Instruct"
GENERATOR_REVISION = "a09a35458c702b33eeacc393d103063234e8bc28"  # as stops 27 to 37
PORT = 30000
CHUNK = 40
WORKERS = 16

sglang_image = modal.Image.from_registry(SGLANG_IMAGE).env({"HF_HOME": "/hf"})
judge_image = (
    modal.Image.from_registry(SGLANG_IMAGE)
    .env({"HF_HOME": "/hf", "PYTHONPATH": "/app/src:/app/scripts"})
    .add_local_dir(ROOT / "src", "/app/src")
    .add_local_file(ROOT / "scripts/auditor_judge.py", "/app/scripts/auditor_judge.py")
)
K2 = "IFM/K2-Horizon-7B"
K2_REVISION = "3b6ae394c1b863c27a306d168b25555837955192"
weights = modal.Volume.from_name("legal-rag-verifier-hf", create_if_missing=True)
app = modal.App("legal-rag-verifier-distill")


def _wait(server: "subprocess.Popen[bytes]", url: str, limit: float = 1500) -> None:
    deadline = time.time() + limit
    while True:
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=5) as r:  # noqa: S310
                if r.status == 200:  # noqa: PLR2004
                    return
        except OSError:
            pass
        if server.poll() is not None or time.time() > deadline:
            raise RuntimeError("SGLang server did not come up")
        time.sleep(5)


@app.function(image=sglang_image, timeout=1800, volumes={"/hf": weights})
def probe() -> dict[str, Any]:
    """CPU: the SGLang version, and whether it registers K2 Horizon's architecture natively."""
    import importlib.metadata  # noqa: PLC0415

    from sglang.srt.models.registry import ModelRegistry  # noqa: PLC0415

    archs = ModelRegistry.get_supported_archs()
    return {
        "sglang": importlib.metadata.version("sglang"),
        "K2HorizonForCausalLM": "K2HorizonForCausalLM" in archs,
        "k2_like": sorted(a for a in archs if "k2" in a.lower() or "horizon" in a.lower()),
    }


@app.function(image=sglang_image, timeout=3600, volumes={"/hf": weights})
def download_k2() -> str:
    from huggingface_hub import snapshot_download  # noqa: PLC0415

    snapshot_download(K2, revision=K2_REVISION)
    weights.commit()
    return K2_REVISION


@app.local_entrypoint()
def check_k2() -> None:
    print(probe.remote())
    print(download_k2.remote())


@app.cls(
    image=sglang_image,
    gpu="L4",
    volumes={"/hf": weights},
    timeout=3600,
    max_containers=1,
    scaledown_window=60,
)
class Generator:
    """Qwen 2.5 7B Instruct behind SGLang, started once per container."""

    @modal.enter()
    def start(self) -> None:
        self.started = time.time()
        self.server = subprocess.Popen(  # noqa: S603
            [
                sys.executable, "-m", "sglang.launch_server",
                "--model-path", GENERATOR, "--revision", GENERATOR_REVISION,
                "--port", str(PORT), "--mem-fraction-static", "0.85",
            ]
        )  # fmt: skip
        self.url = f"http://127.0.0.1:{PORT}"
        _wait(self.server, self.url)
        self.startup = time.time() - self.started

    @modal.exit()
    def stop(self) -> None:
        self.server.terminate()

    def _one(self, request: dict[str, Any]) -> dict[str, Any]:
        body = {
            "model": GENERATOR,
            "messages": request["messages"],
            "temperature": 0,
            "max_tokens": 512,
        }
        for attempt in range(3):
            try:
                req = urllib.request.Request(  # noqa: S310 - the container's own server
                    f"{self.url}/v1/chat/completions",
                    data=json.dumps(body).encode(),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=600) as r:  # noqa: S310
                    out = json.loads(r.read())
                choice = out["choices"][0]
                return {
                    "key": request["key"],
                    "text": choice["message"]["content"],
                    "finish": choice.get("finish_reason"),
                    "tokens": out.get("usage", {}).get("completion_tokens"),
                    "model": f"{GENERATOR}@{GENERATOR_REVISION}",
                }
            except OSError as exc:
                error = repr(exc)
                time.sleep(5 * (attempt + 1))
        return {"key": request["key"], "text": None, "error": error}

    @modal.method()
    def answer(self, chunk: list[dict[str, Any]]) -> dict[str, Any]:
        t0 = time.time()
        with ThreadPoolExecutor(WORKERS) as pool:
            results = list(pool.map(self._one, chunk))
        return {"results": results, "seconds": time.time() - t0, "startup": self.startup}


def _local() -> Any:
    sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT / "batteries/verifier")]
    import fresh_battery  # noqa: PLC0415
    import modal_ledger  # noqa: PLC0415

    return fresh_battery, modal_ledger


@app.local_entrypoint()
def fresh_answers() -> None:
    fresh, ledger = _local()
    done = fresh.answers()
    todo = [r for r in fresh.requests() if r["key"] not in done]
    print(f"{len(done)} done, {len(todo)} to answer", flush=True)
    if not todo:
        return
    ledger.check("L4", 1800)
    chunks = [todo[i : i + CHUNK] for i in range(0, len(todo), CHUNK)]
    startup_recorded = False
    for out in Generator().answer.map(chunks, return_exceptions=True):
        if isinstance(out, Exception):
            print(f"chunk failed, retried on the next run: {out!r}", flush=True)
            continue
        good = [r for r in out["results"] if r.get("text") is not None]
        fresh.append_answers(good)
        seconds = out["seconds"] + (0 if startup_recorded else out["startup"])
        startup_recorded = True
        ledger.record("stop43 fresh answers", "L4", seconds, f"{len(good)} answers")
        print(f"{len(good)}/{len(out['results'])} answers, {out['seconds']:.0f} s", flush=True)
    print(f"Modal spent ${ledger.spent():.2f}")


# ------------------------------------------------------------------ stop 44: untrained baselines

CONTEXT = ("--context-length", "65536")
QWEN27 = "Qwen/Qwen3.8-27B-FP8"
QWEN27_REVISION = "017b9c7af6b5689d5dd426a76e0bc077eb5ca20a"
JUDGES: dict[str, dict[str, Any]] = {
    "qwen27-nothink": {
        "model": QWEN27,
        "revision": QWEN27_REVISION,
        "gpu": "L40S",
        "args": ["--reasoning-parser", "qwen3", "--context-length", "65536"],
        # the card's non-thinking sampling
        "sampling": {
            "temperature": 0.7,
            "top_p": 0.8,
            "top_k": 20,
            "min_p": 0.0,
            "presence_penalty": 1.5,
            "max_tokens": 1024,
            "seed": 0,
        },
        "template": {"enable_thinking": False},
    },
    "k2-low": {
        "model": K2,
        "revision": K2_REVISION,
        "gpu": "L40S",  # SGLang serves K2 in FP8 only from pre-quantised weights; bf16 here
        "args": ["--reasoning-parser", "k2_horizon", *CONTEXT],
        # the card's recommended sampling, low effort
        "sampling": {"temperature": 1.0, "top_p": 0.95, "max_tokens": 16384, "seed": 0},
        "template": {"reasoning_effort": "low"},
    },
}


@app.cls(
    image=judge_image,
    gpu="L4",
    volumes={"/hf": weights},
    timeout=4 * 3600,
    max_containers=1,
    scaledown_window=60,
)
class Judge:
    """One judge model behind SGLang, started once per container."""

    name: str = modal.parameter()

    @modal.enter()
    def start(self) -> None:
        spec = JUDGES[self.name]
        self.started = time.time()
        self.server = subprocess.Popen(  # noqa: S603
            [
                sys.executable, "-m", "sglang.launch_server",
                "--model-path", spec["model"], "--revision", spec["revision"],
                "--port", str(PORT), "--mem-fraction-static", "0.85", *spec["args"],
            ]
        )  # fmt: skip
        self.url = f"http://127.0.0.1:{PORT}"
        _wait(self.server, self.url)
        self.startup = time.time() - self.started

    @modal.exit()
    def stop(self) -> None:
        self.server.terminate()

    @modal.method()
    def judge(self, requests: dict[str, str], workers: int) -> dict[str, Any]:
        from auditor_judge import judge_all, server_chat  # noqa: PLC0415

        spec = JUDGES[self.name]
        chat = server_chat(self.url, spec["model"], spec["sampling"], spec["template"])
        t0 = time.time()
        labels = judge_all(requests, chat, workers)
        return {"labels": labels, "seconds": time.time() - t0, "startup": self.startup}


def _judge_local() -> Any:
    sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT / "batteries/verifier")]
    import auditor_judge  # noqa: PLC0415
    import modal_ledger  # noqa: PLC0415

    return auditor_judge, modal_ledger


def _append(aj: Any, name: str, labels: dict[str, Any]) -> None:
    path = aj.OUT / "labels" / f"{name}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for sha, label in labels.items():
            if label.get("label") != "error" or label.get("attempts", 0) >= 3:  # noqa: PLR2004
                f.write(json.dumps({"sha": sha, **label}, ensure_ascii=False) + "\n")


@app.local_entrypoint()
def baselines(name: str, sequential: int = 20) -> None:
    """Every stop 42 per-clause prompt, 16 at a time in chunks of 40; then ``sequential`` Part A
    prompts one at a time, for latency. Resumable: done prompts are skipped."""
    aj, ledger = _judge_local()
    spec = JUDGES[name]
    texts, _, recorded = aj.recorded_sets()
    asked = aj.requests(recorded)
    aj.assert_prompts_clean(texts, asked)
    have = aj.read_labels(name)
    todo = {k: v for k, v in asked.items() if k not in have}
    part_a = aj.requests([r for r, t in zip(recorded, texts, strict=True) if t["level"] == "A"])
    seq_have = aj.read_labels(f"{name}-sequential")
    seq_todo = {k: v for k, v in list(part_a.items())[:sequential] if k not in seq_have}
    print(f"{name}: {len(todo)} to judge, {len(seq_todo)} one at a time", flush=True)
    if not todo and not seq_todo:
        return
    ledger.check(spec["gpu"], 3600)
    judge = Judge.with_options(gpu=spec["gpu"])(name=name)
    items = list(todo.items())
    chunks = [dict(items[i : i + CHUNK]) for i in range(0, len(items), CHUNK)]
    startup_recorded = False
    for out in judge.judge.map(chunks, kwargs={"workers": WORKERS}, return_exceptions=True):
        if isinstance(out, Exception):
            print(f"chunk failed, retried on the next run: {out!r}", flush=True)
            continue
        _append(aj, name, out["labels"])
        seconds = out["seconds"] + (0 if startup_recorded else out["startup"])
        startup_recorded = True
        ledger.record(f"stop44 {name}", spec["gpu"], seconds, f"{len(out['labels'])} prompts")
        print(f"{len(out['labels'])} prompts, {out['seconds']:.0f} s", flush=True)
    if seq_todo:
        out = judge.judge.remote(seq_todo, 1)
        _append(aj, f"{name}-sequential", out["labels"])
        ledger.record(f"stop44 {name} sequential", spec["gpu"], out["seconds"])
    print(f"Modal spent ${ledger.spent():.2f}")
