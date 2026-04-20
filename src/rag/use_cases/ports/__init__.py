"""Abstract ports the use-case layer depends on.

Adapters in ``rag.adapters`` implement these. Nothing in this package imports
from ``rag.adapters`` — the dependency rule goes the other way.
"""

from __future__ import annotations

from .document import DocumentAdapter
from .llm import LLMClient, LLMMessage
from .metrics import CustomCheck, CustomCheckResult, MetricProfile
from .pipeline import LangBranchState, PipelineDependencies, PipelineRunner, RunState
from .repository import RunRepository
from .retrieval import KnowledgeRetriever
from .term_cache import TermLookupCache

__all__ = [
    "CustomCheck",
    "CustomCheckResult",
    "DocumentAdapter",
    "KnowledgeRetriever",
    "LangBranchState",
    "LLMClient",
    "LLMMessage",
    "MetricProfile",
    "PipelineDependencies",
    "PipelineRunner",
    "RunRepository",
    "RunState",
    "TermLookupCache",
]
