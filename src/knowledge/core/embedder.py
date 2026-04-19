"""Embedder protocol — text in, vectors out.

Backends (local bge-m3, OpenAI, Voyage) live under knowledge.core.embedders
and plug in via this protocol. Callers never import a concrete embedder.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    """Produces dense vectors for a batch of texts.

    Implementations must return vectors of fixed `dimension` for every call
    so the vector store can be created with the right schema up front.
    """

    @property
    def name(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...
