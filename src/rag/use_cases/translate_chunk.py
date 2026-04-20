"""TranslateChunk — single-pass translator with inline self-flagging.

One call per :class:`~rag.domain.Unit`. The prompt instructs the LLM to
wrap ambiguous spans in ``<unsure>…</unsure>`` / ``<sense>…|reason</sense>``
tags; :func:`parse_flags` then strips the tags and returns the clean text
plus a structured flag list that :class:`~rag.use_cases.repair_chunk`
consumes downstream.

Knows nothing about retries — a clean draft flows through untouched, and
flagged drafts are handed to Repair by the pipeline node.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ..domain import AnalysisResult, GlossaryEntry, TranslatedUnit, TranslationFlag, Unit
from .flag_parser import parse_flags
from .ports import KnowledgeRetriever, LLMClient, LLMMessage

_TRANSLATOR_SYSTEM = (
    "You are a professional translator. Translate the user message from "
    "{source_lang} to {target_lang}. Follow these rules:\n"
    "1. Preserve meaning and register faithfully; do not summarize.\n"
    "2. When a glossary term appears, use the provided target verbatim.\n"
    "3. Wrap spans you are unsure about in <unsure>...</unsure>.\n"
    "4. Wrap spans whose sense you had to disambiguate in "
    "<sense>chosen|short reason</sense>.\n"
    "5. Return only the translated text — no prefix, suffix, or commentary."
)


@dataclass(slots=True)
class TranslateOutput:
    translated: TranslatedUnit
    flags: list[TranslationFlag] = field(default_factory=list)
    raw_response: str = ""


class TranslateChunk:
    def __init__(
        self,
        *,
        llm: LLMClient,
        retriever: KnowledgeRetriever,
        example_k: int = 3,
    ) -> None:
        self._llm = llm
        self._retriever = retriever
        self._example_k = example_k

    def execute(
        self,
        unit: Unit,
        *,
        target_lang: str,
        source_lang: str,
        analysis: AnalysisResult | None,
        glossary: list[GlossaryEntry],
    ) -> TranslateOutput:
        domain = analysis.domain if analysis is not None else None
        active_glossary = _filter_glossary(glossary, unit.text)
        examples = self._retriever.examples(
            unit.text,
            source_lang=source_lang,
            target_lang=target_lang,
            domain=domain,
            k=self._example_k,
        )
        messages = _build_messages(
            unit=unit,
            source_lang=source_lang,
            target_lang=target_lang,
            analysis=analysis,
            glossary=active_glossary,
            examples=examples,
        )
        raw = self._llm.complete(messages, temperature=0.0)
        clean, flags = parse_flags(raw)
        translated = TranslatedUnit(
            id=unit.id,
            source_text=unit.text,
            target_text=clean.strip(),
            target_lang=target_lang,
            meta={
                **unit.meta,
                "flags": [asdict(f) for f in flags],
            },
        )
        return TranslateOutput(translated=translated, flags=flags, raw_response=raw)


def _filter_glossary(
    glossary: list[GlossaryEntry], source_text: str
) -> list[GlossaryEntry]:
    lowered = source_text.lower()
    return [g for g in glossary if g.source.lower() in lowered]


def _build_messages(
    *,
    unit: Unit,
    source_lang: str,
    target_lang: str,
    analysis: AnalysisResult | None,
    glossary: list[GlossaryEntry],
    examples: list[dict[str, Any]],
) -> list[LLMMessage]:
    system = _TRANSLATOR_SYSTEM.format(
        source_lang=source_lang, target_lang=target_lang
    )
    user_parts: list[str] = []
    if analysis is not None and (analysis.domain or analysis.summary):
        user_parts.append(
            f"Domain: {analysis.domain or 'general'}"
            + (f" / {analysis.sub_domain}" if analysis.sub_domain else "")
        )
        if analysis.summary:
            user_parts.append(f"Summary: {analysis.summary}")
    if glossary:
        lines = "\n".join(f"- {g.source} → {g.target}" for g in glossary)
        user_parts.append(f"Glossary (use verbatim):\n{lines}")
    if examples:
        lines = "\n".join(
            f"- {_example_source(ex)} → {_example_target(ex)}"
            for ex in examples
            if _example_source(ex) and _example_target(ex)
        )
        if lines:
            user_parts.append(f"Examples:\n{lines}")
    user_parts.append(f"Source ({source_lang}):\n{unit.text}")
    return [
        LLMMessage(role="system", content=system),
        LLMMessage(role="user", content="\n\n".join(user_parts)),
    ]


def _example_source(example: dict[str, Any]) -> str:
    val = example.get("source") or example.get("text") or ""
    return str(val).strip()


def _example_target(example: dict[str, Any]) -> str:
    val = example.get("target") or ""
    if not val:
        meta = example.get("metadata")
        if isinstance(meta, dict):
            val = meta.get("target") or ""
    return str(val).strip()
