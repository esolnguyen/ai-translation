"""Vault walker tests — folder routing + frontmatter error surfacing."""

from __future__ import annotations

from pathlib import Path

import pytest

from knowledge.core import vault as vault_walker
from knowledge.core.models import NoteKind

FIXTURE_VAULT = Path(__file__).parent / "fixtures" / "vault"


def test_walk_routes_every_kind():
    notes = list(vault_walker.walk(FIXTURE_VAULT))
    by_kind = {n.kind: n for n in notes}
    assert NoteKind.DOMAIN in by_kind
    assert NoteKind.EXAMPLE in by_kind
    assert NoteKind.GLOSSARY in by_kind
    assert NoteKind.LANGUAGE in by_kind
    assert NoteKind.ENTITY in by_kind


def test_walk_includes_needs_review_notes():
    # Walker yields every routable note; status filtering is the indexer's job.
    notes = list(vault_walker.walk(FIXTURE_VAULT))
    ids = {n.id for n in notes}
    assert "legal-contract-terms" in ids
    assert "legal-privacy" in ids


def test_walk_skips_index_files(tmp_path: Path):
    (tmp_path / "domains").mkdir()
    (tmp_path / "domains" / "INDEX.md").write_text("not a note", encoding="utf-8")
    assert list(vault_walker.walk(tmp_path)) == []


def test_missing_frontmatter_raises(tmp_path: Path):
    (tmp_path / "domains").mkdir()
    (tmp_path / "domains" / "bad.md").write_text("no frontmatter here\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing frontmatter"):
        list(vault_walker.walk(tmp_path))


def test_walk_returns_empty_for_missing_vault(tmp_path: Path):
    assert list(vault_walker.walk(tmp_path / "does-not-exist")) == []
