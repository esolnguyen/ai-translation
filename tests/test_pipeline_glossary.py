"""Glossary-node fan-out integration — M3 exit criterion.

Drives ``build_default_graph`` end-to-end with a scripted retriever and a
``NullLLMClient``. Verifies each per-lang branch ends up with a non-empty
glossary, and the filesystem repository writes ``glossary.<lang>.json``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rag.adapters.llm.null import NullLLMClient
from rag.adapters.persistence.filesystem import FilesystemRunRepository
from rag.adapters.persistence.term_cache import JsonTermLookupCache
from rag.adapters.pipeline import SimplePipelineRunner
from rag.adapters.pipeline.nodes import build_default_graph
from rag.domain import RunConfig, RunPaths, Unit, UnitKind
from rag.use_cases.ports import KnowledgeRetriever, PipelineDependencies, RunState


class _ScriptedRetriever(KnowledgeRetriever):
    def __init__(
        self, glossary_hits: dict[tuple[str, str], dict[str, Any]]
    ) -> None:
        self._glossary = glossary_hits

    def search(
        self, query: str, domain: str | None = None, k: int = 5
    ) -> list[dict[str, Any]]:
        return []

    def glossary(self, term: str, target_lang: str) -> dict[str, Any] | None:
        return self._glossary.get((term, target_lang))

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


def test_glossary_node_fanout_writes_per_lang_files(tmp_path: Path) -> None:
    units = [
        Unit(
            id="u1",
            kind=UnitKind.PARAGRAPH,
            text="Operators deploy Pulse Display Service every quarter at NHTSA.",
        ),
    ]
    retriever = _ScriptedRetriever(
        glossary_hits={
            ("Pulse Display Service", "vi"): {
                "id": "g-pds",
                "body": "## Translations\n- vi: Dịch vụ Hiển thị Xung\n- ja: パルス表示サービス\n",
            },
            ("Pulse Display Service", "ja"): {
                "id": "g-pds",
                "body": "## Translations\n- vi: Dịch vụ Hiển thị Xung\n- ja: パルス表示サービス\n",
            },
        }
    )
    repository = FilesystemRunRepository()
    deps = PipelineDependencies(
        llm=NullLLMClient(),
        retriever=retriever,
        repository=repository,
        term_cache=JsonTermLookupCache(tmp_path / "lookup-cache.json", kb_version="v1"),
    )

    run_dir = tmp_path / "run"
    source_path = tmp_path / "src.txt"
    source_path.write_text("unused", encoding="utf-8")
    paths = RunPaths.for_run(run_dir, source_path)
    run_dir.mkdir(parents=True, exist_ok=True)

    config = RunConfig(source_path=source_path, target_langs=["vi", "ja"])
    state = RunState(config=config, paths=paths, units=list(units))
    for lang in config.target_langs:
        state.branch(lang)

    runner = SimplePipelineRunner(build_default_graph(deps))
    final = runner.run(state)

    # Each branch sees at least the Pulse Display Service glossary entry.
    for lang in ("vi", "ja"):
        entries = final.branches[lang].glossary
        sources = [e.source for e in entries]
        assert "Pulse Display Service" in sources, (
            f"{lang} branch missing glossary hit; saw {sources}"
        )

    # Per-lang glossaries land as distinct JSON files with distinct targets.
    vi_path = paths.glossary("vi")
    ja_path = paths.glossary("ja")
    assert vi_path.exists()
    assert ja_path.exists()
    vi_doc = json.loads(vi_path.read_text(encoding="utf-8"))
    ja_doc = json.loads(ja_path.read_text(encoding="utf-8"))
    vi_targets = {e["source"]: e["target"] for e in vi_doc["entries"]}
    ja_targets = {e["source"]: e["target"] for e in ja_doc["entries"]}
    assert vi_targets["Pulse Display Service"] == "Dịch vụ Hiển thị Xung"
    assert ja_targets["Pulse Display Service"] == "パルス表示サービス"

    # Manifest events record cache_hits / cache_misses for the glossary stage.
    glossary_events = [e for e in final.events if e["node"] == "glossary"]
    assert {e["lang"] for e in glossary_events} == {"vi", "ja"}
    for e in glossary_events:
        assert "cache_hits" in e
        assert "cache_misses" in e
