"""BuildGlossary — per-language glossary materialization from the term cache."""

from __future__ import annotations

from typing import Any

from rag.use_cases.build_glossary import BuildGlossary
from rag.use_cases.ports import KnowledgeRetriever


class _ScriptedRetriever(KnowledgeRetriever):
    """Retriever double driven by two dicts: glossary hits + entity decisions.

    ``glossary_hits[(term, lang)]`` → the dict the retriever returns for
    ``glossary(term, lang)``. ``entities[name]`` → the dict returned for
    ``entity(name)``.
    """

    def __init__(
        self,
        *,
        glossary_hits: dict[tuple[str, str], dict[str, Any]] | None = None,
        entities: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._glossary = glossary_hits or {}
        self._entities = entities or {}

    def search(
        self, query: str, domain: str | None = None, k: int = 5
    ) -> list[dict[str, Any]]:
        return []

    def glossary(self, term: str, target_lang: str) -> dict[str, Any] | None:
        return self._glossary.get((term, target_lang))

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
        return self._entities.get(name)

    def idiom(
        self,
        phrase: str,
        source_lang: str,
        target_lang: str,
    ) -> dict[str, Any] | None:
        return None


def test_glossary_hit_produces_entry_with_body_parse() -> None:
    retriever = _ScriptedRetriever(
        glossary_hits={
            ("brake disc", "vi"): {
                "id": "glossary-brake-disc",
                "body": "Disc.\n\n## Translations\n- vi: đĩa phanh\n- ja: ブレーキディスク\n",
                "frontmatter": {"rationale": "canonical"},
            }
        }
    )
    term_cache: dict[str, dict[str, Any]] = {
        "brake disc": {"entity": None, "notes": []},
    }

    out = BuildGlossary(retriever=retriever).execute(
        term_cache, target_lang="vi", domain="automotive"
    )

    assert len(out.entries) == 1
    entry = out.entries[0]
    assert entry.source == "brake disc"
    assert entry.target == "đĩa phanh"
    assert entry.kind == "glossary"
    assert entry.kb_id == "glossary-brake-disc"
    assert entry.rationale == "canonical"


def test_entity_keep_as_is_fallback() -> None:
    retriever = _ScriptedRetriever(
        entities={
            "Holden": {
                "id": "entity-holden",
                "body": "Australian car brand.\n\n## Decision\nKeep as-is — brand name.\n",
            }
        }
    )
    term_cache: dict[str, dict[str, Any]] = {
        "Holden": {
            "entity": {
                "id": "entity-holden",
                "body": "Australian car brand.\n\n## Decision\nKeep as-is — brand name.\n",
            },
            "notes": [],
        }
    }

    out = BuildGlossary(retriever=retriever).execute(
        term_cache, target_lang="vi"
    )

    assert len(out.entries) == 1
    entry = out.entries[0]
    assert entry.source == "Holden"
    assert entry.target == "Holden"
    assert entry.kind == "entity"
    assert entry.kb_id == "entity-holden"


def test_no_hit_no_entity_skips_term() -> None:
    retriever = _ScriptedRetriever()
    term_cache: dict[str, dict[str, Any]] = {
        "gizmo": {"entity": None, "notes": []},
    }

    out = BuildGlossary(retriever=retriever).execute(
        term_cache, target_lang="vi"
    )

    assert out.entries == []


def test_dedupe_by_source_casefold() -> None:
    body = "x\n\n## Translations\n- vi: máy\n"
    retriever = _ScriptedRetriever(
        glossary_hits={
            ("Widget", "vi"): {"id": "g1", "body": body},
            ("widget", "vi"): {"id": "g2", "body": body},
        }
    )
    term_cache: dict[str, dict[str, Any]] = {
        "Widget": {"entity": None, "notes": []},
        "widget": {"entity": None, "notes": []},
    }

    out = BuildGlossary(retriever=retriever).execute(
        term_cache, target_lang="vi"
    )

    assert len(out.entries) == 1
    assert out.entries[0].source == "Widget"


def test_target_lang_selects_matching_bullet() -> None:
    body = "## Translations\n- vi: má phanh\n- ja: ブレーキパッド\n"
    retriever = _ScriptedRetriever(
        glossary_hits={
            ("brake pad", "vi"): {"id": "g-bp", "body": body},
            ("brake pad", "ja"): {"id": "g-bp", "body": body},
        }
    )
    term_cache: dict[str, dict[str, Any]] = {
        "brake pad": {"entity": None, "notes": []},
    }

    out_vi = BuildGlossary(retriever=retriever).execute(
        term_cache, target_lang="vi"
    )
    out_ja = BuildGlossary(retriever=retriever).execute(
        term_cache, target_lang="ja"
    )

    assert out_vi.entries[0].target == "má phanh"
    assert out_ja.entries[0].target == "ブレーキパッド"


def test_body_without_matching_lang_falls_through() -> None:
    retriever = _ScriptedRetriever(
        glossary_hits={
            ("brake disc", "de"): {
                "id": "g-bd",
                "body": "## Translations\n- vi: đĩa phanh\n",
            }
        }
    )
    term_cache: dict[str, dict[str, Any]] = {
        "brake disc": {"entity": None, "notes": []},
    }

    out = BuildGlossary(retriever=retriever).execute(
        term_cache, target_lang="de"
    )

    assert out.entries == []


def test_entity_decision_not_keep_as_is_is_ignored() -> None:
    retriever = _ScriptedRetriever()
    term_cache: dict[str, dict[str, Any]] = {
        "Bosch": {
            "entity": {
                "id": "entity-bosch",
                "body": "## Decision\nTransliterate to local script where applicable.\n",
            },
            "notes": [],
        }
    }

    out = BuildGlossary(retriever=retriever).execute(
        term_cache, target_lang="vi"
    )

    assert out.entries == []
