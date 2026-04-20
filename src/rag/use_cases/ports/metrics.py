"""MetricProfile + CustomCheck ports (Rev 3).

A metric profile bundles per-language scoring weights, repair settings, and
the set of custom pass/fail gates a language needs. Loaded from the
language card in the vault (see ``PLAN-rag-pipeline.md`` §4). The Rev 3
reviewer makes zero LLM calls — it combines a rule-based checklist,
embedding cosine vs retrieved examples, and named custom checks.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True, frozen=True)
class MetricWeights:
    """Composite score weights. Should sum to 1.0."""

    checklist: float
    similarity: float
    custom: float


@dataclass(slots=True, frozen=True)
class CustomCheckResult:
    name: str
    passed: bool
    detail: str | None = None


@dataclass(slots=True, frozen=True)
class MetricProfile:
    """Per-language scoring config. Immutable after load."""

    lang: str
    weights: MetricWeights
    repair_max_passes: int = 1
    custom_check_names: list[str] = field(default_factory=list)


class CustomCheck(ABC):
    """One named pass/fail gate runnable against a translated chunk."""

    name: str

    @abstractmethod
    def run(
        self,
        draft: str,
        source: str,
        context: Any,
    ) -> CustomCheckResult:
        """Return the check result for ``draft`` given ``source`` + ``context``."""


class CustomCheckRegistry(ABC):
    """Resolve a check name to its implementation."""

    @abstractmethod
    def get(self, name: str) -> CustomCheck:
        """Return the check registered under ``name`` (raises on miss)."""

    @abstractmethod
    def resolve(self, names: Sequence[str]) -> list[CustomCheck]:
        """Batch lookup; preserves order."""


class MetricProfileRegistry(ABC):
    """Resolve a language tag to its :class:`MetricProfile`."""

    @abstractmethod
    def get(self, lang: str) -> MetricProfile:
        """Return the profile for ``lang``; falls back to a default."""
