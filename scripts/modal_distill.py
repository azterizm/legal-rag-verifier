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
import urllib.error
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
    "qwen27-low": {
        "model": QWEN27,
        "revision": QWEN27_REVISION,
        "gpu": "H100",
        "args": ["--reasoning-parser", "qwen3", *CONTEXT],
        # stop 42's settings: thinking on, low effort, the card's sampling
        "sampling": {
            "temperature": 1.0,
            "top_p": 0.95,
            "top_k": 20,
            "min_p": 0.0,
            "max_tokens": 16384,
            "seed": 0,
        },
        "template": {"enable_thinking": True, "reasoning_effort": "low"},
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


class _JudgeServer:
    """One judge model behind SGLang, started once per container."""

    name: str

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


_JUDGE_OPTIONS: dict[str, Any] = {
    "image": judge_image,
    "volumes": {"/hf": weights},
    "timeout": 4 * 3600,
    "max_containers": 1,
    "scaledown_window": 60,
}


@app.cls(gpu="L4", **_JUDGE_OPTIONS)
class Judge(_JudgeServer):
    name: str = modal.parameter()


@app.cls(gpu="L40S", **_JUDGE_OPTIONS)
class JudgeL40S(_JudgeServer):
    name: str = modal.parameter()


@app.cls(gpu="H100", **_JUDGE_OPTIONS)
class JudgeH100(_JudgeServer):
    name: str = modal.parameter()


@app.function(image=judge_image, gpu="L40S", timeout=1800, volumes={"/hf": weights})
def raw_replies(name: str, prompts: list[str]) -> list[dict[str, Any]]:
    """Debug: the server's full reply to each per-clause prompt, first ask only."""
    spec = JUDGES[name]
    server = subprocess.Popen(  # noqa: S603
        [
            sys.executable, "-m", "sglang.launch_server",
            "--model-path", spec["model"], "--revision", spec["revision"],
            "--port", str(PORT), "--mem-fraction-static", "0.85", *spec["args"],
        ]
    )  # fmt: skip
    url = f"http://127.0.0.1:{PORT}"
    out = []
    try:
        _wait(server, url)
        from auditor_judge import SYSTEM  # noqa: PLC0415

        for user in prompts:
            body = {
                "model": spec["model"],
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": user},
                ],
                **spec["sampling"],
                "chat_template_kwargs": spec["template"],
            }
            req = urllib.request.Request(  # noqa: S310 - the container's own server
                f"{url}/v1/chat/completions",
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=900) as r:  # noqa: S310
                    out.append(json.loads(r.read()))
            except urllib.error.HTTPError as exc:
                out.append({"status": exc.code, "body": exc.read().decode()[:2000]})
    finally:
        server.terminate()
    return out


@app.local_entrypoint()
def debug_judge(name: str, n: int = 5) -> None:
    aj, _ = _judge_local()
    texts, _, recorded = aj.recorded_sets()
    part_a = aj.requests([r for r, t in zip(recorded, texts, strict=True) if t["level"] == "A"])
    for reply in raw_replies.remote(name, list(part_a.values())[:n]):
        print(json.dumps(reply, ensure_ascii=False)[:1500])


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
    have = {k: v for k, v in aj.read_labels(name).items() if v["label"] != "error"}
    todo = {k: v for k, v in asked.items() if k not in have}
    part_a = aj.requests([r for r, t in zip(recorded, texts, strict=True) if t["level"] == "A"])
    seq_have = {
        k: v for k, v in aj.read_labels(f"{name}-sequential").items() if v["label"] != "error"
    }
    seq_todo = {k: v for k, v in list(part_a.items())[:sequential] if k not in seq_have}
    print(f"{name}: {len(todo)} to judge, {len(seq_todo)} one at a time", flush=True)
    if not todo and not seq_todo:
        return
    ledger.check(spec["gpu"], 3600)
    judge = JUDGE_CLASSES[spec["gpu"]](name=name)
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


# ------------------------------------------------------------------ stop 45: pool answers


