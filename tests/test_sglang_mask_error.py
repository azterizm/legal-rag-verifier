"""``SGLangBackend.processor()`` says what the logit mask needs when torch or sglang is absent."""

from __future__ import annotations

import sys

import pytest

from legal_rag_verifier.backends.sglang import SGLangBackend
from tests.test_sglang_backend import EOS, CharTokenizer, FakeServer

MASK_MODULE = "legal_rag_verifier.backends._sglang_mask"
SGLANG_KEYS = (
    "sglang",
    "sglang.srt",
    "sglang.srt.sampling",
    "sglang.srt.sampling.custom_logit_processor",
)


def _backend(processor: str | None = None) -> SGLangBackend:
    return SGLangBackend(
        "http://fake",
        CharTokenizer(),
        model_id="fake@0",
        eos=[EOS],
        post=FakeServer([]),
        processor=processor,
    )


QUOTED = (  # the docs quote this text verbatim
    "steering 'allow' and 'ban' send a logit mask built by legal_rag_verifier.backends."
    "_sglang_mask, which needs torch and sglang installed where this client runs; the [sglang] "
    "extra installs neither. Install them (pip install torch sglang), or build the mask where "
    "they are installed with MaskProcessor().to_str() and pass it as SGLangBackend(..., "
    "processor=...), or use steering='inject', which needs neither."
)


def _assert_guided(excinfo: pytest.ExceptionInfo[ImportError]) -> None:
    message = str(excinfo.value)
    for needle in ("allow", "ban", "torch", "sglang", "processor=", "steering='inject'"):
        assert needle in message, needle
    assert message == QUOTED
    assert isinstance(excinfo.value.__cause__, ImportError)  # ModuleNotFoundError subclasses it
    assert excinfo.value.__cause__ is not excinfo.value


def test_missing_torch_raises_a_guiding_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "torch", None)
    monkeypatch.delitem(sys.modules, MASK_MODULE, raising=False)
    with pytest.raises(ImportError) as excinfo:
        _backend().processor()
    _assert_guided(excinfo)


def test_missing_sglang_raises_a_guiding_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in SGLANG_KEYS:
        monkeypatch.setitem(sys.modules, key, None)
    monkeypatch.delitem(sys.modules, MASK_MODULE, raising=False)
    with pytest.raises(ImportError) as excinfo:
        _backend().processor()
    _assert_guided(excinfo)


def test_given_processor_is_returned_without_importing_the_mask(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "torch", None)
    monkeypatch.delitem(sys.modules, MASK_MODULE, raising=False)
    assert _backend(processor="<mask>").processor() == "<mask>"
    assert MASK_MODULE not in sys.modules
