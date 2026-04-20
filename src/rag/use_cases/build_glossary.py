"""BuildGlossary — materialize a per-language glossary from the term cache.

Runs once per target language, right after ``ResolveTerms``. For each term
the resolver surfaced, we prefer (in order):

1. A canonical glossary hit for ``target_lang`` — via the KB retriever.
2. An entity note whose ``## Decision`` says *keep as-is* → source = target.
3. Nothing — the term is left for the translator to handle inline.

Glossary hits are also cached in the shared :class:`TermLookupCache` under
``(term, domain, target_lang)`` so subsequent runs against the same KB
version skip the retriever roundtrip.

Body-parse only. The KB stores glossary translations as Markdown bullets
under a ``## Translations`` heading (``- {lang}: {translation}``); mirroring
that shape keeps the retrieval API agnostic of lang plumbing.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..domain import GlossaryEntry
from .ports import KnowledgeRetriever, TermLookupCache

_TRANSLATIONS_HEADING = re.compile(r"^\s*##\s+Translations\s*$", re.MULTILINE)
_NEXT_HEADING = re.compile(r"^\s*##\s+\S", re.MULTILINE)
_LANG_BULLET = re.compile(r"^\s*-\s*([A-Za-z]{2,3}(?:[-_][A-Za-z0-9]+)?)\s*:\s*(.+?)\s*$")
_DECISION_HEADING = re.compile(r"^\s*##\s+Decision\s*$", re.MULTILINE)
_KEEP_AS_IS = re.compile(
    r"\bas[- ]is\b|do\s+not\s+translate|preserve\s+verbatim",
    re.IGNORECASE,
)

_MISS_MARKER = {"hit": None}


@dataclass(slots=True)
class BuildGlossaryOutput:
    entries: list[GlossaryEntry] = field(default_factory=list)
    cache_hits: int = 0
    cache_misses: int = 0


class BuildGlossary:
    """Use-case: turn a resolver cache into ``BuildGlossaryOutput`` for one lang."""

    def __init__(
        self,
        *,
        retriever: KnowledgeRetriever,
        lookup_cache: TermLookupCache | None = None,
    ) -> None:
        self._retriever = retriever
        self._lookup_cache = lookup_cache

    def execute(
        self,
        term_cache: Mapping[str, Mapping[str, Any]],
        target_lang: str,
        *,
        domain: str | None = None,
    ) -> BuildGlossaryOutput:
        out = BuildGlossaryOutput()
        seen: set[str] = set()
        for term, cached in term_cache.items():
            hit, from_cache = self._glossary_lookup(term, target_lang, domain)
            if from_cache:
                out.cache_hits += 1
            else:
                out.cache_misses += 1
            entry = self._entry_for(term, cached, hit, target_lang)
            if entry is None:
                continue
            key = entry.source.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.entries.append(entry)
        if self._lookup_cache is not None:
            self._lookup_cache.flush()
        return out

    def _glossary_lookup(
        self,
        term: str,
        target_lang: str,
        domain: str | None,
    ) -> tuple[Mapping[str, Any] | None, bool]:
        if self._lookup_cache is not None:
            cached = self._lookup_cache.get(
                term, domain=domain, target_lang=target_lang
            )
            if cached is not None:
                return cached.get("hit"), True
        hit = self._retriever.glossary(term, target_lang)
        if self._lookup_cache is not None:
            payload = {"hit": dict(hit)} if hit is not None else _MISS_MARKER
            self._lookup_cache.put(
                term, domain=domain, target_lang=target_lang, payload=payload
            )
        return hit, False

    def _entry_for(
        self,
        term: str,
        cached: Mapping[str, Any],
        glossary_hit: Mapping[str, Any] | None,
        target_lang: str,
    ) -> GlossaryEntry | None:
        if glossary_hit is not None:
            translation = _translation_from_body(
                glossary_hit.get("body", ""), target_lang
            )
            if translation:
                return GlossaryEntry(
                    source=term,
                    target=translation,
                    kind="glossary",
                    kb_id=glossary_hit.get("id"),
                    rationale=_frontmatter_rationale(glossary_hit),
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
    if not body or not target_lang:
        return None
    heading = _TRANSLATIONS_HEADING.search(body)
    if heading is None:
        return None
    start = heading.end()
    tail = body[start:]
    next_heading = _NEXT_HEADING.search(tail)
    section = tail[: next_heading.start()] if next_heading else tail
    lang_key = target_lang.casefold().replace("_", "-")
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
