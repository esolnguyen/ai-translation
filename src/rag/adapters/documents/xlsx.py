"""XLSX adapter — one Unit per cell, batched in the translator by row groups."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ...domain import TranslatedUnit, Unit
from ...use_cases.ports import DocumentAdapter


class XlsxAdapter(DocumentAdapter):
    extension = ".xlsx"

    def extract(self, source_path: Path) -> list[Unit]:
        raise NotImplementedError("XlsxAdapter.extract is not implemented yet")

    def write(
        self,
        source_path: Path,
        translated: Iterable[TranslatedUnit],
        target_lang: str,
        output_path: Path,
    ) -> None:
        raise NotImplementedError("XlsxAdapter.write is not implemented yet")
