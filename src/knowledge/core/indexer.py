"""Vault → vector DB + structured stores sync.

Only ``status: approved`` notes are indexed. Chunks are upserted by stable
id; any id present in the store but missing from the new run is deleted
(differential sync). Structured stores rewrite their JSON file on each run.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from . import vault as vault_walker
from .chunker import chunk
from .embedder import Embedder
from .entities import EntityStore
from .glossary import GlossaryStore
from .languages import LanguageStore
from .models import Chunk, Note, NoteKind, Status
from .store import Store, VectorRecord
from .sync import SyncDelta, SyncReport

_VECTOR_COLLECTIONS: dict[NoteKind, str] = {
    NoteKind.DOMAIN: "notes",
    NoteKind.EXAMPLE: "examples",
    NoteKind.IDIOM: "idioms",
}


def _chunk_metadata(note: Note, chunk_: Chunk) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "note_id": note.id,
        "kind": note.kind.value,
        "status": note.status.value,
        "source_path": str(note.path),
        "heading_path": "/".join(chunk_.heading_path),
    }
    if note.domain:
        meta["domain"] = note.domain
    if note.tags:
        meta["tags"] = note.tags
    # Example + idiom notes carry language pair + extra section content.
    for key in ("source_lang", "target_lang"):
        value = note.frontmatter.get(key)
        if value is not None:
            meta[key] = value
    for key in ("target", "notes"):
        value = chunk_.metadata.get(key)
        if value:
            meta[key] = value
    return meta


class Indexer:
    """Orchestrates one full sync pass across every collection."""

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

    def sync(self, vault_path: Path) -> SyncReport:
        notes_by_kind: dict[NoteKind, list[Note]] = defaultdict(list)
        for note in vault_walker.walk(vault_path):
            if note.status is Status.APPROVED:
                notes_by_kind[note.kind].append(note)

        report = SyncReport()

        for kind, collection in _VECTOR_COLLECTIONS.items():
            delta = self._sync_vector_collection(
                collection=collection,
                notes=notes_by_kind.get(kind, []),
            )
            report.record(collection, delta)

        report.record("glossary", self._glossary.sync(notes_by_kind.get(NoteKind.GLOSSARY, [])))
        report.record("entities", self._entities.sync(notes_by_kind.get(NoteKind.ENTITY, [])))
        report.record("languages", self._languages.sync(notes_by_kind.get(NoteKind.LANGUAGE, [])))

        return report

    def _sync_vector_collection(self, collection: str, notes: list[Note]) -> SyncDelta:
        self._store.ensure_collection(collection, self._embedder.dimension)
        previous_ids = self._store.list_ids(collection)

        records: list[VectorRecord] = []
        chunks_by_note: list[tuple[Note, Chunk]] = []
        for note in notes:
            for chunk_ in chunk(note):
                chunks_by_note.append((note, chunk_))

        if chunks_by_note:
            texts = [c.text for _, c in chunks_by_note]
            vectors = self._embedder.embed(texts)
            for (note, chunk_), vector in zip(chunks_by_note, vectors, strict=True):
                records.append(
                    VectorRecord(
                        id=chunk_.id,
                        vector=vector,
                        text=chunk_.text,
                        metadata=_chunk_metadata(note, chunk_),
                    )
                )

        self._store.upsert(collection, records)

        current_ids = {r.id for r in records}
        stale = list(previous_ids - current_ids)
        if stale:
            self._store.delete(collection, stale)

        return SyncDelta(
            added=len(current_ids - previous_ids),
            updated=len(current_ids & previous_ids),
            removed=len(stale),
        )
