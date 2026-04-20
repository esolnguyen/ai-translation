"""Abstract ports the use-case layer depends on.

Adapters in ``rag.adapters`` implement these. Nothing in this package imports
from ``rag.adapters`` — the dependency rule goes the other way.
"""

from __future__ import annotations

from .document import DocumentAdapter
from .embedder import Embedder
from .llm import LLMClient, LLMMessage
from .metrics import (
    CustomCheck,
    CustomCheckRegistry,
    CustomCheckResult,
    MetricProfile,
    MetricProfileRegistry,
    MetricWeights,
)
from .pipeline import LangBranchState, PipelineDependencies, PipelineRunner, RunState
from .repository import RunRepository
from .retrieval import KnowledgeRetriever
from .term_cache import TermLookupCache

__all__ = [
    "CustomCheck",
    "CustomCheckRegistry",
    "CustomCheckResult",
    "DocumentAdapter",
    "Embedder",
    "KnowledgeRetriever",
    "LangBranchState",
    "LLMClient",
    "LLMMessage",
    "MetricProfile",
    "MetricProfileRegistry",
    "MetricWeights",
    "PipelineDependencies",
    "PipelineRunner",
    "RunRepository",
    "RunState",
    "TermLookupCache",
]
