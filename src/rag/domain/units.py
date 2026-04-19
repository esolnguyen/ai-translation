"""Translatable unit value objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class UnitKind(str, Enum):
    """Kinds of translatable units emitted by adapters."""

    PARAGRAPH = "paragraph"
    HEADING = "heading"
    LIST_ITEM = "list_item"
    RUN = "run"           # docx per-run granularity
    CUE = "cue"           # srt subtitle cue
    CELL = "cell"         # xlsx cell
    CHUNK = "chunk"       # txt paragraph-group


@dataclass(slots=True)
class Unit:
    """One translatable unit produced by a document adapter.

    ``meta`` carries format-specific location data so the writer can splice
    the translation back into the original document faithfully.
    """

    id: str
    kind: UnitKind
    text: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TranslatedUnit:
    """A translated unit produced by the pipeline."""

    id: str
    source_text: str
    target_text: str
    target_lang: str
    meta: dict[str, Any] = field(default_factory=dict)
