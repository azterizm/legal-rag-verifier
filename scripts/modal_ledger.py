"""Modal spend for stops 43 to 47: a ledger of GPU time at list prices, with a hard stop.

Prices are Modal's per-second list prices read on 2026-10-09, plus 15 % for CPU, memory and idle
time. Each run is recorded when it returns, before the next starts; ``check`` refuses a run whose
estimate would take the ledger past the cap.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "results/distill/modal_ledger.json"
PER_HOUR = {"L4": 0.80, "L40S": 1.95, "A100-80GB": 2.50, "H100": 3.95, "CPU": 0.10}
OVERHEAD = 1.15
CAP = 55.0


class ModalBudgetError(RuntimeError):
    """A run would take the Modal ledger past its cap."""


def usd(gpu: str, seconds: float) -> float:
    return round(PER_HOUR[gpu] * seconds / 3600 * OVERHEAD, 4)


def entries() -> list[dict[str, Any]]:
    if not LEDGER.exists():
        return []
    data: list[dict[str, Any]] = json.loads(LEDGER.read_text(encoding="utf-8"))
    return data


def spent() -> float:
    return round(sum(float(e["usd"]) for e in entries()), 4)


def check(gpu: str, estimate_seconds: float) -> None:
    if spent() + usd(gpu, estimate_seconds) > CAP:
        raise ModalBudgetError(f"Modal: ${spent():.2f} spent, cap ${CAP:.2f}")


def record(run: str, gpu: str, seconds: float, note: str = "") -> None:
    data = entries()
    data.append(
        {
            "run": run,
            "gpu": gpu,
            "seconds": round(seconds, 1),
            "usd": usd(gpu, seconds),
            "note": note,
        }
    )
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    tmp = LEDGER.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    tmp.replace(LEDGER)