@app.local_entrypoint()
def pool_answers() -> None:
    """Every pool question, with source and closed-book. Resumable."""
    sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT / "batteries/verifier")]
    import distill_data  # noqa: PLC0415
    import modal_ledger as ledger  # noqa: PLC0415

    done = distill_data.answers()
    todo = [r for r in distill_data.requests() if r["key"] not in done]
    print(f"{len(done)} done, {len(todo)} to answer", flush=True)
    if not todo:
        return
    ledger.check("L4", 3600)
    chunks = [todo[i : i + CHUNK] for i in range(0, len(todo), CHUNK)]
    startup_recorded = False
    for out in Generator().answer.map(chunks, return_exceptions=True):
        if isinstance(out, Exception):
            print(f"chunk failed, retried on the next run: {out!r}", flush=True)
            continue
        good = [r for r in out["results"] if r.get("text") is not None]
        distill_data.append_answers(good)
        seconds = out["seconds"] + (0 if startup_recorded else out["startup"])
        startup_recorded = True
        ledger.record("stop45 pool answers", "L4", seconds, f"{len(good)} answers")
    print(f"Modal spent ${ledger.spent():.2f}")


# ------------------------------------------------------------------ stop 46: the student

runs = modal.Volume.from_name("legal-rag-verifier-runs", create_if_missing=True)
train_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "torch==2.14.0",
        "transformers==5.17.0",
        "peft==0.21.0",
        "trl==1.13.0",
        "accelerate==1.15.0",
        "datasets==5.0.1",
        "bitsandbytes==0.50.2",
    )
    .env({"HF_HOME": "/hf"})
)
STUDENTS: dict[str, dict[str, Any]] = {
    "k2": {"model": K2, "revision": K2_REVISION, "four_bit": False},
}
TRAIN_SEED = 20261009


@app.function(
    image=train_image, gpu="H100", timeout=8 * 3600, volumes={"/hf": weights, "/runs": runs}
)
def train(student: str, epochs: int = 1, max_tokens: int = 8192, *, smoke: bool = False) -> dict:
    """LoRA on the teacher's replies, no reasoning. Checkpoints go to the runs volume and are
    committed on every save, so a lost container resumes from the last one."""
    import torch  # noqa: PLC0415
    from datasets import Dataset  # noqa: PLC0415
    from peft import LoraConfig  # noqa: PLC0415
    from transformers import (  # noqa: PLC0415
        AutoModelForCausalLM,
        AutoTokenizer,
        TrainerCallback,
    )
    from trl import SFTConfig, SFTTrainer  # noqa: PLC0415

    spec = STUDENTS[student]
    out = Path("/runs") / student / ("smoke" if smoke else "run")
    tokenizer = AutoTokenizer.from_pretrained(
        spec["model"], revision=spec["revision"], trust_remote_code=True
    )

    def load(split: str) -> list[dict[str, Any]]:
        rows = [json.loads(x) for x in Path(f"/runs/data/{split}.jsonl").read_text().splitlines()]
        kept = []
        for r in rows:
            system, user, reply = r["messages"]
            messages = [system, user, {**reply, "reasoning_content": ""}]
            ids = tokenizer.apply_chat_template(messages, tokenize=True)
            if len(ids) <= max_tokens:
                kept.append({"messages": messages})
        return kept

    train_rows = load("train")
    dropped = sum(1 for _ in Path("/runs/data/train.jsonl").read_text().splitlines()) - len(
        train_rows
    )
    if smoke:
        train_rows = train_rows[:64]
    quant: dict[str, Any] = {}
    if spec["four_bit"]:
        from transformers import BitsAndBytesConfig  # noqa: PLC0415

        quant["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_quant_type="nf4"
        )
    model = AutoModelForCausalLM.from_pretrained(
        spec["model"],
        revision=spec["revision"],
        dtype=torch.bfloat16,
        trust_remote_code=True,
        attn_implementation="sdpa",
        **quant,
    )

    class Commit(TrainerCallback):  # type: ignore[misc]
        def on_save(self, *args: Any, **kwargs: Any) -> None:
            runs.commit()

    config = SFTConfig(
        output_dir=str(out / "checkpoints"),
        num_train_epochs=epochs,
        max_steps=10 if smoke else -1,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=16,
        learning_rate=1e-4,
        lr_scheduler_type="cosine",
        warmup_steps=0.03,  # a float below 1 is a ratio of total steps
        bf16=True,
        gradient_checkpointing=True,
        logging_steps=5,
        save_steps=5 if smoke else 50,
        save_total_limit=2,
        assistant_only_loss=True,
        loss_type="nll",
        router_aux_loss_coef=0.0,  # K2 7B has no experts
        max_length=max_tokens,
        report_to=[],
        seed=TRAIN_SEED,
    )
    trainer = SFTTrainer(
        model=model,
        args=config,
        train_dataset=Dataset.from_list(train_rows),
        processing_class=tokenizer,
        peft_config=LoraConfig(
            r=16,
            lora_alpha=32,
            lora_dropout=0.05,
            target_modules="all-linear",
            task_type="CAUSAL_LM",
        ),
        callbacks=[Commit()],
    )
    t0 = time.time()
    resume = any((out / "checkpoints").glob("checkpoint-*"))
    result = trainer.train(resume_from_checkpoint=True if resume else None)
    trainer.save_model(str(out / "adapter"))
    runs.commit()
    return {
        "examples": len(train_rows),
        "dropped_over_max_tokens": dropped,
        "seconds": time.time() - t0,
        "loss": result.training_loss,
        "log": trainer.state.log_history[-20:],
        "resumed": resume,
    }


