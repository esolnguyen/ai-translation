"""Filesystem-backed ``RunRepository`` — writes under ``.translate-runs/<run-id>/``."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from dataclasses import asdict

from ...domain import AnalysisResult, GlossaryEntry, RunPaths, TranslatedUnit, Unit
from ...use_cases.ports import RunRepository


class FilesystemRunRepository(RunRepository):
    """Default implementation; mirrors the scratchpad layout in ``DESIGN-rag.md``."""

    def init_run(self, paths: RunPaths, manifest: Mapping[str, Any]) -> None:
        paths.run_dir.mkdir(parents=True, exist_ok=True)
        self._write_manifest(paths.manifest, manifest)

    def write_units(self, paths: RunPaths, units: Iterable[Unit]) -> None:
        paths.units.parent.mkdir(parents=True, exist_ok=True)
        with paths.units.open("w", encoding="utf-8") as fh:
            for u in units:
                fh.write(
                    json.dumps(
                        {
                            "id": u.id,
                            "kind": u.kind.value,
                            "text": u.text,
                            "meta": u.meta,
                        },
                        ensure_ascii=False,
                    )
                )
                fh.write("\n")

    def write_analysis(
        self,
        paths: RunPaths,
        analysis: AnalysisResult,
        *,
        candidate_terms: list[str],
        term_cache: Mapping[str, Mapping[str, Any]],
    ) -> None:
        payload = {
            "analysis": asdict(analysis),
            "candidate_terms": candidate_terms,
            "term_cache": {k: dict(v) for k, v in term_cache.items()},
        }
        paths.analysis.parent.mkdir(parents=True, exist_ok=True)
        paths.analysis.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def write_glossary(
        self,
        paths: RunPaths,
        target_lang: str,
        entries: Iterable[GlossaryEntry],
    ) -> None:
        target_file = paths.glossary(target_lang)
        target_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "target_lang": target_lang,
            "entries": [asdict(e) for e in entries],
        }
        target_file.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def write_translated(
        self,
        paths: RunPaths,
        target_lang: str,
        units: Iterable[TranslatedUnit],
    ) -> None:
        target_file = paths.run_dir / target_lang / "translated.jsonl"
        target_file.parent.mkdir(parents=True, exist_ok=True)
        with target_file.open("w", encoding="utf-8") as fh:
            for u in units:
                fh.write(
                    json.dumps(
                        {
                            "id": u.id,
                            "source_text": u.source_text,
                            "target_text": u.target_text,
                            "target_lang": u.target_lang,
                            "meta": u.meta,
                        },
                        ensure_ascii=False,
                    )
                )
                fh.write("\n")

    def finalize_manifest(
        self,
        paths: RunPaths,
        manifest: Mapping[str, Any],
    ) -> None:
        self._write_manifest(paths.manifest, manifest)

    @staticmethod
    def _write_manifest(path: Path, manifest: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
