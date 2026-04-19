"""Heading-level chunking.

Splits note bodies at H2 / H3 boundaries (never fixed token windows, per
DESIGN-knowledge.md). Uses ``markdown-it-py`` so ATX headings inside fenced
code blocks don't get misread as section headers.

Routing by NoteKind:
    DOMAIN        -> one Chunk per H2/H3 section (plus any preamble)
    EXAMPLE/IDIOM -> one Chunk embedded on the ``## Source`` section;
                     target + notes sections ride along in metadata
    everything else -> returns [] (those kinds are stored in structured
                       stores rather than vectorized)
"""

from __future__ import annotations

from markdown_it import MarkdownIt

from .models import Chunk, Note, NoteKind

_md = MarkdownIt("commonmark")


def _split_sections(body: str) -> list[tuple[tuple[str, ...], str]]:
    """Return (heading_path, text) for the preamble and each H2/H3 section.

    The preamble (text before the first heading) gets an empty path. H3s
    inherit the most recent H2 as their parent; an H3 with no preceding H2
    is treated as top-level.
    """
    tokens = _md.parse(body)
    lines = body.splitlines()

    headings: list[tuple[int, str, int]] = []  # (level, text, line_start)
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open" and tok.tag in ("h2", "h3") and tok.map is not None:
            heading_text = tokens[i + 1].content.strip()
            headings.append((int(tok.tag[1]), heading_text, tok.map[0]))

    sections: list[tuple[tuple[str, ...], str]] = []

    preamble_end = headings[0][2] if headings else len(lines)
    preamble = "\n".join(lines[:preamble_end]).strip()
    if preamble:
        sections.append(((), preamble))

    current_h2: str | None = None
    for i, (level, text, line_start) in enumerate(headings):
        content_start = line_start + 1
        content_end = headings[i + 1][2] if i + 1 < len(headings) else len(lines)
        content = "\n".join(lines[content_start:content_end]).strip()

        if level == 2:
            current_h2 = text
            path: tuple[str, ...] = (text,)
        else:  # H3
            path = (current_h2, text) if current_h2 else (text,)

        if content:
            sections.append((path, content))

    return sections


def _chunk_id(note_id: str, path: tuple[str, ...]) -> str:
    suffix = "/".join(path) if path else "_preamble"
    return f"{note_id}#{suffix}"


def chunk(note: Note) -> list[Chunk]:
    """Split a note body into embeddable chunks. See module docstring for rules."""
    if note.kind in (NoteKind.GLOSSARY, NoteKind.LANGUAGE, NoteKind.ENTITY):
        return []

    sections = _split_sections(note.body)
    section_map = dict(sections)

    if note.kind in (NoteKind.EXAMPLE, NoteKind.IDIOM):
        source_text = section_map.get(("Source",))
        if not source_text:
            # Design mandates embedding on the source field; a missing
            # Source section means the note is malformed for indexing.
            return []
        metadata = {
            "target": section_map.get(("Target",), ""),
            "notes": section_map.get(("Notes",), ""),
        }
        return [
            Chunk(
                id=_chunk_id(note.id, ("Source",)),
                note_id=note.id,
                kind=note.kind,
                heading_path=("Source",),
                text=source_text,
                metadata=metadata,
            )
        ]

    # DOMAIN: emit every section.
    return [
        Chunk(
            id=_chunk_id(note.id, path),
            note_id=note.id,
            kind=note.kind,
            heading_path=path,
            text=text,
        )
        for path, text in sections
    ]
