"""M5 integration — reviewer drives a repair retry and escalation.

Two scenarios exercise the review node's loop:

- ``placeholder_round_trip`` fails on the translator draft; scripted LLM
  repairs the missing placeholder; reviewer re-runs and passes.
- A second unit that can't be repaired (LLM returns empty) escalates after
  the profile's ``repair_max_passes`` budget is spent.
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
    def __init__(self, translate: dict[str, str], repair: list[str]) -> None:
        self._translate = translate
        self._repair = list(repair)

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
            return ""
        if "repair specialist" in system:
            if not self._repair:
                return ""
            return self._repair.pop(0)
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


def test_review_retry_repairs_missing_placeholder(tmp_path: Path) -> None:
    units = [Unit(id="u1", kind=UnitKind.PARAGRAPH, text="Hello, {name}!")]
    # Translator drops the placeholder — reviewer catches it and triggers repair.
    llm = _ScriptedLLM(
        translate={"Hello, {name}!": "Xin chào bạn!"},
        repair=["Xin chào, {name}!"],
    )
    deps = PipelineDependencies(
        llm=llm,
        retriever=_EmptyRetriever(),
        repository=FilesystemRunRepository(),
        term_cache=JsonTermLookupCache(tmp_path / "lookup.json", kb_version="v1"),
    )

    state, run_dir = _prepare_state(tmp_path, units)

    final = SimplePipelineRunner(build_default_graph(deps)).run(state)

    vi = final.branches["vi"]
    assert vi.translations["u1"].target_text == "Xin chào, {name}!"
    assert vi.chunks_passed == 1
    assert vi.chunks_escalated == 0

    review_path = run_dir / "vi" / "review.json"
    assert review_path.exists()
    payload = json.loads(review_path.read_text(encoding="utf-8"))
    assert payload["target_lang"] == "vi"
    (chunk,) = payload["chunks"]
    assert chunk["unit_id"] == "u1"
    assert chunk["decision"] == "pass"
    assert chunk["retries"] == 1

    review_events = [e for e in final.events if e["node"] == "review"]
    (vi_event,) = [e for e in review_events if e["lang"] == "vi"]
    assert vi_event["passed"] == 1
    assert vi_event["escalated"] == 0
    assert vi_event["retries"] == 1


def test_review_escalates_when_repair_budget_exhausted(tmp_path: Path) -> None:
    units = [Unit(id="u1", kind=UnitKind.PARAGRAPH, text="Hello, {name}!")]
    # Translator drops the placeholder AND repair also fails to restore it.
    llm = _ScriptedLLM(
        translate={"Hello, {name}!": "Xin chào bạn!"},
        repair=[],  # no repair outputs → review can't recover
    )
    deps = PipelineDependencies(
        llm=llm,
        retriever=_EmptyRetriever(),
        repository=FilesystemRunRepository(),
        term_cache=JsonTermLookupCache(tmp_path / "lookup.json", kb_version="v1"),
    )

    state, run_dir = _prepare_state(tmp_path, units)

    final = SimplePipelineRunner(build_default_graph(deps)).run(state)

    vi = final.branches["vi"]
    assert vi.chunks_passed == 0
    assert vi.chunks_escalated == 1

    review_path = run_dir / "vi" / "review.json"
    payload = json.loads(review_path.read_text(encoding="utf-8"))
    (chunk,) = payload["chunks"]
    assert chunk["decision"] == "escalate"
    assert "placeholder_round_trip" in chunk["failures"]


def test_clean_translation_bypasses_repair(tmp_path: Path) -> None:
    units = [Unit(id="u1", kind=UnitKind.PARAGRAPH, text="Hello world.")]
    llm = _ScriptedLLM(
        translate={"Hello world.": "Chào thế giới."},
        repair=[],
    )
    deps = PipelineDependencies(
        llm=llm,
        retriever=_EmptyRetriever(),
        repository=FilesystemRunRepository(),
        term_cache=JsonTermLookupCache(tmp_path / "lookup.json", kb_version="v1"),
    )

    state, run_dir = _prepare_state(tmp_path, units)

    final = SimplePipelineRunner(build_default_graph(deps)).run(state)

    vi = final.branches["vi"]
    assert vi.chunks_passed == 1
    assert vi.chunks_escalated == 0

    review_payload = json.loads(
        (run_dir / "vi" / "review.json").read_text(encoding="utf-8")
    )
    (chunk,) = review_payload["chunks"]
    assert chunk["retries"] == 0
    assert chunk["decision"] == "pass"
    assert chunk["failures"] == []
