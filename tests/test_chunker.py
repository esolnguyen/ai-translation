"""Chunker tests — heading splitting + EXAMPLE/IDIOM source extraction."""

from __future__ import annotations

from pathlib import Path

from knowledge.core.chunker import chunk
from knowledge.core.models import Note, NoteKind, Status


def _note(body: str, kind: NoteKind = NoteKind.DOMAIN, note_id: str = "n1") -> Note:
    return Note(
        id=note_id,
        kind=kind,
        path=Path(f"/tmp/{note_id}.md"),
        status=Status.APPROVED,
        body=body,
        frontmatter={"id": note_id, "status": "approved"},
    )


def test_domain_splits_on_h2_and_h3():
    body = (
        "Opening preamble.\n"
        "\n"
        "## Termination\n"
        "\n"
        "Lead paragraph.\n"
        "\n"
        "### For-cause\n"
        "\n"
        "Breach-triggered.\n"
        "\n"
        "### For-convenience\n"
        "\n"
        "Notice-triggered.\n"
        "\n"
        "## Jurisdiction\n"
        "\n"
        "Choice of law.\n"
    )
    chunks = chunk(_note(body))
    paths = [c.heading_path for c in chunks]
    assert () in paths  # preamble
    assert ("Termination",) in paths  # H2 preamble paragraph
    assert ("Termination", "For-cause") in paths
    assert ("Termination", "For-convenience") in paths
    assert ("Jurisdiction",) in paths


def test_chunk_ids_are_stable_and_unique():
    body = "## A\n\ntext\n\n## B\n\nother\n"
    chunks = chunk(_note(body, note_id="nX"))
    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids))
    assert all(i.startswith("nX#") for i in ids)


def test_example_emits_single_source_chunk_with_metadata():
    body = (
        "## Source\n"
        "The parties agree...\n"
        "\n"
        "## Target\n"
        "両当事者は...\n"
        "\n"
        "## Notes\n"
        "Formal legal register.\n"
    )
    chunks = chunk(_note(body, kind=NoteKind.EXAMPLE, note_id="ex1"))
    assert len(chunks) == 1
    c = chunks[0]
    assert c.heading_path == ("Source",)
    assert "parties agree" in c.text
    assert "両当事者" in c.metadata["target"]
    assert "Formal" in c.metadata["notes"]


def test_glossary_and_language_and_entity_yield_no_chunks():
    body = "## Translations\n\n- ja: 和解\n"
    for kind in (NoteKind.GLOSSARY, NoteKind.LANGUAGE, NoteKind.ENTITY):
        assert chunk(_note(body, kind=kind)) == []


def test_example_without_source_section_is_skipped():
    body = "## Target\nonly target\n"
    assert chunk(_note(body, kind=NoteKind.EXAMPLE)) == []


def test_code_fence_headings_do_not_split():
    body = (
        "## Real\n"
        "\n"
        "body\n"
        "\n"
        "```\n"
        "## Not a heading\n"
        "```\n"
    )
    chunks = chunk(_note(body))
    paths = [c.heading_path for c in chunks]
    assert ("Real",) in paths
    assert ("Not a heading",) not in paths
