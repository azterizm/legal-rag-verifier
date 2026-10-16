"""Sentence-level claim and NLI verification with KV-cache rollback during generation."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("legal-rag-verifier")
except PackageNotFoundError:  # running from a source tree that is not installed
    __version__ = "0+unknown"
