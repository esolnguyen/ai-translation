"""Embedder port — dense vectors for a batch of texts.

Declared in the use-case layer so the Reviewer can compute cosine similarity
against retrieved examples without importing ``knowledge.core``. The bridge
adapter in ``rag.adapters.embedding`` wraps a ``knowledge.core.Embedder``
implementation to satisfy this port.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class Embedder(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Stable identifier for the embedding model."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Fixed vector dimension returned by :meth:`embed`."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed every text in ``texts`` and return one vector per input."""
