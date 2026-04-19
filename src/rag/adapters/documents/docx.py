"""DOCX adapter — per-run extraction preserves formatting."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ...domain import TranslatedUnit, Unit
from ...use_cases.ports import DocumentAdapter


class DocxAdapter(DocumentAdapter):
    extension = ".docx"

    def extract(self, source_path: Path) -> list[Unit]:
        raise NotImplementedError("DocxAdapter.extract is not implemented yet")

    def write(
        self,
        source_path: Path,
        translated: Iterable[TranslatedUnit],
        target_lang: str,
        output_path: Path,
    ) -> None:
        raise NotImplementedError("DocxAdapter.write is not implemented yet")
