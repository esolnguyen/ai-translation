"""PipelineRunner port + ``RunState`` channel.

``RunState`` is the single mutable value that flows through the graph. Nodes
return updates that get merged in; no node mutates shared references.

Concrete runners live in ``rag.adapters.pipeline`` (hand-rolled now; can be
swapped for a LangGraph runner without changing node functions).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from ...domain import (
    AnalysisResult,
    GlossaryEntry,
    RunConfig,
    RunPaths,
    TranslatedUnit,
    Unit,
)
from .llm import LLMClient
from .repository import RunRepository
from .retrieval import KnowledgeRetriever


@dataclass(slots=True)
class LangBranchState:
    """Per-target-language branch state in the run."""

    target_lang: str
    glossary: list[GlossaryEntry] = field(default_factory=list)
    translations: dict[str, TranslatedUnit] = field(default_factory=dict)
    chunks_total: int = 0
    chunks_passed: int = 0
    chunks_retried: int = 0
    chunks_escalated: int = 0


@dataclass(slots=True)
class RunState:
    """The graph channel: everything every node needs to read or write."""

    config: RunConfig
    paths: RunPaths
    units: list[Unit] = field(default_factory=list)
    analysis: AnalysisResult | None = None
    candidate_terms: list[str] = field(default_factory=list)
    term_cache: dict[str, dict[str, Any]] = field(default_factory=dict)
    branches: dict[str, LangBranchState] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

    def branch(self, lang: str) -> LangBranchState:
        if lang not in self.branches:
            self.branches[lang] = LangBranchState(target_lang=lang)
        return self.branches[lang]

    def record(self, node: str, payload: Mapping[str, Any]) -> None:
        """Append a lightweight audit record — used for dry-run verification."""
        self.events.append({"node": node, **payload})


type NodeFn = Callable[[RunState], RunState]


@dataclass(slots=True, frozen=True)
class PipelineDependencies:
    """Ports handed to node builders at composition time."""

    llm: LLMClient
    retriever: KnowledgeRetriever
    repository: RunRepository


class PipelineRunner(ABC):
    """Compile a set of nodes into a runnable graph and execute one run."""

    @abstractmethod
    def run(self, state: RunState) -> RunState:
        """Execute the full graph against ``state`` and return the final state."""
