"""Vector store protocol + shared record types.

The Store protocol is deliberately narrow: upsert, delete, query. Collections
(notes / examples) are plain string names; the indexer decides which
collection a chunk lands in.

Backends (Chroma, LanceDB, Qdrant) live under knowledge.core.stores.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class VectorRecord:
    """One embedded row, ready to upsert."""

    id: str
    vector: list[float]
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class QueryHit:
    """One result from a vector query."""

    id: str
    score: float
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Store(Protocol):
    """Minimum surface the indexer and retrieval API need."""

    def ensure_collection(self, name: str, dimension: int) -> None: ...

    def upsert(self, collection: str, records: list[VectorRecord]) -> None: ...

    def delete(self, collection: str, ids: list[str]) -> None: ...

    def list_ids(self, collection: str) -> set[str]: ...

    def query(
        self,
        collection: str,
        vector: list[float],
        k: int,
        where: dict[str, Any] | None = None,
    ) -> list[QueryHit]: ...
