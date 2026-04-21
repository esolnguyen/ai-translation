"""KB lookup cache — adapter round-trip, staleness, and ResolveTerms wiring."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rag.adapters.persistence.term_cache import JsonTermLookupCache
from rag.domain import Unit, UnitKind
from rag.use_cases.build_glossary import BuildGlossary
from rag.use_cases.ports import KnowledgeRetriever
from rag.use_cases.resolve_terms import ResolveTerms


class _CountingRetriever(KnowledgeRetriever):
    """Retriever double that records how often each surface is called."""

    def __init__(self) -> None:
        self.search_calls = 0
        self.entity_calls = 0
        self.glossary_calls = 0

    def search(
        self,
        query: str,
        domain: str | None = None,
        k: int = 5,
    ) -> list[dict[str, Any]]:
        self.search_calls += 1
        if query == "Pulse Display Service":
            return [{"id": "note-pds", "text": "PDS docs", "score": 0.9}]
        return []

    def glossary(self, term: str, target_lang: str) -> dict[str, Any] | None:
        self.glossary_calls += 1
        if term == "Holden" and target_lang == "vi":
            return {
                "id": "glossary-holden-vi",
                "body": "## Translations\n- vi: Holden\n- de: Holden\n",
            }
        return None

    def examples(
        self,
        source_text: str,
        source_lang: str,
        target_lang: str,
        domain: str | None = None,
        k: int = 3,
    ) -> list[dict[str, Any]]:
        return []

    def language_card(self, lang: str) -> dict[str, Any] | None:
        return None

    def entity(self, name: str) -> dict[str, Any] | None:
        self.entity_calls += 1
        if name == "Holden":
            return {"id": "entity-holden", "canonical": "Holden"}
        return None


_UNITS = [
    Unit(
        id="u1",
        kind=UnitKind.PARAGRAPH,
        text="Holden dealers run the Pulse Display Service every quarter.",
    ),
]


def test_cache_round_trip(tmp_path: Path) -> None:
    cache_path = tmp_path / "lookup-cache.json"
    cache = JsonTermLookupCache(cache_path, kb_version="v1")
    cache.put(
        "Holden",
        domain="automotive",
        target_lang=None,
        payload={"entity": {"id": "entity-holden"}, "notes": []},
    )
    cache.flush()

    reloaded = JsonTermLookupCache(cache_path, kb_version="v1")
    entry = reloaded.get("Holden", domain="automotive", target_lang=None)
    assert entry == {"entity": {"id": "entity-holden"}, "notes": []}


def test_cache_miss_on_version_change(tmp_path: Path) -> None:
    cache_path = tmp_path / "lookup-cache.json"
    cache = JsonTermLookupCache(cache_path, kb_version="v1")
    cache.put("Holden", domain="automotive", target_lang=None, payload={"entity": None, "notes": []})
    cache.flush()

    bumped = JsonTermLookupCache(cache_path, kb_version="v2")
    assert bumped.get("Holden", domain="automotive", target_lang=None) is None


def test_cache_key_separates_target_lang(tmp_path: Path) -> None:
    cache = JsonTermLookupCache(tmp_path / "lookup-cache.json", kb_version="v1")
    cache.put("strike", domain="legal", target_lang=None, payload={"entity": None, "notes": ["a"]})
    cache.put("strike", domain="legal", target_lang="vi", payload={"entity": None, "notes": ["b"]})
    assert cache.get("strike", domain="legal", target_lang=None) == {"entity": None, "notes": ["a"]}
    assert cache.get("strike", domain="legal", target_lang="vi") == {"entity": None, "notes": ["b"]}


def test_resolve_terms_second_run_hits_cache(tmp_path: Path) -> None:
    cache_path = tmp_path / "lookup-cache.json"
    retriever = _CountingRetriever()
    cache = JsonTermLookupCache(cache_path, kb_version="v1")

    first = ResolveTerms(retriever=retriever, lookup_cache=cache).execute(
        _UNITS, [], domain="automotive"
    )
    assert first.total > 0
    assert first.cache_hits == 0
    assert first.cache_misses == first.total
    calls_after_first = retriever.entity_calls + retriever.search_calls
    assert calls_after_first > 0

    cache_reloaded = JsonTermLookupCache(cache_path, kb_version="v1")
    second = ResolveTerms(retriever=retriever, lookup_cache=cache_reloaded).execute(
        _UNITS, [], domain="automotive"
    )
    assert second.cache_hits == second.total
    assert second.cache_misses == 0
    # Retriever is not consulted again on a fully-hit second pass.
    assert retriever.entity_calls + retriever.search_calls == calls_after_first


def test_resolve_terms_without_cache_still_works() -> None:
    retriever = _CountingRetriever()
    out = ResolveTerms(retriever=retriever, lookup_cache=None).execute(
        _UNITS, [], domain="automotive"
    )
    assert out.total > 0
    assert out.cache_hits == 0
    assert out.cache_misses == out.total


def test_build_glossary_second_run_hits_cache(tmp_path: Path) -> None:
    cache_path = tmp_path / "lookup-cache.json"
    retriever = _CountingRetriever()
    cache = JsonTermLookupCache(cache_path, kb_version="v1")
    term_cache: dict[str, dict[str, Any]] = {
        "Holden": {"entity": {"id": "entity-holden"}, "notes": []},
        "Pulse Display Service": {"entity": None, "notes": []},
    }

    first = BuildGlossary(retriever=retriever, lookup_cache=cache).execute(
        term_cache, target_lang="vi", domain="automotive"
    )
    assert first.cache_hits == 0
    assert first.cache_misses == len(term_cache)
    # Glossary retriever called once per term on the first pass.
    assert retriever.glossary_calls == len(term_cache)
    calls_after_first = retriever.glossary_calls

    cache_reloaded = JsonTermLookupCache(cache_path, kb_version="v1")
    second = BuildGlossary(retriever=retriever, lookup_cache=cache_reloaded).execute(
        term_cache, target_lang="vi", domain="automotive"
    )
    assert second.cache_hits == len(term_cache)
    assert second.cache_misses == 0
    # Miss-sentinels serve from the cache too — no new retriever calls.
    assert retriever.glossary_calls == calls_after_first
    # Second-run entries mirror the first run.
    assert [e.source for e in second.entries] == [e.source for e in first.entries]
