"""SimplePipelineRunner — walks a ``Graph`` in topo order.

Per-lang nodes (``NodeSpec.per_lang=True``) are invoked once per target
language listed in ``state.config.target_langs``. Each branch shares the
same ``RunState`` (nodes update ``state.branches[lang]``).
"""

from __future__ import annotations

import logging
import time
from typing import cast

from ...use_cases.ports import PipelineRunner, RunState
from .graph import BranchNode, Graph, Node

logger = logging.getLogger(__name__)


class SimplePipelineRunner(PipelineRunner):
    def __init__(self, graph: Graph) -> None:
        self._graph = graph
        self._order = graph.topo_order()

    def run(self, state: RunState) -> RunState:
        run_id = state.config.run_id
        logger.info(
            "pipeline start run_id=%s nodes=%s langs=%s",
            run_id, self._order, state.config.target_langs,
        )
        for name in self._order:
            spec = self._graph.nodes[name]
            if spec.per_lang:
                fn = cast(BranchNode, spec.fn)
                for lang in state.config.target_langs:
                    state.branch(lang)
                    started = time.perf_counter()
                    logger.info("node start name=%s lang=%s run_id=%s", name, lang, run_id)
                    state = fn(state, lang)
                    logger.info(
                        "node done  name=%s lang=%s run_id=%s elapsed=%.2fs",
                        name, lang, run_id, time.perf_counter() - started,
                    )
            else:
                fn = cast(Node, spec.fn)
                started = time.perf_counter()
                logger.info("node start name=%s run_id=%s", name, run_id)
                state = fn(state)
                logger.info(
                    "node done  name=%s run_id=%s elapsed=%.2fs",
                    name, run_id, time.perf_counter() - started,
                )
        logger.info("pipeline end   run_id=%s", run_id)
        return state
