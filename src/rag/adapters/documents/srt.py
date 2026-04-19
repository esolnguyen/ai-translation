"""SRT subtitle adapter — one Unit per cue, timing preserved verbatim."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ...domain import TranslatedUnit, Unit
from ...use_cases.ports import DocumentAdapter


class SrtAdapter(DocumentAdapter):
    extension = ".srt"

    def extract(self, source_path: Path) -> list[Unit]:
        raise NotImplementedError("SrtAdapter.extract is not implemented yet")

    def write(
        self,
        source_path: Path,
        translated: Iterable[TranslatedUnit],
        target_lang: str,
        output_path: Path,
    ) -> None:
        raise NotImplementedError("SrtAdapter.write is not implemented yet")
