"""RunRepository port — persistence for translation runs.

Concrete backends live in ``rag.adapters.persistence``. The default shipped
backend is filesystem (``.translate-runs/<run-id>/``); a Mongo backend is
planned per ``CLAUDE.md`` for shared-state deployments.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from typing import Any

from ...domain import AnalysisResult, GlossaryEntry, RunPaths, TranslatedUnit, Unit


class RunRepository(ABC):
    @abstractmethod
    def init_run(self, paths: RunPaths, manifest: Mapping[str, Any]) -> None:
        """Create the run scratchpad and write the initial manifest."""

    @abstractmethod
    def write_units(self, paths: RunPaths, units: Iterable[Unit]) -> None:
        """Persist the extracted source units."""

    @abstractmethod
    def write_analysis(
        self,
        paths: RunPaths,
        analysis: AnalysisResult,
        *,
        candidate_terms: list[str],
        term_cache: Mapping[str, Mapping[str, Any]],
    ) -> None:
        """Persist analyzer output and the resolved term cache."""

    @abstractmethod
    def write_glossary(
        self,
        paths: RunPaths,
        target_lang: str,
        entries: Iterable[GlossaryEntry],
    ) -> None:
        """Persist the per-language glossary snapshot."""

    @abstractmethod
    def write_translated(
        self,
        paths: RunPaths,
        target_lang: str,
        units: Iterable[TranslatedUnit],
    ) -> None:
        """Persist the per-language translated units."""

    @abstractmethod
    def write_repair(
        self,
        paths: RunPaths,
        target_lang: str,
        reports: Iterable[Mapping[str, Any]],
    ) -> None:
        """Persist the per-language repair audit — one entry per chunk."""

    @abstractmethod
    def write_review(
        self,
        paths: RunPaths,
        target_lang: str,
        reports: Iterable[Mapping[str, Any]],
    ) -> None:
        """Persist the per-language reviewer audit — one entry per chunk."""

    @abstractmethod
    def write_roundtrip(
        self,
        paths: RunPaths,
        target_lang: str,
        reports: Iterable[Mapping[str, Any]],
    ) -> None:
        """Persist the per-language back-translation QA audit."""

    @abstractmethod
    def finalize_manifest(
        self,
        paths: RunPaths,
        manifest: Mapping[str, Any],
    ) -> None:
        """Overwrite the manifest at end-of-run."""
