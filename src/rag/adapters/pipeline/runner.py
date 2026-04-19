"""SimplePipelineRunner — walks a ``Graph`` in topo order.

Per-lang nodes (``NodeSpec.per_lang=True``) are invoked once per target
language listed in ``state.config.target_langs``. Each branch shares the
same ``RunState`` (nodes update ``state.branches[lang]``).
"""

from __future__ import annotations

from typing import cast

from ...use_cases.ports import PipelineRunner, RunState
from .graph import BranchNode, Graph, Node


class SimplePipelineRunner(PipelineRunner):
    def __init__(self, graph: Graph) -> None:
        self._graph = graph
        self._order = graph.topo_order()

    def run(self, state: RunState) -> RunState:
        for name in self._order:
            spec = self._graph.nodes[name]
            if spec.per_lang:
                fn = cast(BranchNode, spec.fn)
                for lang in state.config.target_langs:
                    state.branch(lang)
                    state = fn(state, lang)
            else:
                fn = cast(Node, spec.fn)
                state = fn(state)
        return state