@app.function(image=train_image, gpu="H100", timeout=3600, volumes={"/hf": weights, "/runs": runs})
def merge(student: str, *, smoke: bool = False) -> str:
    """The adapter merged into the base in bf16, with the base's code and tokenizer files."""
    import shutil  # noqa: PLC0415

    import torch  # noqa: PLC0415
    from huggingface_hub import snapshot_download  # noqa: PLC0415
    from peft import PeftModel  # noqa: PLC0415
    from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: PLC0415

    spec = STUDENTS[student]
    run = Path("/runs") / student / ("smoke" if smoke else "run")
    base = AutoModelForCausalLM.from_pretrained(
        spec["model"], revision=spec["revision"], dtype=torch.bfloat16, trust_remote_code=True
    )
    merged = PeftModel.from_pretrained(base, str(run / "adapter")).merge_and_unload()
    target = run / "merged"
    merged.save_pretrained(str(target), safe_serialization=True)
    AutoTokenizer.from_pretrained(
        spec["model"], revision=spec["revision"], trust_remote_code=True
    ).save_pretrained(str(target))
    snapshot = Path(snapshot_download(spec["model"], revision=spec["revision"]))
    for f in [*snapshot.glob("*.py"), *snapshot.glob("*.jinja"), snapshot / "config.json"]:
        if f.exists():
            shutil.copy(f, target / f.name)  # the base's config keeps auto_map and archs
    runs.commit()
    return str(target)


@app.local_entrypoint()
def train_student(student: str = "k2", epochs: int = 1, smoke: bool = False) -> None:  # noqa: FBT001, FBT002
    """Upload train / validation, train (resumes from the last checkpoint), merge. Ledgered."""
    sys.path[:0] = [str(ROOT / "scripts")]
    import modal_ledger as ledger  # noqa: PLC0415

    data = ROOT / "results/distill"
    with runs.batch_upload(force=True) as batch:
        for split in ("train", "validation"):
            batch.put_file(str(data / f"{split}.jsonl"), f"/data/{split}.jsonl")
    ledger.check("H100", 1800 if smoke else 4 * 3600)
    t0 = time.time()
    try:
        out = train.remote(student, epochs, smoke=smoke)
    finally:
        run = f"stop46 train {student}{' smoke' if smoke else ''}"
        ledger.record(run, "H100", time.time() - t0)
    print(json.dumps({k: v for k, v in out.items() if k != "log"}, indent=1))
    for row in out["log"][-5:]:
        print(row)
    t0 = time.time()
    try:
        print(merge.remote(student, smoke=smoke))
    finally:
        ledger.record(f"stop46 merge {student}", "H100", time.time() - t0)


# ------------------------------------------------------------------ stop 46: the student served


