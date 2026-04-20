"""Pipeline runners — compile nodes into a graph and drive a run to completion.

Current runner is a hand-rolled topological executor (``SimplePipelineRunner``)
with no external dependency. A LangGraph-backed runner can be swapped in by
registering a new factory branch without changing the node functions.
"""

from __future__ import annotations

import os
from typing import Literal

from ...use_cases.ports import PipelineDependencies, PipelineRunner
from .nodes import build_default_graph, build_simple_graph
from .runner import SimplePipelineRunner

type RunnerKind = Literal["simple", "langgraph"]


def make_pipeline_runner(
    deps: PipelineDependencies,
    kind: RunnerKind | None = None,
    *,
    roundtrip: bool = False,
) -> PipelineRunner:
    resolved = kind or os.environ.get("RAG_PIPELINE", "simple")
    if resolved == "simple":
        return SimplePipelineRunner(build_default_graph(deps, roundtrip=roundtrip))
    if resolved == "langgraph":
        raise NotImplementedError("LangGraph runner is not wired up yet")
    raise ValueError(f"unknown pipeline runner kind: {resolved}")


def make_simple_pipeline_runner(deps: PipelineDependencies) -> PipelineRunner:
    """Short-circuit runner: translate-only, no RAG nodes."""
    return SimplePipelineRunner(build_simple_graph(deps))


__all__ = [
    "SimplePipelineRunner",
    "make_pipeline_runner",
    "make_simple_pipeline_runner",
]
