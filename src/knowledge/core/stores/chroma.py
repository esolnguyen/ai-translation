"""Chroma-backed implementation of the ``Store`` protocol.

Each collection is created with cosine distance; query results convert
distance to a similarity score via ``score = 1 - distance``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings

from ..store import QueryHit, VectorRecord


def _clean_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """Drop None values and stringify lists — Chroma only accepts scalars."""
    out: dict[str, Any] = {}
    for k, v in meta.items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            out[k] = v
        elif isinstance(v, (list, tuple)):
            out[k] = ",".join(str(x) for x in v)
        else:
            out[k] = str(v)
    return out


class ChromaStore:
    """Persistent Chroma client wrapped in the ``Store`` protocol surface."""

    def __init__(self, persist_dir: Path) -> None:
        persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(persist_dir),
            settings=Settings(anonymized_telemetry=False, allow_reset=True),
        )

    def ensure_collection(self, name: str, dimension: int) -> None:
        # Chroma infers dimension from the first upsert; we still record the
        # expected value in metadata so drift is spottable.
        self._client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine", "embedding_dim": dimension},
        )

    def upsert(self, collection: str, records: list[VectorRecord]) -> None:
        if not records:
            return
        col = self._client.get_or_create_collection(
            name=collection, metadata={"hnsw:space": "cosine"}
        )
        col.upsert(
            ids=[r.id for r in records],
            embeddings=[r.vector for r in records],
            documents=[r.text for r in records],
            metadatas=[_clean_metadata(r.metadata) for r in records],
        )

    def delete(self, collection: str, ids: list[str]) -> None:
        if not ids:
            return
        col = self._client.get_or_create_collection(name=collection)
        col.delete(ids=ids)

    def list_ids(self, collection: str) -> set[str]:
        col = self._client.get_or_create_collection(name=collection)
        result = col.get(include=[])
        return set(result.get("ids", []))

    def query(
        self,
        collection: str,
        vector: list[float],
        k: int,
        where: dict[str, Any] | None = None,
    ) -> list[QueryHit]:
        col = self._client.get_or_create_collection(name=collection)
        result = col.query(
            query_embeddings=[vector],
            n_results=k,
            where=where or None,
        )
        ids = (result.get("ids") or [[]])[0]
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        dists = (result.get("distances") or [[]])[0]
        hits: list[QueryHit] = []
        for i, hit_id in enumerate(ids):
            distance = dists[i] if i < len(dists) else 0.0
            hits.append(
                QueryHit(
                    id=hit_id,
                    score=1.0 - float(distance),
                    text=docs[i] if i < len(docs) else "",
                    metadata=dict(metas[i]) if i < len(metas) and metas[i] else {},
                )
            )
        return hits
