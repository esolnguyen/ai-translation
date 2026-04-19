"""DocumentAdapter port — parse input file, reconstruct output file."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from pathlib import Path

from ...domain import TranslatedUnit, Unit


class DocumentAdapter(ABC):
    """Parse and rebuild one document format.

    Adapters are **thin I/O wrappers**. They read and write on disk; the
    pipeline only ever sees ``Unit`` text. ASTs, style trees, workbook
    structures never flow through the conversation.

    Round-trip contract: ``write(extract(src))`` equals ``src`` when every
    ``TranslatedUnit`` equals its source ``Unit`` verbatim.
    """

    extension: str

    @abstractmethod
    def extract(self, source_path: Path) -> list[Unit]:
        """Parse ``source_path`` and return translatable units."""

    @abstractmethod
    def write(
        self,
        source_path: Path,
        translated: Iterable[TranslatedUnit],
        target_lang: str,
        output_path: Path,
    ) -> None:
        """Rebuild the output file from ``translated`` units.

        Must never mutate ``source_path``; all output goes to ``output_path``.
        """
