"""KnowledgeBaseRetriever — bridges to ``knowledge.core.retrieval.Retriever``.

The use-case layer depends on ``KnowledgeRetriever``; this adapter converts
that port into concrete calls against the knowledge package.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from knowledge.core.retrieval import Retriever as _KBRetriever

from ...use_cases.ports import KnowledgeRetriever


class KnowledgeBaseRetriever(KnowledgeRetriever):
    """Thin pass-through to the knowledge package's ``Retriever``."""

    def __init__(self, inner: _KBRetriever) -> None:
        self._inner = inner

    def search(
        self,
        query: str,
        domain: str | None = None,
        k: int = 5,
    ) -> list[dict[str, Any]]:
        return self._inner.search(query, domain=domain, k=k)

    def glossary(self, term: str, target_lang: str) -> dict[str, Any] | None:
        return self._inner.glossary(term, target_lang)

    def examples(
        self,
        source_text: str,
        source_lang: str,
        target_lang: str,
        domain: str | None = None,
        k: int = 3,
    ) -> list[dict[str, Any]]:
        return self._inner.examples(
            source_text,
            source_lang=source_lang,
            target_lang=target_lang,
            domain=domain,
            k=k,
        )

    def language_card(self, lang: str) -> dict[str, Any] | None:
        return self._inner.language_card(lang)

    def entity(self, name: str) -> dict[str, Any] | None:
        return self._inner.entity(name)


def make_retriever(kb_store: Path | None = None) -> KnowledgeRetriever:
    """Build a retriever using env defaults.

    Factory — call sites never instantiate ``_KBRetriever`` directly.
    """
    if kb_store is not None:
        os.environ.setdefault("KB_STORE_PATH", str(kb_store))
    return KnowledgeBaseRetriever(_KBRetriever.from_env())
