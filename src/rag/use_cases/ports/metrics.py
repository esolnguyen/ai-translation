"""MetricProfile + CustomCheck ports.

A metric profile bundles the per-language scoring weights, cycle-check mode,
optional external metrics, and custom pass/fail gates. Loaded from the
language card in the vault (see ``PLAN-rag-pipeline.md`` §4).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal


type CycleCheckMode = Literal["scalpel_only", "primary", "off"]


@dataclass(slots=True, frozen=True)
class MetricWeights:
    ground: float
    example: float
    checklist: float


@dataclass(slots=True, frozen=True)
class ExternalMetric:
    name: str
    weight: float


@dataclass(slots=True, frozen=True)
class CustomCheckResult:
    name: str
    passed: bool
    detail: str | None = None


@dataclass(slots=True)
class MetricProfile:
    """Per-language scoring config. Immutable after load."""

    lang: str
    weights: MetricWeights
    cycle_check_mode: CycleCheckMode
    cycle_check_threshold: float
    external_metrics: list[ExternalMetric]
    custom_check_names: list[str]


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
