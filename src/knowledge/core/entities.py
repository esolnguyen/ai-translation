"""Structured entity store — JSON-backed, keyed by normalized entity name."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .models import Note
from .sync import SyncDelta


def normalize_name(name: str) -> str:
    return name.strip().lower()


def _note_key(note: Note) -> str:
    raw = note.frontmatter.get("name") or note.id
    return normalize_name(str(raw))


def _note_payload(note: Note) -> dict[str, Any]:
    return {
        "id": note.id,
        "name": note.frontmatter.get("name", note.id),
        "frontmatter": dict(note.frontmatter),
        "body": note.body,
        "source_path": str(note.path),
    }


class EntityStore:
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
        next_data = {_note_key(n): _note_payload(n) for n in notes}
        current = set(next_data.keys())

        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(next_data, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        self._data = next_data
        return SyncDelta(
            added=len(current - previous),
            updated=len(current & previous),
            removed=len(previous - current),
        )

    def get(self, name: str) -> dict[str, Any] | None:
        return self._load().get(normalize_name(name))