class _StudentServer:
    """The merged student behind SGLang. The reply follows an empty reasoning block, exactly as
    in training, so the student never thinks."""

    path: str

    @modal.enter()
    def start(self) -> None:
        from transformers import AutoTokenizer  # noqa: PLC0415

        self.started = time.time()
        self.tokenizer = AutoTokenizer.from_pretrained(self.path)
        self.server = subprocess.Popen(  # noqa: S603
            [
                sys.executable, "-m", "sglang.launch_server", "--model-path", self.path,
                "--port", str(PORT), "--mem-fraction-static", "0.85", *CONTEXT,
            ]
        )  # fmt: skip
        self.url = f"http://127.0.0.1:{PORT}"
        _wait(self.server, self.url)
        self.startup = time.time() - self.started

    @modal.exit()
    def stop(self) -> None:
        self.server.terminate()

    def _prompt(self, messages: list[dict[str, str]]) -> str:
        marker = "\x00REPLY\x00"
        full = [
            *messages,
            {"role": "assistant", "content": marker, "reasoning_content": ""},
        ]
        text: str = self.tokenizer.apply_chat_template(full, tokenize=False)
        return text[: text.index(marker)]

    def _chat(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        sent = [{**m, "reasoning_content": ""} if m["role"] == "assistant" else m for m in messages]
        body = {
            "model": self.path,
            "prompt": self._prompt(sent),
            "temperature": 0,
            "max_tokens": 512,
            "stop": ["<|ifm|im_end|>"],
        }
        request = urllib.request.Request(  # noqa: S310 - the container's own server
            f"{self.url}/v1/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        t0 = time.perf_counter()
        with urllib.request.urlopen(request, timeout=900) as r:  # noqa: S310
            out = json.loads(r.read())
        return {
            "content": out["choices"][0]["text"],
            "ms": (time.perf_counter() - t0) * 1000,
            "tokens": out.get("usage", {}).get("completion_tokens"),
        }

    @modal.method()
    def judge(self, requests: dict[str, str], workers: int) -> dict[str, Any]:
        from auditor_judge import judge_all  # noqa: PLC0415

        t0 = time.time()
        labels = judge_all(requests, self._chat, workers)
        return {"labels": labels, "seconds": time.time() - t0, "startup": self.startup}


@app.cls(
    gpu="L40S",
    image=judge_image,
    volumes={"/hf": weights, "/runs": runs},
    timeout=4 * 3600,
    max_containers=1,
    scaledown_window=60,
)
class StudentL40S(_StudentServer):
    path: str = modal.parameter()


@app.local_entrypoint()
def student_eval(
    student: str = "k2", sequential: int = 20, run: str = "run", limit: int = 0
) -> None:
    """The merged student on the validation prompts and stop 42's 280 prompts (16 at a time,
    chunks of 40), then ``sequential`` Part A prompts one at a time. Resumable."""
    aj, ledger = _judge_local()
    name = f"{student}-student" if run == "run" else f"{student}-{run}"
    texts, _, recorded = aj.recorded_sets()
    asked = aj.requests(recorded)
    aj.assert_prompts_clean(texts, asked)
    rows = (ROOT / "results/distill/validation.jsonl").read_text(encoding="utf-8").splitlines()
    validation = {r["sha"]: r["messages"][1]["content"] for r in map(json.loads, rows)}
    part_a = aj.requests([r for r, t in zip(recorded, texts, strict=True) if t["level"] == "A"])
    server = StudentL40S(path=f"/runs/{student}/{run}/merged")
    ledger.check("L40S", 3600)
    startup_recorded = False
    for label_name, wanted, workers in (
        (f"{name}-validation", validation, WORKERS),
        (name, asked, WORKERS),
        (f"{name}-sequential", dict(list(part_a.items())[:sequential]), 1),
    ):
        have = {k for k, v in aj.read_labels(label_name).items() if v["label"] != "error"}
        items = [(k, v) for k, v in wanted.items() if k not in have]
        items = items[:limit] if limit else items
        print(f"{label_name}: {len(items)} to judge", flush=True)
        size = CHUNK if workers > 1 else len(items) or 1
        chunks = [dict(items[i : i + size]) for i in range(0, len(items), size)]
        for out in server.judge.map(chunks, kwargs={"workers": workers}, return_exceptions=True):
            if isinstance(out, Exception):
                print(f"chunk failed, retried on the next run: {out!r}", flush=True)
                continue
            _append(aj, label_name, out["labels"])
            seconds = out["seconds"] + (0 if startup_recorded else out["startup"])
            startup_recorded = True
            ledger.record(f"stop46 {label_name}", "L40S", seconds, f"{len(out['labels'])}")
    print(f"Modal spent ${ledger.spent():.2f}")


# ------------------------------------------------------------------ stop 47: the fresh test

JUDGE_CLASSES = {"L4": Judge, "L40S": JudgeL40S, "H100": JudgeH100}
classifier_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("torch==2.14.1", "transformers==5.18.0")
    .env({"PYTHONPATH": "/app/src", "HF_HOME": "/hf"})
    .add_local_dir(ROOT / "src", "/app/src")
)
V0_MODEL = "cross-encoder/nli-deberta-v3-base"
V0_REVISION = "6c749ce3425cd33b46d187e45b92bbf96ee12ec7"


@app.function(image=classifier_image, gpu="L4", timeout=3600, volumes={"/hf": weights})
def v0_table(pairs: dict[str, list[str]]) -> dict[str, Any]:
    """V0's probabilities per (candidate, clause), with the verifier's own chunking."""
    from legal_rag_verifier.nli import SentenceNLIVerifier  # noqa: PLC0415

    scorer = SentenceNLIVerifier(V0_MODEL, "cuda", revision=V0_REVISION)
    by_clause: dict[str, list[str]] = {}
    for key, (_, clause) in pairs.items():
        by_clause.setdefault(clause, []).append(key)
    t0 = time.time()
    table: dict[str, list[float]] = {}
    for clause, keys in by_clause.items():
        for k, p in zip(keys, scorer.score([pairs[k][0] for k in keys], clause), strict=True):
            table[k] = [round(p.entailment, 6), round(p.neutral, 6), round(p.contradiction, 6)]
    return {"model_id": scorer.model_id, "table": table, "seconds": time.time() - t0}


def _fresh_local() -> Any:
    sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT / "batteries/verifier")]
    import auditor_judge  # noqa: PLC0415
    import fresh_eval  # noqa: PLC0415
    import modal_ledger  # noqa: PLC0415

    return auditor_judge, fresh_eval, modal_ledger


