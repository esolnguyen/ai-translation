"""Glossary entry value object."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class GlossaryEntry:
    """A single term in the run-scoped glossary.

    ``kind`` records whether the entry came from ``kb glossary``,
    ``kb entity``, ``kb idiom``, or resolver-level polysemy lock.
    """

    source: str
    target: str
    kind: str
    kb_id: str | None = None
    rationale: str | None = None
