"""Indexer tests — approved filtering, collection routing, differential sync."""

from __future__ import annotations

import shutil
from pathlib import Path

from knowledge.core.entities import EntityStore
from knowledge.core.glossary import GlossaryStore
from knowledge.core.indexer import Indexer
from knowledge.core.languages import LanguageStore

from .fakes import FakeEmbedder, InMemoryStore

FIXTURE_VAULT = Path(__file__).parent / "fixtures" / "vault"


def _build(tmp_path: Path) -> tuple[Indexer, InMemoryStore]:
    store = InMemoryStore()
    indexer = Indexer(
        embedder=FakeEmbedder(),
        store=store,
        glossary_store=GlossaryStore(tmp_path / "glossary.json"),
        entity_store=EntityStore(tmp_path / "entities.json"),
        language_store=LanguageStore(tmp_path / "languages.json"),
    )
    return indexer, store


def test_sync_adds_all_approved_notes(tmp_path: Path):
    indexer, store = _build(tmp_path)
    report = indexer.sync(FIXTURE_VAULT)

    # Every vector collection received at least one chunk.
    assert report.deltas["notes"].added >= 1
    assert report.deltas["examples"].added == 1
    assert report.deltas["glossary"].added == 1
    assert report.deltas["entities"].added == 1
    assert report.deltas["languages"].added == 1

    # Needs-review domain note is not indexed.
    note_ids = {meta_note_id(store, "notes", i) for i in store.list_ids("notes")}
    assert "legal-privacy" not in note_ids
    assert "legal-contract-terms" in note_ids


def test_resync_marks_existing_as_updated(tmp_path: Path):
    indexer, _ = _build(tmp_path)
    indexer.sync(FIXTURE_VAULT)
    report = indexer.sync(FIXTURE_VAULT)
    assert report.deltas["notes"].added == 0
    assert report.deltas["notes"].updated >= 1
    assert report.deltas["notes"].removed == 0


def test_removed_note_is_purged_on_next_sync(tmp_path: Path):
    vault_copy = tmp_path / "vault"
    shutil.copytree(FIXTURE_VAULT, vault_copy)

    indexer, store = _build(tmp_path)
    indexer.sync(vault_copy)
    before = store.list_ids("examples")
    assert len(before) == 1

    (vault_copy / "examples" / "en-ja" / "legal" / "contract-001.md").unlink()
    report = indexer.sync(vault_copy)
    assert report.deltas["examples"].removed == 1
    assert store.list_ids("examples") == set()


def test_glossary_store_is_rewritten_on_removal(tmp_path: Path):
    vault_copy = tmp_path / "vault"
    shutil.copytree(FIXTURE_VAULT, vault_copy)

    indexer, _ = _build(tmp_path)
    indexer.sync(vault_copy)
    glossary_path = tmp_path / "glossary.json"
    assert "settlement" in glossary_path.read_text(encoding="utf-8")

    (vault_copy / "glossary" / "terms" / "settlement.md").unlink()
    report = indexer.sync(vault_copy)
    assert report.deltas["glossary"].removed == 1
    assert "settlement" not in glossary_path.read_text(encoding="utf-8")


def meta_note_id(store: InMemoryStore, collection: str, chunk_id: str) -> str:
    return store._collections[collection][chunk_id].metadata["note_id"]  # noqa: SLF001
