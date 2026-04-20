"""Metrics adapters — universal custom checks + registries.

Per the Rev 3 reviewer design in ``PLAN-rag-pipeline.md`` §4, custom checks
are small pure functions wrapped as named gates. The reviewer loads the
checks it needs via a :class:`CustomCheckRegistry` keyed on the active
:class:`MetricProfile`.
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
from .profile_registry import DefaultMetricProfileRegistry, default_profile
from .registry import InMemoryCustomCheckRegistry, default_custom_check_registry
from .vault_loader import VaultMetricProfileRegistry

__all__ = [
    "ChunkContext",
    "DefaultMetricProfileRegistry",
    "GlossaryAdherenceCheck",
    "InMemoryCustomCheckRegistry",
    "LengthSanityCheck",
    "MarkdownIntegrityCheck",
    "PlaceholderRoundTripCheck",
    "TagBalanceCheck",
    "VaultMetricProfileRegistry",
    "default_custom_check_registry",
    "default_profile",
]
