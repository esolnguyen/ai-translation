"""M4 integration — translate → repair → review over an ambiguous fixture.

Two source units go through the graph:

- "bank" — deliberately ambiguous. The scripted LLM returns a
  ``<sense>…|reason</sense>`` flag; Repair rewrites that span.
- "plain" — no flag. Repair leaves it alone; ``repair.json`` still lands
  but carries no chunk entry for this unit.
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
    KnowledgeRetriever,
    LLMClient,
    LLMMessage,
    PipelineDependencies,
    RunState,
)


class _ScriptedLLM(LLMClient):
    """Dispatch by role/content keyword so analyzer + translator + repair agree."""

    def __init__(self, responses: dict[str, str]) -> None:
        self._responses = responses

    def complete(
        self,
        messages: Sequence[LLMMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        system = next((m.content for m in messages if m.role == "system"), "")
        user = next((m.content for m in messages if m.role == "user"), "")
        if "document analyst" in system:
            return self._responses.get("analyze", "")
        if "repair specialist" in system:
            return self._responses.get("repair", "")
        if "professional translator" in system:
            if "bank" in user:
                return self._responses.get("translate_bank", "")
            return self._responses.get("translate_plain", "")
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
        self,
        phrase: str,
        source_lang: str,
        target_lang: str,
    ) -> dict[str, Any] | None:
        return None


def test_ambiguous_bank_repairs_only_flagged_span(tmp_path: Path) -> None:
    units = [
        Unit(id="u1", kind=UnitKind.PARAGRAPH, text="Meet at the bank tonight."),
        Unit(id="u2", kind=UnitKind.PARAGRAPH, text="Hello world."),
    ]
    llm = _ScriptedLLM(
        {
            "analyze": "",  # forces fallback analysis
            "translate_bank": "Gặp ở <sense>bank|river, not financial</sense> tối nay.",
            "translate_plain": "Chào thế giới.",
            "repair": "bờ sông",
        }
    )
    deps = PipelineDependencies(
        llm=llm,
        retriever=_EmptyRetriever(),
        repository=FilesystemRunRepository(),
        term_cache=JsonTermLookupCache(tmp_path / "lookup.json", kb_version="v1"),
    )

    source_path = tmp_path / "src.txt"
    source_path.write_text("unused", encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    paths = RunPaths.for_run(run_dir, source_path)

    config = RunConfig(source_path=source_path, target_langs=["vi"])
    state = RunState(config=config, paths=paths, units=list(units))
    state.branch("vi")

    final = SimplePipelineRunner(build_default_graph(deps)).run(state)

    # u1 got the repair; u2 is untouched.
    vi = final.branches["vi"]
    assert vi.translations["u1"].target_text == "Gặp ở bờ sông tối nay."
    assert vi.translations["u2"].target_text == "Chào thế giới."
    assert vi.chunks_retried == 1
    assert vi.chunks_escalated == 0

    # repair.json lands with one chunk entry (u1); clean u2 not present.
    repair_path = run_dir / "vi" / "repair.json"
    assert repair_path.exists()
    payload = json.loads(repair_path.read_text(encoding="utf-8"))
    assert payload["target_lang"] == "vi"
    assert len(payload["chunks"]) == 1
    chunk = payload["chunks"][0]
    assert chunk["unit_id"] == "u1"
    assert chunk["escalated"] is False
    assert chunk["actions"][0]["original"] == "bank"
    assert chunk["actions"][0]["replacement"] == "bờ sông"

    # Manifest-style events record flagged + repaired counts.
    translate_events = [e for e in final.events if e["node"] == "translate"]
    (vi_translate,) = [e for e in translate_events if e["lang"] == "vi"]
    assert vi_translate["chunks"] == 2
    assert vi_translate["flagged"] == 1
    repair_events = [e for e in final.events if e["node"] == "repair"]
    (vi_repair,) = [e for e in repair_events if e["lang"] == "vi"]
    assert vi_repair["repaired"] == 1
    assert vi_repair["escalated"] == 0


def test_clean_run_writes_empty_repair_json(tmp_path: Path) -> None:
    units = [Unit(id="u1", kind=UnitKind.PARAGRAPH, text="Hello world.")]
    llm = _ScriptedLLM(
        {
            "analyze": "",
            "translate_plain": "Chào thế giới.",
        }
    )
    deps = PipelineDependencies(
        llm=llm,
        retriever=_EmptyRetriever(),
        repository=FilesystemRunRepository(),
        term_cache=JsonTermLookupCache(tmp_path / "lookup.json", kb_version="v1"),
    )

    source_path = tmp_path / "src.txt"
    source_path.write_text("unused", encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    paths = RunPaths.for_run(run_dir, source_path)

    config = RunConfig(source_path=source_path, target_langs=["vi"])
    state = RunState(config=config, paths=paths, units=list(units))
    state.branch("vi")

    final = SimplePipelineRunner(build_default_graph(deps)).run(state)

    repair_path = run_dir / "vi" / "repair.json"
    assert repair_path.exists()
    payload = json.loads(repair_path.read_text(encoding="utf-8"))
    assert payload["chunks"] == []
    assert final.branches["vi"].chunks_retried == 0
    assert final.branches["vi"].chunks_escalated == 0
