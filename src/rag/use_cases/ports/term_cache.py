"""TermLookupCache port — cross-run cache for KB term lookups.

Keyed by ``(term, domain, target_lang)`` so one entry can serve multiple
runs targeting the same language/domain combination. ResolveTerms uses
``target_lang=None`` for the shared lang-agnostic lookup (entity + notes);
Glossary (M3) will reuse the same cache with a concrete target lang.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any


class TermLookupCache(ABC):
    @abstractmethod
    def get(
        self,
        term: str,
        *,
        domain: str | None,
        target_lang: str | None,
    ) -> dict[str, Any] | None:
        """Return a cached payload or ``None`` on miss / stale entry."""

    @abstractmethod
    def put(
        self,
        term: str,
        *,
        domain: str | None,
        target_lang: str | None,
        payload: Mapping[str, Any],
    ) -> None:
        """Store ``payload`` under the composite key."""

    @abstractmethod
    def flush(self) -> None:
        """Persist any in-memory writes to the underlying store."""
