"""Structured glossary store — JSON-backed, keyed by normalized term.

Glossary notes live under ``vault/glossary/terms/``. The store rewrites its
JSON file on every sync (no incremental merges) so stale entries can never
leak past a removal.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .models import Note
from .sync import SyncDelta


def normalize_term(term: str) -> str:
    """Case-insensitive, whitespace-trimmed key for term lookups."""
    return term.strip().lower()


def _note_term(note: Note) -> str:
    """Lookup key for a glossary note — prefer frontmatter `term`, fall back to id."""
    raw = note.frontmatter.get("term") or note.id
    return normalize_term(str(raw))


def _note_payload(note: Note) -> dict[str, Any]:
    return {
        "id": note.id,
        "term": note.frontmatter.get("term", note.id),
        "frontmatter": dict(note.frontmatter),
        "body": note.body,
        "source_path": str(note.path),
    }


class GlossaryStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._data: dict[str, dict[str, Any]] | None = None

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._data is not None:
            return self._data
        if self._path.exists():
            self._data = json.loads(self._path.read_text(encoding="utf-8"))
        else:
            self._data = {}
        return self._data

    def sync(self, notes: Iterable[Note]) -> SyncDelta:
        previous = set(self._load().keys())
        next_data: dict[str, dict[str, Any]] = {}
        for note in notes:
            next_data[_note_term(note)] = _note_payload(note)
        current = set(next_data.keys())

        added = len(current - previous)
        removed = len(previous - current)
        updated = len(current & previous)

        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(next_data, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        self._data = next_data
        return SyncDelta(added=added, updated=updated, removed=removed)

    def get(self, term: str) -> dict[str, Any] | None:
        return self._load().get(normalize_term(term))