def _fresh_append(fe: Any, name: str, labels: dict[str, Any]) -> None:
    path = fe.LABELS / f"{name}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for sha, label in labels.items():
            f.write(json.dumps({"sha": sha, **label}, ensure_ascii=False) + "\n")


@app.local_entrypoint()
def fresh_judges(names: str = "v0,qwen27-low,qwen27-nothink,k2-low") -> None:
    """Every fresh per-clause prompt to each named judge (``k2-student`` for the student).
    Resumable: a rerun asks only prompts with no label or an error."""
    aj, fe, ledger = _fresh_local()
    us, _, rec = fe.recorded()
    asked = aj.requests(rec)
    fe.assert_blind(us, asked)
    for name in names.split(","):
        if name == "v0":
            path = fe.OUT / "scores" / "v0.json"
            if path.exists():
                continue
            ledger.check("L4", 1800)
            t0 = time.time()
            out = v0_table.remote(aj.pairs(rec))
            ledger.record("stop47 fresh v0", "L4", time.time() - t0)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(out["table"], sort_keys=True) + "\n", encoding="utf-8")
            print(f"v0: {len(out['table'])} pairs, {out['model_id']}", flush=True)
            continue
        have = {k for k, v in fe.read(name).items() if v["label"] != "error"}
        items = [(k, v) for k, v in asked.items() if k not in have]
        print(f"{name}: {len(items)} to judge", flush=True)
        if not items:
            continue
        if name.endswith("-student"):
            gpu = "L40S"
            server = StudentL40S(path=f"/runs/{name.removesuffix('-student')}/run/merged")
        else:
            gpu = JUDGES[name]["gpu"]
            server = JUDGE_CLASSES[gpu](name=name)
        ledger.check(gpu, 3600)
        chunks = [dict(items[i : i + CHUNK]) for i in range(0, len(items), CHUNK)]
        startup_recorded = False
        for out in server.judge.map(chunks, kwargs={"workers": WORKERS}, return_exceptions=True):
            if isinstance(out, Exception):
                print(f"{name}: chunk failed, retried on the next run: {out!r}", flush=True)
                continue
            _fresh_append(fe, name, out["labels"])
            seconds = out["seconds"] + (0 if startup_recorded else out["startup"])
            startup_recorded = True
            ledger.record(f"stop47 fresh {name}", gpu, seconds, f"{len(out['labels'])}")
    print(f"Modal spent ${ledger.spent():.2f}")
