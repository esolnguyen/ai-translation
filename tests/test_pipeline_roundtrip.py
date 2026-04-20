"""M8 — roundtrip flag toggles an extra graph edge.

- ``roundtrip=False`` (default): the graph has no roundtrip node and no
  ``roundtrip.json`` is written.
- ``roundtrip=True``: a per-lang node runs after ``review``, writing
  ``roundtrip.json`` with one entry per chunk and populating the per-lang
  manifest summary with ``mean_similarity``.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from rag.adapters.persistence.filesystem import FilesystemRunRepository
from rag.adapters.persistence.term_cache import JsonTermLookupCache
from rag.adapters.pipeline import SimplePipelineRunner
from rag.adapters.pipeline.nodes import build_default_graph
from rag.domain import RunConfig, RunPaths, Unit, UnitKind
from rag.use_cases.ports import (
    Embedder,
    KnowledgeRetriever,
    LLMClient,
    LLMMessage,
    PipelineDependencies,
    RunState,
)


class _ScriptedLLM(LLMClient):
    """Returns canned responses for translator / repair / back-translate."""

    def __init__(
        self,
        translate: dict[str, str],
        back: dict[str, str],
    ) -> None:
        self._translate = translate
        self._back = back

    def complete(
        self,
        messages: Sequence[LLMMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        system = next((m.content for m in messages if m.role == "system"), "")
        user = next((m.content for m in messages if m.role == "user"), "")
        if "round-trip" in system:
            for key, val in self._back.items():
                if key in user:
                    return val
            return ""
        if "document analyst" in system:
            return ""
        if "professional translator" in system:
            for key, val in self._translate.items():
                if key in user:
                    return val
        return ""


class _EmptyRetriever(KnowledgeRetriever):
    def search(
        self, query: str, domain: str | None = None, k: int = 5
    ) -> list[dict[str, Any]]:
        return []

    def glossary(self, term: str, target_lang: str) -> dict[str, Any] | None:
        return None

    def examples(
        self,
        source_text: str,
        source_lang: str,
        target_lang: str,
        domain: str | None = None,
        k: int = 3,
    ) -> list[dict[str, Any]]:
        return []

    def language_card(self, lang: str) -> dict[str, Any] | None:
        return None

    def entity(self, name: str) -> dict[str, Any] | None:
        return None

    def idiom(
        self, phrase: str, source_lang: str, target_lang: str
    ) -> dict[str, Any] | None:
        return None


class _TableEmbedder(Embedder):
    def __init__(self, table: dict[str, list[float]]) -> None:
        self._table = table

    @property
    def name(self) -> str:
        return "table"

    @property
    def dimension(self) -> int:
        return 3

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._table.get(t, [0.0, 0.0, 0.0]) for t in texts]


def _prepare_state(tmp_path: Path, units: list[Unit]) -> tuple[RunState, Path]:
    source_path = tmp_path / "src.txt"
    source_path.write_text("unused", encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    paths = RunPaths.for_run(run_dir, source_path)
    config = RunConfig(source_path=source_path, target_langs=["vi"])
    state = RunState(config=config, paths=paths, units=list(units))
    state.branch("vi")
    return state, run_dir


def _deps(tmp_path: Path, llm: LLMClient, embedder: Embedder | None = None) -> PipelineDependencies:
    return PipelineDependencies(
        llm=llm,
        retriever=_EmptyRetriever(),
        repository=FilesystemRunRepository(),
        term_cache=JsonTermLookupCache(tmp_path / "lookup.json", kb_version="v1"),
        embedder=embedder,
    )


def test_roundtrip_disabled_produces_no_extra_node(tmp_path: Path) -> None:
    units = [Unit(id="u1", kind=UnitKind.PARAGRAPH, text="Hello world.")]
    llm = _ScriptedLLM(
        translate={"Hello world.": "Chào thế giới."},
        back={},
    )
    deps = _deps(tmp_path, llm)
    state, run_dir = _prepare_state(tmp_path, units)

    graph = build_default_graph(deps, roundtrip=False)
    assert "roundtrip" not in graph.nodes

    final = SimplePipelineRunner(graph).run(state)

    nodes_hit = {e["node"] for e in final.events}
    assert "roundtrip" not in nodes_hit
    assert not (run_dir / "vi" / "roundtrip.json").exists()
    assert final.branches["vi"].roundtrip_reports == []


def test_roundtrip_enabled_writes_per_chunk_report(tmp_path: Path) -> None:
    units = [Unit(id="u1", kind=UnitKind.PARAGRAPH, text="Hello world.")]
    llm = _ScriptedLLM(
        translate={"Hello world.": "Chào thế giới."},
        back={"Chào thế giới.": "Hello world."},
    )
    embedder = _TableEmbedder(
        {
            "Hello world.": [1.0, 0.0, 0.0],
            "Hello world.".lower(): [1.0, 0.0, 0.0],
        }
    )
    deps = _deps(tmp_path, llm, embedder=embedder)
    state, run_dir = _prepare_state(tmp_path, units)

    graph = build_default_graph(deps, roundtrip=True)
    assert "roundtrip" in graph.nodes
    assert "roundtrip" in graph.edges["review"]

    final = SimplePipelineRunner(graph).run(state)

    nodes_hit = {e["node"] for e in final.events}
    assert "roundtrip" in nodes_hit

    report_path = run_dir / "vi" / "roundtrip.json"
    assert report_path.exists()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["target_lang"] == "vi"
    (chunk,) = payload["chunks"]
    assert chunk["unit_id"] == "u1"
    assert chunk["back_text"] == "Hello world."
    assert chunk["similarity"] == 1.0

    vi = final.branches["vi"]
    assert vi.roundtrip_mean_similarity == 1.0


def test_roundtrip_node_records_low_similarity_without_repair(
    tmp_path: Path,
) -> None:
    units = [Unit(id="u1", kind=UnitKind.PARAGRAPH, text="Hello world.")]
    llm = _ScriptedLLM(
        translate={"Hello world.": "Chào thế giới."},
        back={"Chào thế giới.": "A completely unrelated sentence."},
    )
    embedder = _TableEmbedder(
        {
            "Hello world.": [1.0, 0.0, 0.0],
            "A completely unrelated sentence.": [0.0, 1.0, 0.0],
        }
    )
    deps = _deps(tmp_path, llm, embedder=embedder)
    state, run_dir = _prepare_state(tmp_path, units)

    graph = build_default_graph(deps, roundtrip=True)
    final = SimplePipelineRunner(graph).run(state)

    vi = final.branches["vi"]
    # Chunk still passes review (pure code); roundtrip is informational only.
    assert vi.chunks_passed == 1
    assert vi.chunks_escalated == 0
    assert vi.roundtrip_mean_similarity == 0.0

    payload = json.loads((run_dir / "vi" / "roundtrip.json").read_text("utf-8"))
    (chunk,) = payload["chunks"]
    assert chunk["similarity"] == 0.0
