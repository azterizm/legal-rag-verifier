"""Building the DeBERTa NLI head warns that it did not improve answers, even without [nli].

No test here downloads a model: either torch is blocked, or ``from_pretrained`` runs with
``local_files_only=True`` on a model name that is not in the cache.
"""

from __future__ import annotations

import contextlib
import sys
import tomllib
import warnings
from pathlib import Path

import pytest

from legal_rag_verifier.nli import SentenceNLIVerifier

PREFIX = "The DeBERTa NLI head did not improve answers"
PARTS = ("58.3%–68.7%", "90.1%–93.8%", "docs/VERDICT.md", "legal_rag_verifier.judge")
IGNORE = f"ignore:{PREFIX}:UserWarning"
PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"
UNKNOWN_MODEL = "no-such/model"


def _deberta(record: list[warnings.WarningMessage]) -> list[warnings.WarningMessage]:
    return [w for w in record if str(w.message).startswith(PREFIX)]


def _build_without_torch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Construct the verifier with torch and transformers made unimportable."""
    monkeypatch.setitem(sys.modules, "torch", None)
    monkeypatch.setitem(sys.modules, "transformers", None)
    with contextlib.suppress(ImportError):
        SentenceNLIVerifier(UNKNOWN_MODEL, device="cpu")


def test_warning_is_raised() -> None:
    # ImportError without the [nli] extra; OSError from from_pretrained(local_files_only=True).
    with (
        pytest.warns(UserWarning, match="docs/VERDICT.md") as record,
        contextlib.suppress(ImportError, OSError),
    ):
        SentenceNLIVerifier(UNKNOWN_MODEL, device="cpu")
    assert len(_deberta(record.list)) == 1


def test_message_category_and_caller() -> None:
    with (
        pytest.warns(UserWarning, match=PREFIX) as record,
        contextlib.suppress(ImportError, OSError),
    ):
        SentenceNLIVerifier(UNKNOWN_MODEL, device="cpu")
    (warning,) = _deberta(record.list)
    message = str(warning.message)
    assert message.startswith(PREFIX)
    for part in PARTS:
        assert part in message, part
    assert warning.category is UserWarning
    assert Path(warning.filename).resolve() == Path(__file__).resolve()  # stacklevel=2


def test_warning_fires_before_torch_import(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.warns(UserWarning, match=PREFIX) as record:
        _build_without_torch(monkeypatch)
    assert len(_deberta(record.list)) == 1


def test_pyproject_ignores_the_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    filters: list[str] = config["tool"]["pytest"]["ini_options"]["filterwarnings"]
    assert IGNORE in filters
    # Under the configured filters ("error" + the ignore entry) building it must not error.
    _build_without_torch(monkeypatch)
