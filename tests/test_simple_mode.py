"""M7 — simple-mode pipeline + runner selection.

Three scenarios:

- ``build_simple_graph`` runs only a translate node; no analysis/glossary/
  review/repair events are recorded; LLM is called exactly once per unit
  per target language.
- ``TranslateDocument`` picks the simple runner when auto-selection fires,
  the full runner when ``--no-simple`` is explicit, and obeys ``--simple``
  even on a many-word input.
- A 100-word × 5-language run through the router-level composition uses
  ≤6 LLM calls total (plan §3 exit criterion).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from rag.adapters.persistence.filesystem import FilesystemRunRepository
from rag.adapters.pipeline import (
    SimplePipelineRunner,
    make_simple_pipeline_runner,
)
from rag.adapters.pipeline.nodes import build_default_graph, build_simple_graph
from rag.domain import (
    RunConfig,
    RunPaths,
    TranslatedUnit,
    Unit,
    UnitKind,
)
from rag.use_cases.ports import (
    DocumentAdapter,
    KnowledgeRetriever,
    LLMClient,
    LLMMessage,
    PipelineDependencies,
    PipelineRunner,
    RunState,
)
from rag.use_cases.translate_document import TranslateDocument


class _CountingLLM(LLMClient):
    """Records every call's system role so we can assert which nodes fired."""

    def __init__(self, response: str = "translated") -> None:
        self._response = response
        self.calls: list[str] = []

    def complete(
        self,
        messages: Sequence[LLMMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        system = next((m.content for m in messages if m.role == "system"), "")
        self.calls.append(system)
        return self._response


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


class _FakeAdapter(DocumentAdapter):
    extension = ".txt"

    def __init__(self, units: list[Unit]) -> None:
        self._units = units
        self.written: list[tuple[str, list[TranslatedUnit], Path]] = []

    def extract(self, source_path: Path) -> list[Unit]:
        return list(self._units)

    def write(
        self,
        source_path: Path,
        translated: Iterable[TranslatedUnit],
        target_lang: str,
        output_path: Path,
    ) -> None:
        self.written.append((target_lang, list(translated), output_path))


def _make_deps(tmp_path: Path, llm: LLMClient) -> PipelineDependencies:
    return PipelineDependencies(
        llm=llm,
        retriever=_EmptyRetriever(),
        repository=FilesystemRunRepository(),
    )


def _prepare_state(
    tmp_path: Path, units: list[Unit], langs: list[str]
) -> RunState:
    source_path = tmp_path / "src.txt"
    source_path.write_text("unused", encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    paths = RunPaths.for_run(run_dir, source_path)
    config = RunConfig(source_path=source_path, target_langs=langs)
    state = RunState(config=config, paths=paths, units=list(units))
    for lang in langs:
        state.branch(lang)
    return state


def test_simple_graph_emits_only_translate_events(tmp_path: Path) -> None:
    units = [Unit(id="u1", kind=UnitKind.PARAGRAPH, text="Hello.")]
    llm = _CountingLLM(response="Xin chào.")
    deps = _make_deps(tmp_path, llm)
    state = _prepare_state(tmp_path, units, ["vi"])

    final = SimplePipelineRunner(build_simple_graph(deps)).run(state)

    nodes_hit = {e["node"] for e in final.events}
    assert nodes_hit == {"translate_simple"}
    assert len(llm.calls) == 1
    assert all("professional translator" in s for s in llm.calls)
    vi = final.branches["vi"]
    assert vi.translations["u1"].target_text == "Xin chào."
    assert vi.chunks_passed == 1


def test_simple_graph_calls_translate_once_per_lang_per_unit(
    tmp_path: Path,
) -> None:
    units = [
        Unit(id="u1", kind=UnitKind.PARAGRAPH, text="A."),
        Unit(id="u2", kind=UnitKind.PARAGRAPH, text="B."),
    ]
    llm = _CountingLLM(response="ok")
    deps = _make_deps(tmp_path, llm)
    state = _prepare_state(tmp_path, units, ["vi", "fr"])

    SimplePipelineRunner(build_simple_graph(deps)).run(state)

    assert len(llm.calls) == 2 * 2


def test_translate_document_picks_simple_runner_for_tiny_input(
    tmp_path: Path,
) -> None:
    units = [Unit(id="u1", kind=UnitKind.PARAGRAPH, text="Tiny note.")]
    full_llm = _CountingLLM(response="[FULL]")
    simple_llm = _CountingLLM(response="[SIMPLE]")
    full = SimplePipelineRunner(
        build_default_graph(_make_deps(tmp_path, full_llm))
    )
    simple = SimplePipelineRunner(
        build_simple_graph(_make_deps(tmp_path, simple_llm))
    )

    adapter = _FakeAdapter(units)
    use_case = TranslateDocument(
        document_adapter_factory=lambda _p: adapter,
        runner=full,
        simple_runner=simple,
        repository=FilesystemRunRepository(),
    )
    source = tmp_path / "src.txt"
    source.write_text("unused", encoding="utf-8")
    report = use_case.execute(
        RunConfig(
            source_path=source,
            target_langs=["vi"],
            run_root=tmp_path / ".runs",
        )
    )

    assert full_llm.calls == []
    assert len(simple_llm.calls) == 1
    assert report.per_lang["vi"]["chunks_total"] == 1


def test_translate_document_honours_no_simple_override(tmp_path: Path) -> None:
    units = [Unit(id="u1", kind=UnitKind.PARAGRAPH, text="Tiny note.")]
    full_llm = _CountingLLM(response="[FULL]")
    simple_llm = _CountingLLM(response="[SIMPLE]")
    full = SimplePipelineRunner(
        build_default_graph(_make_deps(tmp_path, full_llm))
    )
    simple = SimplePipelineRunner(
        build_simple_graph(_make_deps(tmp_path, simple_llm))
    )

    adapter = _FakeAdapter(units)
    use_case = TranslateDocument(
        document_adapter_factory=lambda _p: adapter,
        runner=full,
        simple_runner=simple,
        repository=FilesystemRunRepository(),
    )
    source = tmp_path / "src.txt"
    source.write_text("unused", encoding="utf-8")
    use_case.execute(
        RunConfig(
            source_path=source,
            target_langs=["vi"],
            simple_mode=False,
            run_root=tmp_path / ".runs",
        )
    )

    assert simple_llm.calls == []
    # Full pipeline calls analyze + translate at minimum.
    systems = " | ".join(full_llm.calls)
    assert "professional translator" in systems


def test_translate_document_honours_explicit_simple_on_large_input(
    tmp_path: Path,
) -> None:
    long_text = " ".join(["word"] * 800)
    units = [Unit(id="u1", kind=UnitKind.PARAGRAPH, text=long_text)]
    full_llm = _CountingLLM(response="[FULL]")
    simple_llm = _CountingLLM(response="[SIMPLE]")
    full = SimplePipelineRunner(
        build_default_graph(_make_deps(tmp_path, full_llm))
    )
    simple = SimplePipelineRunner(
        build_simple_graph(_make_deps(tmp_path, simple_llm))
    )

    adapter = _FakeAdapter(units)
    use_case = TranslateDocument(
        document_adapter_factory=lambda _p: adapter,
        runner=full,
        simple_runner=simple,
        repository=FilesystemRunRepository(),
    )
    source = tmp_path / "src.txt"
    source.write_text("unused", encoding="utf-8")
    use_case.execute(
        RunConfig(
            source_path=source,
            target_langs=["vi"],
            simple_mode=True,
            run_root=tmp_path / ".runs",
        )
    )

    assert full_llm.calls == []
    assert len(simple_llm.calls) == 1


def test_simple_runner_factory_returns_runner(tmp_path: Path) -> None:
    llm = _CountingLLM()
    deps = _make_deps(tmp_path, llm)
    runner = make_simple_pipeline_runner(deps)
    assert isinstance(runner, PipelineRunner)


def test_100_word_5_lang_run_stays_within_6_calls(tmp_path: Path) -> None:
    """Plan §3 M7 exit criterion: a 100-word × 5-lang run uses ≤6 LLM calls.

    Five target languages × one unit through the simple graph = five LLM
    calls (one per lang). That's comfortably under the six-call budget.
    """
    text = " ".join(["word"] * 100)
    units = [Unit(id="u1", kind=UnitKind.PARAGRAPH, text=text)]
    llm = _CountingLLM(response="translated")
    deps = _make_deps(tmp_path, llm)

    adapter = _FakeAdapter(units)
    full = SimplePipelineRunner(build_default_graph(deps))
    simple = SimplePipelineRunner(build_simple_graph(deps))
    use_case = TranslateDocument(
        document_adapter_factory=lambda _p: adapter,
        runner=full,
        simple_runner=simple,
        repository=FilesystemRunRepository(),
    )
    source = tmp_path / "src.txt"
    source.write_text("unused", encoding="utf-8")
    report = use_case.execute(
        RunConfig(
            source_path=source,
            target_langs=["vi", "fr", "de", "pl", "ja"],
            run_root=tmp_path / ".runs",
        )
    )

    assert len(llm.calls) <= 6
    # Manifest records the chosen mode via translate_simple events.
    manifest_path = Path(report.run_id and (tmp_path / ".runs" / report.run_id / "manifest.json"))
    doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    event_nodes = {e["node"] for e in doc.get("events", [])}
    assert event_nodes == {"translate_simple"}
