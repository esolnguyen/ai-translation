"""Retrieval API tests — every surface returns expected results on a seeded vault."""

from __future__ import annotations

from pathlib import Path

from knowledge.core.entities import EntityStore
from knowledge.core.glossary import GlossaryStore
from knowledge.core.indexer import Indexer
from knowledge.core.languages import LanguageStore
from knowledge.core.retrieval import Retriever

from .fakes import FakeEmbedder, InMemoryStore

FIXTURE_VAULT = Path(__file__).parent / "fixtures" / "vault"


def _seeded(tmp_path: Path) -> Retriever:
    embedder = FakeEmbedder()
    store = InMemoryStore()
    glossary_store = GlossaryStore(tmp_path / "glossary.json")
    entity_store = EntityStore(tmp_path / "entities.json")
    language_store = LanguageStore(tmp_path / "languages.json")
    Indexer(
        embedder=embedder,
        store=store,
        glossary_store=glossary_store,
        entity_store=entity_store,
        language_store=language_store,
    ).sync(FIXTURE_VAULT)
    return Retriever(
        embedder=embedder,
        store=store,
        glossary_store=glossary_store,
        entity_store=entity_store,
        language_store=language_store,
    )


def test_search_returns_legal_note(tmp_path: Path):
    retriever = _seeded(tmp_path)
    hits = retriever.search("contract termination clauses", domain="legal", k=3)
    assert hits
    top = hits[0]
    assert top["metadata"]["note_id"] == "legal-contract-terms"
    assert top["metadata"]["domain"] == "legal"


def test_search_domain_filter_excludes_mismatch(tmp_path: Path):
    retriever = _seeded(tmp_path)
    assert retriever.search("termination", domain="medical", k=3) == []


def test_glossary_lookup(tmp_path: Path):
    retriever = _seeded(tmp_path)
    entry = retriever.glossary("settlement", target_lang="ja")
    assert entry is not None
    assert entry["id"] == "glossary-settlement"
    assert entry["target_lang"] == "ja"
    assert retriever.glossary("does-not-exist", target_lang="ja") is None


def test_language_card(tmp_path: Path):
    retriever = _seeded(tmp_path)
    card = retriever.language_card("ja")
    assert card is not None
    assert card["lang"] == "ja"
    assert "keigo" in card["body"] or "敬語" in card["body"]


def test_entity_lookup(tmp_path: Path):
    retriever = _seeded(tmp_path)
    entry = retriever.entity("Apple")
    assert entry is not None
    assert entry["name"] == "Apple"


def test_examples_returns_matching_pair(tmp_path: Path):
    retriever = _seeded(tmp_path)
    hits = retriever.examples(
        "either party may terminate this agreement",
        source_lang="en",
        target_lang="ja",
        domain="legal",
        k=3,
    )
    assert hits
    assert hits[0]["metadata"]["note_id"] == "ex-legal-contract-001"
    assert hits[0]["metadata"]["source_lang"] == "en"


def test_idiom_lookup_returns_match(tmp_path: Path):
    retriever = _seeded(tmp_path)
    entry = retriever.idiom("kick the bucket", source_lang="en", target_lang="vi")
    assert entry is not None
    assert entry["metadata"]["note_id"] == "idiom-en-vi-kick-the-bucket"


def test_idiom_below_threshold_returns_none(tmp_path: Path):
    retriever = _seeded(tmp_path)
    # Entirely unrelated phrase should score below the similarity threshold.
    assert (
        retriever.idiom("unrelated random gibberish xyz", source_lang="en", target_lang="vi")
        is None
    )
