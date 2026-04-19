"""Test doubles for Embedder and Store — pure Python, no network."""

from __future__ import annotations

import hashlib
import math
from typing import Any

from knowledge.core.store import QueryHit, VectorRecord


class FakeEmbedder:
    """Bag-of-words-ish embedder. Token-hash buckets → normalized vector.

    Two texts that share tokens get similar vectors; identical texts map to
    identical vectors. Cheap and deterministic — good enough for exercising
    the retrieval surface without shipping real model weights.
    """

    def __init__(self, dimension: int = 64) -> None:
        self._dimension = dimension

    @property
    def name(self) -> str:
        return f"fake-bow-{self._dimension}"

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self._dimension
        for token in text.lower().split():
            digest = hashlib.md5(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self._dimension
            vec[idx] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


def _match_where(meta: dict[str, Any], where: dict[str, Any] | None) -> bool:
    if not where:
        return True
    if "$and" in where:
        return all(_match_where(meta, clause) for clause in where["$and"])
    return all(meta.get(k) == v for k, v in where.items())


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


class InMemoryStore:
    """Dict-backed implementation of the ``Store`` protocol."""

    def __init__(self) -> None:
        self._collections: dict[str, dict[str, VectorRecord]] = {}

    def ensure_collection(self, name: str, dimension: int) -> None:
        self._collections.setdefault(name, {})

    def upsert(self, collection: str, records: list[VectorRecord]) -> None:
        col = self._collections.setdefault(collection, {})
        for r in records:
            col[r.id] = r

    def delete(self, collection: str, ids: list[str]) -> None:
        col = self._collections.setdefault(collection, {})
        for id_ in ids:
            col.pop(id_, None)

    def list_ids(self, collection: str) -> set[str]:
        return set(self._collections.get(collection, {}).keys())

    def query(
        self,
        collection: str,
        vector: list[float],
        k: int,
        where: dict[str, Any] | None = None,
    ) -> list[QueryHit]:
        col = self._collections.get(collection, {})
        scored: list[tuple[float, VectorRecord]] = []
        for rec in col.values():
            if not _match_where(rec.metadata, where):
                continue
            scored.append((_cosine(vector, rec.vector), rec))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            QueryHit(id=r.id, score=score, text=r.text, metadata=dict(r.metadata))
            for score, r in scored[:k]
        ]
