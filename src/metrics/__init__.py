"""Metrics — universal + language-specific custom checks and profile registries.

Per the Rev 3 reviewer design in ``PLAN-rag-pipeline.md`` §4, custom checks
are small pure functions wrapped as named gates. The reviewer loads the
checks it needs via a :class:`CustomCheckRegistry` keyed on the active
:class:`MetricProfile`.

Split out of ``rag.adapters`` so both the RAG pipeline and the ``kb`` CLI
(for agent-facing quality gates) can import from here without pulling in
the rest of the translation pipeline.
"""

from __future__ import annotations

from .checks import (
    ChunkContext,
    GlossaryAdherenceCheck,
    LengthSanityCheck,
    MarkdownIntegrityCheck,
    PlaceholderRoundTripCheck,
    TagBalanceCheck,
)
from .ports import (
    CustomCheck,
    CustomCheckRegistry,
    CustomCheckResult,
    MetricProfile,
    MetricProfileRegistry,
    MetricWeights,
)
from .profile_registry import DefaultMetricProfileRegistry, default_profile
from .registry import InMemoryCustomCheckRegistry, default_custom_check_registry
from .vault_loader import VaultMetricProfileRegistry

__all__ = [
    "ChunkContext",
    "CustomCheck",
    "CustomCheckRegistry",
    "CustomCheckResult",
    "DefaultMetricProfileRegistry",
    "GlossaryAdherenceCheck",
    "InMemoryCustomCheckRegistry",
    "LengthSanityCheck",
    "MarkdownIntegrityCheck",
    "MetricProfile",
    "MetricProfileRegistry",
    "MetricWeights",
    "PlaceholderRoundTripCheck",
    "TagBalanceCheck",
    "VaultMetricProfileRegistry",
    "default_custom_check_registry",
    "default_profile",
]
