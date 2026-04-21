"""TranslateChunk — single-pass translator with inline self-flagging.

Supports two call shapes:

- :meth:`TranslateChunk.execute(unit, ...)` — one LLM call for one unit.
- :meth:`TranslateChunk.execute_batch(units, ...)` — one LLM call for up to
  ``batch_size`` units, with an envelope format so each translation can be
  split back out by source-unit id. If the model fails to return blocks for
  some ids, those units fall back to per-unit calls.

The prompt instructs the LLM to wrap ambiguous spans in
``<unsure>…</unsure>`` / ``<sense>…|reason</sense>`` tags;
:func:`parse_flags` then strips the tags and returns the clean text plus a
structured flag list that :class:`~rag.use_cases.repair_chunk` consumes
downstream.

Knows nothing about retries — a clean draft flows through untouched, and
flagged drafts are handed to Repair by the pipeline node.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from ..domain import AnalysisResult, GlossaryEntry, TranslatedUnit, TranslationFlag, Unit
from .flag_parser import parse_flags
from .ports import KnowledgeRetriever, LLMClient, LLMMessage

_TRANSLATOR_SYSTEM_SINGLE = (
    "You are a professional translator. Translate the user message from "
    "{source_lang} to {target_lang}. Follow these rules:\n"
    "1. Preserve meaning and register faithfully; do not summarize.\n"
    "2. When a glossary term appears, use the provided target verbatim.\n"
    "3. Wrap spans you are unsure about in <unsure>...</unsure>.\n"
    "4. Wrap spans whose sense you had to disambiguate in "
    "<sense>chosen|short reason</sense>.\n"
    "5. Return only the translated text — no prefix, suffix, or commentary."
)

_TRANSLATOR_SYSTEM_BATCH = (
    "You are a professional translator. Translate each source unit from "
    "{source_lang} to {target_lang}. Follow these rules:\n"
    "1. Preserve meaning and register faithfully; do not summarize.\n"
    "2. When a glossary term appears, use the provided target verbatim.\n"
    "3. Wrap spans you are unsure about in <unsure>...</unsure>.\n"
    "4. Wrap spans whose sense you had to disambiguate in "
    "<sense>chosen|short reason</sense>.\n"
    "5. For EACH input block ``<<<SRC id=\"X\">>>``, return exactly one "
    "output block ``<<<TGT id=\"X\">>>`` with the same id, followed by the "
    "translation on the next lines. Use every id exactly once, in the same "
    "order as the input. No prefix, suffix, or commentary outside the "
    "blocks."
)

_TGT_BLOCK_RE = re.compile(
    r'<<<\s*TGT\s+id\s*=\s*"([^"]+)"\s*>>>\s*(.*?)\s*(?=<<<\s*TGT\s+id\s*=\s*"|\Z)',
    re.DOTALL,
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
        batch_size: int = 100,
    ) -> None:
        self._llm = llm
        self._retriever = retriever
        self._example_k = example_k
        self._batch_size = max(1, batch_size)

    @property
    def batch_size(self) -> int:
        return self._batch_size

    def execute(
        self,
        unit: Unit,
        *,
        target_lang: str,
        source_lang: str,
        analysis: AnalysisResult | None,
        glossary: list[GlossaryEntry],
    ) -> TranslateOutput:
        return self._execute_single(
            unit,
            target_lang=target_lang,
            source_lang=source_lang,
            analysis=analysis,
            glossary=glossary,
        )

    def execute_batch(
        self,
        units: list[Unit],
        *,
        target_lang: str,
        source_lang: str,
        analysis: AnalysisResult | None,
        glossary: list[GlossaryEntry],
    ) -> list[TranslateOutput]:
        if not units:
            return []
        if len(units) == 1:
            return [
                self._execute_single(
                    units[0],
                    target_lang=target_lang,
                    source_lang=source_lang,
                    analysis=analysis,
                    glossary=glossary,
                )
            ]
        return self._execute_batched(
            units,
            target_lang=target_lang,
            source_lang=source_lang,
            analysis=analysis,
            glossary=glossary,
        )

    def _execute_single(
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
        messages = _build_single_messages(
            unit=unit,
            source_lang=source_lang,
            target_lang=target_lang,
            analysis=analysis,
            glossary=active_glossary,
            examples=examples,
        )
        raw = self._llm.complete(messages, temperature=0.0)
        return _finalize_output(unit, raw, target_lang)

    def _execute_batched(
        self,
        units: list[Unit],
        *,
        target_lang: str,
        source_lang: str,
        analysis: AnalysisResult | None,
        glossary: list[GlossaryEntry],
    ) -> list[TranslateOutput]:
        domain = analysis.domain if analysis is not None else None
        combined_text = "\n".join(u.text for u in units)
        active_glossary = _filter_glossary(glossary, combined_text)
        pooled_examples = self._pooled_examples(
            units, source_lang=source_lang, target_lang=target_lang, domain=domain
        )
        messages = _build_batch_messages(
            units=units,
            source_lang=source_lang,
            target_lang=target_lang,
            analysis=analysis,
            glossary=active_glossary,
            examples=pooled_examples,
        )
        raw = self._llm.complete(messages, temperature=0.0)
        parsed = _parse_batch_output(raw)

        by_id: dict[str, TranslateOutput] = {}
        missing: list[Unit] = []
        for unit in units:
            body = parsed.get(unit.id)
            if body is None:
                missing.append(unit)
                continue
            by_id[unit.id] = _finalize_output(unit, body, target_lang)

        for unit in missing:
            by_id[unit.id] = self._execute_single(
                unit,
                target_lang=target_lang,
                source_lang=source_lang,
                analysis=analysis,
                glossary=glossary,
            )

        return [by_id[u.id] for u in units]

    def _pooled_examples(
        self,
        units: list[Unit],
        *,
        source_lang: str,
        target_lang: str,
        domain: str | None,
    ) -> list[dict[str, Any]]:
        seen: set[tuple[str, str]] = set()
        pooled: list[dict[str, Any]] = []
        for unit in units:
            for ex in self._retriever.examples(
                unit.text,
                source_lang=source_lang,
                target_lang=target_lang,
                domain=domain,
                k=self._example_k,
            ):
                src = _example_source(ex)
                tgt = _example_target(ex)
                if not src or not tgt:
                    continue
                key = (src, tgt)
                if key in seen:
                    continue
                seen.add(key)
                pooled.append(ex)
        return pooled


def _finalize_output(unit: Unit, raw: str, target_lang: str) -> TranslateOutput:
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


def _parse_batch_output(raw: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for match in _TGT_BLOCK_RE.finditer(raw):
        unit_id = match.group(1).strip()
        body = match.group(2).strip()
        if unit_id and unit_id not in parsed:
            parsed[unit_id] = body
    return parsed


def _filter_glossary(
    glossary: list[GlossaryEntry], source_text: str
) -> list[GlossaryEntry]:
    lowered = source_text.lower()
    return [g for g in glossary if g.source.lower() in lowered]


def _common_preamble(
    *,
    analysis: AnalysisResult | None,
    glossary: list[GlossaryEntry],
    examples: list[dict[str, Any]],
) -> list[str]:
    parts: list[str] = []
    if analysis is not None and (analysis.domain or analysis.summary):
        parts.append(
            f"Domain: {analysis.domain or 'general'}"
            + (f" / {analysis.sub_domain}" if analysis.sub_domain else "")
        )
        if analysis.summary:
            parts.append(f"Summary: {analysis.summary}")
    if glossary:
        lines = "\n".join(f"- {g.source} → {g.target}" for g in glossary)
        parts.append(f"Glossary (use verbatim):\n{lines}")
    if examples:
        lines = "\n".join(
            f"- {_example_source(ex)} → {_example_target(ex)}"
            for ex in examples
            if _example_source(ex) and _example_target(ex)
        )
        if lines:
            parts.append(f"Examples:\n{lines}")
    return parts


def _build_single_messages(
    *,
    unit: Unit,
    source_lang: str,
    target_lang: str,
    analysis: AnalysisResult | None,
    glossary: list[GlossaryEntry],
    examples: list[dict[str, Any]],
) -> list[LLMMessage]:
    system = _TRANSLATOR_SYSTEM_SINGLE.format(
        source_lang=source_lang, target_lang=target_lang
    )
    user_parts = _common_preamble(
        analysis=analysis, glossary=glossary, examples=examples
    )
    user_parts.append(f"Source ({source_lang}):\n{unit.text}")
    return [
        LLMMessage(role="system", content=system),
        LLMMessage(role="user", content="\n\n".join(user_parts)),
    ]


def _build_batch_messages(
    *,
    units: list[Unit],
    source_lang: str,
    target_lang: str,
    analysis: AnalysisResult | None,
    glossary: list[GlossaryEntry],
    examples: list[dict[str, Any]],
) -> list[LLMMessage]:
    system = _TRANSLATOR_SYSTEM_BATCH.format(
        source_lang=source_lang, target_lang=target_lang
    )
    user_parts = _common_preamble(
        analysis=analysis, glossary=glossary, examples=examples
    )
    blocks = "\n".join(
        f'<<<SRC id="{u.id}">>>\n{u.text}' for u in units
    )
    user_parts.append(
        f"Source units ({source_lang}). Translate each into {target_lang} "
        f"and return each under the matching ``<<<TGT id=\"…\">>>`` block:\n"
        f"{blocks}"
    )
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
