"""Core data types flowing through the knowledge base.

These are plain dataclasses so the rest of the library (and its callers) can
operate on them without pulling in any backend-specific types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import frontmatter


class Status(str, Enum):
    NEEDS_REVIEW = "needs-review"
    APPROVED = "approved"


class NoteKind(str, Enum):
    """Routes how a note is indexed. Derived from the note's folder under vault/."""

    DOMAIN = "domain"
    EXAMPLE = "example"
    GLOSSARY = "glossary"
    LANGUAGE = "language"
    ENTITY = "entity"


@dataclass(frozen=True, slots=True)
class Note:
    """A parsed vault note: frontmatter + body."""

    id: str
    kind: NoteKind
    path: Path
    status: Status
    body: str
    frontmatter: dict[str, Any] = field(default_factory=dict)

    @property
    def domain(self) -> str | None:
        val = self.frontmatter.get("domain")
        return str(val) if val is not None else None

    @property
    def tags(self) -> list[str]:
        raw = self.frontmatter.get("tags", [])
        if isinstance(raw, list):
            return [str(t) for t in raw]
        return []


@dataclass(frozen=True, slots=True)
class Chunk:
    """A heading-level slice of a note, ready for embedding."""

    id: str                    # stable: note_id + heading path
    note_id: str
    kind: NoteKind
    heading_path: tuple[str, ...]   # () for pre-H2 preamble
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------

_REQUIRED_FIELDS = ("id", "status")


def load_note(path: Path, kind: NoteKind) -> Note:
    """Load a vault note from disk.

    Raises ValueError if required frontmatter fields are missing — the vault
    is the source of truth, so we surface malformed notes loudly rather than
    silently skipping them.
    """
    post = frontmatter.load(path)
    meta = dict(post.metadata)

    missing = [f for f in _REQUIRED_FIELDS if f not in meta]
    if missing:
        raise ValueError(f"{path}: missing frontmatter fields: {missing}")

    try:
        status = Status(meta["status"])
    except ValueError as exc:
        raise ValueError(f"{path}: invalid status {meta['status']!r}") from exc

    return Note(
        id=str(meta["id"]),
        kind=kind,
        path=path,
        status=status,
        body=post.content,
        frontmatter=meta,
    )
