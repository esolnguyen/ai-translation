"""Mongo-backed ``RunRepository`` — stub.

Filled in when shared-state deployments are needed. Connection string +
database name come from env (``RAG_MONGO_URI`` / ``RAG_MONGO_DB``) per
``CLAUDE.md``.
"""

from __future__ import annotations
from collections.abc import Iterable, Mapping
from typing import Any
from ...domain import AnalysisResult, GlossaryEntry, RunPaths, TranslatedUnit, Unit
from ...use_cases.ports import RunRepository


class MongoRunRepository(RunRepository):
    def __init__(self, uri: str, db_name: str) -> None:
        self._uri = uri
        self._db_name = db_name

    @classmethod
    def from_env(cls) -> MongoRunRepository:
        raise NotImplementedError("MongoRunRepository is not wired up yet")

    def init_run(self, paths: RunPaths, manifest: Mapping[str, Any]) -> None:
        raise NotImplementedError

    def write_units(self, paths: RunPaths, units: Iterable[Unit]) -> None:
        raise NotImplementedError

    def write_analysis(
        self,
        paths: RunPaths,
        analysis: AnalysisResult,
        *,
        candidate_terms: list[str],
        term_cache: Mapping[str, Mapping[str, Any]],
    ) -> None:
        raise NotImplementedError

    def write_glossary(
        self,
        paths: RunPaths,
        target_lang: str,
        entries: Iterable[GlossaryEntry],
    ) -> None:
        raise NotImplementedError

    def write_translated(
        self,
        paths: RunPaths,
        target_lang: str,
        units: Iterable[TranslatedUnit],
    ) -> None:
        raise NotImplementedError

    def write_repair(
        self,
        paths: RunPaths,
        target_lang: str,
        reports: Iterable[Mapping[str, Any]],
    ) -> None:
        raise NotImplementedError

    def finalize_manifest(
        self,
        paths: RunPaths,
        manifest: Mapping[str, Any],
    ) -> None:
        raise NotImplementedError
