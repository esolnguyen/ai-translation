"""TranslateDocument — top-level use-case.

Orchestrates one translate call end-to-end by wiring the injected ports
together. Knows nothing about Claude, Mongo, Chroma, or LangGraph; it only
speaks to ports defined in ``rag.use_cases.ports``.
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..domain import RunConfig, RunPaths, Unit, TranslatedUnit
from .mode_select import should_use_simple
from .ports import (
    DocumentAdapter,
    PipelineRunner,
    RunRepository,
    RunState,
)

type DocumentAdapterFactory = Callable[[Path], DocumentAdapter]


@dataclass(slots=True)
class TranslateReport:
    run_id: str
    outputs: dict[str, Path]
    per_lang: dict[str, dict[str, Any]]


class TranslateDocument:
    """Application service — one instance per composition root.

    Dependencies are injected so tests can use fakes. Nothing framework-
    specific lives here.
    """

    def __init__(
        self,
        *,
        document_adapter_factory: DocumentAdapterFactory,
        runner: PipelineRunner,
        repository: RunRepository,
        simple_runner: PipelineRunner | None = None,
    ) -> None:
        self._adapter_for = document_adapter_factory
        self._runner = runner
        self._simple_runner = simple_runner
        self._repository = repository

    def execute(self, config: RunConfig) -> TranslateReport:
        if config.run_id is None:
            config.run_id = _new_run_id(config.source_path)

        paths = RunPaths.for_run(config.run_dir, config.source_path)
        manifest = _build_manifest(config, status="running")
        self._repository.init_run(paths, manifest)

        adapter = self._adapter_for(config.source_path)
        units = adapter.extract(config.source_path)
        self._repository.write_units(paths, units)

        state = RunState(config=config, paths=paths, units=units)
        for lang in config.target_langs:
            state.branch(lang)

        runner = self._pick_runner(config, units)
        state = runner.run(state)

        outputs: dict[str, Path] = {}
        per_lang: dict[str, dict[str, Any]] = {}
        for lang, branch in state.branches.items():
            output_path = _output_path_for(config.source_path, lang)
            translated = _dummy_translations(units, lang) if config.dry_run else list(branch.translations.values())
            if not config.dry_run or translated:
                adapter.write(config.source_path, translated, lang, output_path)
                outputs[lang] = output_path
            per_lang[lang] = {
                "chunks_total": branch.chunks_total,
                "chunks_passed": branch.chunks_passed,
                "chunks_retried": branch.chunks_retried,
                "chunks_escalated": branch.chunks_escalated,
                "output_path": str(outputs.get(lang, "")),
            }
            if branch.roundtrip_reports:
                per_lang[lang]["roundtrip"] = {
                    "chunks": len(branch.roundtrip_reports),
                    "mean_similarity": branch.roundtrip_mean_similarity,
                }

        final_manifest = _build_manifest(
            config,
            status="done",
            per_lang=per_lang,
            events=state.events,
        )
        self._repository.finalize_manifest(paths, final_manifest)
        return TranslateReport(
            run_id=config.run_id,
            outputs=outputs,
            per_lang=per_lang,
        )

    def _pick_runner(self, config: RunConfig, units: list[Unit]) -> PipelineRunner:
        if self._simple_runner is not None and should_use_simple(config, units):
            return self._simple_runner
        return self._runner


def _new_run_id(source: Path) -> str:
    return f"{int(time.time())}-{source.stem}-{secrets.token_hex(3)}"


def _output_path_for(source: Path, target_lang: str) -> Path:
    return source.with_name(f"{source.stem}.{target_lang}{source.suffix}")


def _dummy_translations(units: list[Unit], target_lang: str) -> list[TranslatedUnit]:
    """Dry-run writer — keeps round-trip surface exercised without LLM calls."""
    return [
        TranslatedUnit(
            id=u.id,
            source_text=u.text,
            target_text=u.text,
            target_lang=target_lang,
            meta=dict(u.meta),
        )
        for u in units
    ]


def _build_manifest(
    config: RunConfig,
    *,
    status: str,
    per_lang: dict[str, dict[str, Any]] | None = None,
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "source_path": str(config.source_path),
        "source_lang": config.source_lang,
        "target_langs": config.target_langs,
        "run_id": config.run_id,
        "status": status,
        "config": {
            k: (str(v) if isinstance(v, Path) else v)
            for k, v in asdict(config).items()
            if k != "source_path"
        },
    }
    if per_lang is not None:
        doc["per_lang"] = per_lang
    if events is not None:
        doc["events"] = events
    return doc
