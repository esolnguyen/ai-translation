"""Translator self-flag value object.

The translator emits ``<unsure>…</unsure>`` and ``<sense>…|reason</sense>``
spans inline. After parsing, the draft holds clean text and a parallel
list of :class:`TranslationFlag` describing each flagged span. Repair
reads these spans to rewrite only the flagged portions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FlagKind(str, Enum):
    UNSURE = "unsure"
    SENSE = "sense"


@dataclass(slots=True)
class TranslationFlag:
    """One self-flagged span in the translator draft.

    ``start`` / ``end`` are character offsets into the *clean* target text
    (after the tags have been stripped). ``reason`` carries the short
    explanation the translator emitted after the ``|`` inside ``<sense>``
    tags, or is empty for ``<unsure>``.
    """

    kind: FlagKind
    text: str
    start: int
    end: int
    reason: str = ""
