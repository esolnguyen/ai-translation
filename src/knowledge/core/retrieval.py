"""Retrieval API — the shared surface both translation paths consume.

The RAG path imports ``Retriever`` directly; the Agent path shells out to
the ``kb`` CLI, which wraps these same methods. Keep return types as plain
dicts/lists so callers never depend on backend types.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .embedder import Embedder
from .embedders import make_embedder
from .entities import EntityStore
from .glossary import GlossaryStore
from .languages import LanguageStore
from .store import QueryHit, Store
from .stores import ChromaStore

_IDIOM_SCORE_THRESHOLD = 0.5


def _hit_to_dict(hit: QueryHit) -> dict[str, Any]:
    return {
        "id": hit.id,
        "score": hit.score,
        "text": hit.text,
        "metadata": hit.metadata,
    }


class Retriever:
    """Query surface backed by a vector store + three structured stores."""

    def __init__(
        self,
        embedder: Embedder,
        store: Store,
        glossary_store: GlossaryStore,
        entity_store: EntityStore,
        language_store: LanguageStore,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._glossary = glossary_store
        self._entities = entity_store
        self._languages = language_store

    # -----------------------------------------------------------------
    # Factory
    # -----------------------------------------------------------------

    @classmethod
    def from_env(cls) -> Retriever:
        """Build a Retriever from ``KB_VAULT`` / ``KB_STORE_PATH`` / ``KB_EMBEDDER``.

        Defaults: vault at ``./vault``, stores at ``./.kb``, local bge-m3.
        """
        store_path = Path(os.environ.get("KB_STORE_PATH", ".kb"))
        embedder = make_embedder()
        store = ChromaStore(store_path / "chroma")
        return cls(
            embedder=embedder,
            store=store,
            glossary_store=GlossaryStore(store_path / "glossary.json"),
            entity_store=EntityStore(store_path / "entities.json"),
            language_store=LanguageStore(store_path / "languages.json"),
        )

    # -----------------------------------------------------------------
    # Retrieval surfaces
    # -----------------------------------------------------------------

    def search(
        self,
        query: str,
        domain: str | None = None,
        k: int = 5,
    ) -> list[dict[str, Any]]:
        vector = self._embedder.embed([query])[0]
        where = {"domain": domain} if domain else None
        hits = self._store.query("notes", vector, k=k, where=where)
        return [_hit_to_dict(h) for h in hits]

    def glossary(self, term: str, target_lang: str) -> dict[str, Any] | None:
        entry = self._glossary.get(term)
        if entry is None:
            return None
        return {**entry, "target_lang": target_lang}

    def examples(
        self,
        source_text: str,
        source_lang: str,
        target_lang: str,
        domain: str | None = None,
        k: int = 3,
    ) -> list[dict[str, Any]]:
        vector = self._embedder.embed([source_text])[0]
        filters = [
            {"source_lang": source_lang},
            {"target_lang": target_lang},
        ]
        if domain:
            filters.append({"domain": domain})
        where: dict[str, Any] = (
            filters[0] if len(filters) == 1 else {"$and": filters}
        )
        hits = self._store.query("examples", vector, k=k, where=where)
        return [_hit_to_dict(h) for h in hits]

    def language_card(self, lang: str) -> dict[str, Any] | None:
        return self._languages.get(lang)

    def entity(self, name: str) -> dict[str, Any] | None:
        return self._entities.get(name)

    def idiom(
        self,
        phrase: str,
        source_lang: str,
        target_lang: str,
    ) -> dict[str, Any] | None:
        vector = self._embedder.embed([phrase])[0]
        where = {"$and": [{"source_lang": source_lang}, {"target_lang": target_lang}]}
        hits = self._store.query("idioms", vector, k=1, where=where)
        if not hits or hits[0].score < _IDIOM_SCORE_THRESHOLD:
            return None
        return _hit_to_dict(hits[0])
