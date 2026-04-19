"""Embedder backends. Plug in via the ``Embedder`` protocol."""

from __future__ import annotations

import os

from ..embedder import Embedder


def make_embedder(name: str | None = None) -> Embedder:
    """Return an embedder instance for the requested backend name.

    Reads ``KB_EMBEDDER`` when ``name`` is None. Only the local bge-m3
    backend is wired up in this build; OpenAI lands with the extractor
    phase.
    """
    backend = (name or os.environ.get("KB_EMBEDDER") or "local").lower()
    if backend == "local":
        from .local import LocalEmbedder

        model = os.environ.get("KB_EMBEDDER_MODEL", "BAAI/bge-m3")
        return LocalEmbedder(model_name=model)
    raise ValueError(f"unknown embedder backend: {backend!r}")


__all__ = ["make_embedder"]
