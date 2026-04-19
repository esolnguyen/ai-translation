"""KnowledgeRetriever port — shared retrieval surface over the KB.

Mirrors the shape of ``knowledge.core.retrieval.Retriever`` but is declared
in the use-case layer so use-cases never import the knowledge package
directly. The adapter in ``rag.adapters.retrieval`` bridges the two.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class KnowledgeRetriever(ABC):
    @abstractmethod
    def search(
        self,
        query: str,
        domain: str | None = None,
        k: int = 5,
    ) -> list[dict[str, Any]]:
        """Vector search over DOMAIN notes."""

    @abstractmethod
    def glossary(self, term: str, target_lang: str) -> dict[str, Any] | None:
        """Canonical glossary entry for ``term`` in ``target_lang``, if any."""

    @abstractmethod
    def examples(
        self,
        source_text: str,
        source_lang: str,
        target_lang: str,
        domain: str | None = None,
        k: int = 3,
    ) -> list[dict[str, Any]]:
        """Nearest translation example pairs."""

    @abstractmethod
    def language_card(self, lang: str) -> dict[str, Any] | None:
        """Language-level style card (register, politeness, metric profile)."""

    @abstractmethod
    def entity(self, name: str) -> dict[str, Any] | None:
        """Entity note for ``name``, if any."""

    @abstractmethod
    def idiom(
        self,
        phrase: str,
        source_lang: str,
        target_lang: str,
    ) -> dict[str, Any] | None:
        """Top idiom match above the configured score threshold."""
