"""BuildGlossary — materialize a per-language glossary from the term cache.

Runs once per target language, right after ``ResolveTerms``. For each term
the resolver surfaced, we prefer (in order):

1. A canonical glossary hit for ``target_lang`` — via the KB retriever.
2. An entity note whose ``## Decision`` says *keep as-is* → source = target.
3. Nothing — the term is left for the translator to handle inline.

Body-parse only. The KB stores glossary translations as Markdown bullets
under a ``## Translations`` heading (``- {lang}: {translation}``); mirroring
that shape keeps the retrieval API agnostic of lang plumbing.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from ..domain import GlossaryEntry
from .ports import KnowledgeRetriever

_TRANSLATIONS_HEADING = re.compile(r"^\s*##\s+Translations\s*$", re.MULTILINE)
_NEXT_HEADING = re.compile(r"^\s*##\s+\S", re.MULTILINE)
_LANG_BULLET = re.compile(r"^\s*-\s*([A-Za-z]{2,3}(?:[-_][A-Za-z0-9]+)?)\s*:\s*(.+?)\s*$")
_DECISION_HEADING = re.compile(r"^\s*##\s+Decision\s*$", re.MULTILINE)
_KEEP_AS_IS = re.compile(
    r"\bas[- ]is\b|do\s+not\s+translate|preserve\s+verbatim",
    re.IGNORECASE,
)


class BuildGlossary:
    """Use-case: turn a resolver cache into ``list[GlossaryEntry]`` for one lang."""

    def __init__(self, *, retriever: KnowledgeRetriever) -> None:
        self._retriever = retriever

    def execute(
        self,
        term_cache: Mapping[str, Mapping[str, Any]],
        target_lang: str,
        *,
        domain: str | None = None,
    ) -> list[GlossaryEntry]:
        entries: list[GlossaryEntry] = []
        seen: set[str] = set()
        for term, cached in term_cache.items():
            entry = self._entry_for(term, cached, target_lang, domain=domain)
            if entry is None:
                continue
            key = entry.source.casefold()
            if key in seen:
                continue
            seen.add(key)
            entries.append(entry)
        return entries

    def _entry_for(
        self,
        term: str,
        cached: Mapping[str, Any],
        target_lang: str,
        *,
        domain: str | None,
    ) -> GlossaryEntry | None:
        hit = self._retriever.glossary(term, target_lang)
        if hit is not None:
            translation = _translation_from_body(hit.get("body", ""), target_lang)
            if translation:
                return GlossaryEntry(
                    source=term,
                    target=translation,
                    kind="glossary",
                    kb_id=hit.get("id"),
                    rationale=_frontmatter_rationale(hit),
                )

        entity = cached.get("entity") if isinstance(cached, Mapping) else None
        if isinstance(entity, Mapping) and _entity_is_keep_as_is(entity):
            return GlossaryEntry(
                source=term,
                target=term,
                kind="entity",
                kb_id=entity.get("id"),
                rationale="keep as-is per entity decision",
            )
        return None


def _translation_from_body(body: str, target_lang: str) -> str | None:
    if not body:
        return None
    heading = _TRANSLATIONS_HEADING.search(body)
    if heading is None:
        return None
    start = heading.end()
    tail = body[start:]
    next_heading = _NEXT_HEADING.search(tail)
    section = tail[: next_heading.start()] if next_heading else tail
    lang_key = target_lang.casefold()
    for line in section.splitlines():
        match = _LANG_BULLET.match(line)
        if match is None:
            continue
        if match.group(1).casefold().replace("_", "-") == lang_key:
            return match.group(2).strip()
    return None


def _entity_is_keep_as_is(entity: Mapping[str, Any]) -> bool:
    body = entity.get("body")
    if not isinstance(body, str):
        return False
    heading = _DECISION_HEADING.search(body)
    if heading is None:
        return False
    tail = body[heading.end():]
    next_heading = _NEXT_HEADING.search(tail)
    section = tail[: next_heading.start()] if next_heading else tail
    return bool(_KEEP_AS_IS.search(section))


def _frontmatter_rationale(hit: Mapping[str, Any]) -> str | None:
    fm = hit.get("frontmatter")
    if not isinstance(fm, Mapping):
        return None
    val = fm.get("rationale") or fm.get("note")
    return str(val) if isinstance(val, str) and val.strip() else None
