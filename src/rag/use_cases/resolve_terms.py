"""ResolveTerms — build a KB-grounded term cache for the run.

Runs once between Analyze and per-lang Glossary. Lang-agnostic: resolves
each candidate term against the shared KB so every target-language branch
reuses the same lookup.

Sources of candidates:
- ``state.candidate_terms`` — LLM output from Analyze (may be empty)
- Heuristic extraction from ``state.units`` — capitalized multi-word phrases,
  acronyms; ensures the cache is non-empty even with a null LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..domain import Unit
from .ports import KnowledgeRetriever, TermLookupCache

_PROPER_PHRASE = re.compile(r"\b(?:[A-Z][a-z0-9]+(?:\s+[A-Z][a-z0-9]+)+)\b")
_ACRONYM = re.compile(r"\b[A-Z]{2,6}(?:-[A-Z0-9]+)?\b")
_MAX_HEURISTIC_TERMS = 30


@dataclass(slots=True)
class ResolveOutput:
    cache: dict[str, dict[str, Any]] = field(default_factory=dict)
    total: int = 0
    resolved: int = 0
    cache_hits: int = 0
    cache_misses: int = 0

    @property
    def hit_rate(self) -> float:
        return self.resolved / self.total if self.total else 0.0


class ResolveTerms:
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
        units: list[Unit],
        llm_candidates: list[str],
        *,
        domain: str | None = None,
    ) -> ResolveOutput:
        candidates = _dedupe_preserve_order(
            list(llm_candidates) + _heuristic_candidates(units)
        )
        out = ResolveOutput(total=len(candidates))
        for term in candidates:
            entry, hit = self._lookup(term, domain)
            if hit:
                out.cache_hits += 1
            else:
                out.cache_misses += 1
            if entry["entity"] is not None or entry["notes"]:
                out.resolved += 1
            out.cache[term] = entry
        if self._lookup_cache is not None:
            self._lookup_cache.flush()
        return out

    def _lookup(
        self, term: str, domain: str | None
    ) -> tuple[dict[str, Any], bool]:
        if self._lookup_cache is not None:
            cached = self._lookup_cache.get(term, domain=domain, target_lang=None)
            if cached is not None:
                return cached, True
        entry: dict[str, Any] = {"entity": None, "notes": []}
        entity = self._retriever.entity(term)
        if entity is not None:
            entry["entity"] = entity
        hits = self._retriever.search(term, domain=domain, k=1)
        if hits:
            entry["notes"] = hits
        if self._lookup_cache is not None:
            self._lookup_cache.put(term, domain=domain, target_lang=None, payload=entry)
        return entry, False


def _heuristic_candidates(units: list[Unit]) -> list[str]:
    seen: dict[str, None] = {}
    for u in units:
        for m in _PROPER_PHRASE.finditer(u.text):
            seen.setdefault(m.group(0), None)
            if len(seen) >= _MAX_HEURISTIC_TERMS:
                return list(seen)
        for m in _ACRONYM.finditer(u.text):
            seen.setdefault(m.group(0), None)
            if len(seen) >= _MAX_HEURISTIC_TERMS:
                return list(seen)
    return list(seen)


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for item in items:
        key = item.strip()
        if key and key not in seen:
            seen[key] = None
    return list(seen)
