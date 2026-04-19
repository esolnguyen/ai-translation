"""Markdown adapter — AST-aware extraction via ``markdown-it-py``.

Skips code, URLs, and YAML frontmatter. Replaces text-node byte ranges on
write so headings, lists, fences, and inline emphasis round-trip.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ...domain import TranslatedUnit, Unit
from ...use_cases.ports import DocumentAdapter


class MarkdownAdapter(DocumentAdapter):
    extension = ".md"

    def extract(self, source_path: Path) -> list[Unit]:
        raise NotImplementedError("MarkdownAdapter.extract is not implemented yet")

    def write(
        self,
        source_path: Path,
        translated: Iterable[TranslatedUnit],
        target_lang: str,
        output_path: Path,
    ) -> None:
        raise NotImplementedError("MarkdownAdapter.write is not implemented yet")
