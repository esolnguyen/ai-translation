"""Vault walker — yields parsed Notes routed to their NoteKind by folder.

The vault layout is fixed by DESIGN-knowledge.md: a known set of top-level
folders (``domains/``, ``examples/``, ``glossary/terms/``, ``languages/``,
``entities/``). The walker uses the folder a note lives in to
decide its ``NoteKind`` — file-level inspection is deliberately avoided so
the routing stays trivial to reason about.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from .models import Note, NoteKind, load_note

# Order matters: longer prefixes first so "glossary/terms" wins over "glossary".
_FOLDER_KINDS: tuple[tuple[tuple[str, ...], NoteKind], ...] = (
    (("glossary", "terms"), NoteKind.GLOSSARY),
    (("domains",), NoteKind.DOMAIN),
    (("examples",), NoteKind.EXAMPLE),
    (("languages",), NoteKind.LANGUAGE),
    (("entities",), NoteKind.ENTITY),
)

_SKIP_FILENAMES = frozenset({"INDEX.md", "README.md"})


def kind_for_path(relative_parts: tuple[str, ...]) -> NoteKind | None:
    """Return the NoteKind for a path relative to the vault root, or None.

    ``relative_parts`` is the split of ``path.relative_to(vault_path)``; a
    note at ``vault/domains/legal/contract.md`` has parts
    ``("domains", "legal", "contract.md")``.
    """
    for prefix, kind in _FOLDER_KINDS:
        if relative_parts[: len(prefix)] == prefix:
            return kind
    return None


def walk(vault_path: Path) -> Iterator[Note]:
    """Yield every routable note under ``vault_path``.

    Notes whose folder doesn't map to a known NoteKind (e.g. stray files at
    the vault root) are skipped silently — INDEX.md/README.md files are
    always skipped so MOCs don't pollute the index.
    """
    if not vault_path.exists():
        return

    for md_path in sorted(vault_path.rglob("*.md")):
        if md_path.name in _SKIP_FILENAMES:
            continue
        if any(part.startswith(".") for part in md_path.parts):
            continue  # skip .obsidian/, .trash/, etc.
        rel_parts = md_path.relative_to(vault_path).parts
        kind = kind_for_path(rel_parts)
        if kind is None:
            continue
        yield load_note(md_path, kind)
