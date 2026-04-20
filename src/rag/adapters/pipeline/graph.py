"""Graph primitives — nodes, edges, and a compile step.

A ``Graph`` is a small DAG with two kinds of nodes:

- **sequential nodes** — one input state, one output state
- **fan-out nodes** — declare a branch key (``target_lang``) so downstream
  sequential nodes run once per branch value

The runner in ``runner.py`` walks edges in topological order. Keeping this
structure explicit (rather than pulling in LangGraph) means the orchestration
layer is <500 lines, easy to test, and the node functions stay portable.
"""

from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass, field
from ...use_cases.ports import RunState

type Node = Callable[[RunState], RunState]
type BranchNode = Callable[[RunState, str], RunState]


@dataclass(slots=True, frozen=True)
class NodeSpec:
    name: str
    fn: Node | BranchNode
    per_lang: bool = False


@dataclass(slots=True)
class Graph:
    """A compiled DAG of named nodes.

    Edges are stored as an adjacency list keyed by parent node name. The
    runner reads ``entry``, then walks edges in declaration order. There are
    no conditional edges yet — the reviewer retry loop is handled *inside*
    its per-lang branch node.
    """

    entry: str
    nodes: dict[str, NodeSpec] = field(default_factory=dict)
    edges: dict[str, list[str]] = field(default_factory=dict)

    def add(self, spec: NodeSpec) -> None:
        if spec.name in self.nodes:
            raise ValueError(f"duplicate node: {spec.name}")
        self.nodes[spec.name] = spec
        self.edges.setdefault(spec.name, [])

    def connect(self, parent: str, child: str) -> None:
        if parent not in self.nodes:
            raise KeyError(f"unknown parent node: {parent}")
        if child not in self.nodes:
            raise KeyError(f"unknown child node: {child}")
        self.edges[parent].append(child)

    def topo_order(self) -> list[str]:
        """Kahn's algorithm; raises on cycles."""
        indeg: dict[str, int] = {n: 0 for n in self.nodes}
        for children in self.edges.values():
            for c in children:
                indeg[c] += 1
        queue: list[str] = [n for n, d in indeg.items() if d == 0]
        order: list[str] = []
        while queue:
            n = queue.pop(0)
            order.append(n)
            for c in self.edges.get(n, ()):
                indeg[c] -= 1
                if indeg[c] == 0:
                    queue.append(c)
        if len(order) != len(self.nodes):
            raise ValueError("graph has a cycle")
        return order
