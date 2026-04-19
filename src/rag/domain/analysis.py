"""Analyzer output value object."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class AnalysisResult:
    """Analyzer output — injected verbatim into translator prompts.

    Rev 3 schema. ``tone``/``register``/``audience`` were dropped — the
    translator infers register from the source text directly.
    """

    domain: str
    sub_domain: str
    source_lang: str
    summary: str = ""
    retrieved_note_ids: list[str] = field(default_factory=list)
