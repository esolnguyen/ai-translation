"""AnalyzeDocument — classify domain + surface candidate terms.

Rev 3: emits `{domain, sub_domain, summary, candidate_terms}` only. The
translator infers register/tone from the source text itself, so we don't
bother classifying them.

Falls back to a neutral analysis when the LLM returns nothing parseable —
the dry-run path goes through this branch and still produces a usable
``AnalysisResult``.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain import AnalysisResult, Unit
from ._json import extract_json
from .ports import KnowledgeRetriever, LLMClient, LLMMessage

_SAMPLE_CHAR_BUDGET = 6000
_ANALYZER_SYSTEM = (
    "You are a document analyst for a translation pipeline. "
    "Given a snippet from a source document, identify the domain and pull "
    "out domain-specific terms that downstream steps should translate "
    'consistently. Respond with strict JSON only, no prose. Schema: '
    '{"domain": str, "sub_domain": str, "summary": str, '
    '"candidate_terms": [str]}. Use lowercase domain labels '
    '(e.g. "automotive", "legal", "medical", "general"). '
    "``candidate_terms`` should list at most 20 proper nouns, multi-word "
    "domain terms, and acronyms — not common words."
)


@dataclass(slots=True)
class AnalyzeOutput:
    analysis: AnalysisResult
    candidate_terms: list[str]


class AnalyzeDocument:
    """Use-case: build an ``AnalysisResult`` + candidate term list."""

    def __init__(self, *, llm: LLMClient, retriever: KnowledgeRetriever) -> None:
        self._llm = llm
        self._retriever = retriever

    def execute(
        self,
        units: list[Unit],
        source_lang: str,
        domain_hint: str | None = None,
    ) -> AnalyzeOutput:
        sample = _build_sample(units)
        parsed = self._ask_llm(sample) if sample else None

        if parsed is None:
            return AnalyzeOutput(
                analysis=_default_analysis(source_lang, domain_hint),
                candidate_terms=[],
            )

        domain = _string(parsed, "domain", fallback=domain_hint or "general")
        summary = _string(parsed, "summary", fallback="")
        note_ids: list[str] = []
        if summary:
            hits = self._retriever.search(summary, domain=domain_hint or domain, k=5)
            note_ids = [h["id"] for h in hits if "id" in h]

        analysis = AnalysisResult(
            domain=domain,
            sub_domain=_string(parsed, "sub_domain", fallback=""),
            source_lang=source_lang,
            summary=summary,
            retrieved_note_ids=note_ids,
        )
        terms = _string_list(parsed, "candidate_terms")
        return AnalyzeOutput(analysis=analysis, candidate_terms=terms)

    def _ask_llm(self, sample: str) -> dict | None:
        response = self._llm.complete(
            [
                LLMMessage(role="system", content=_ANALYZER_SYSTEM),
                LLMMessage(role="user", content=sample),
            ],
            temperature=0.0,
        )
        return extract_json(response)


def _build_sample(units: list[Unit]) -> str:
    out: list[str] = []
    remaining = _SAMPLE_CHAR_BUDGET
    for u in units:
        if remaining <= 0:
            break
        piece = u.text[:remaining]
        out.append(piece)
        remaining -= len(piece)
    return "\n\n".join(out)


def _default_analysis(source_lang: str, domain_hint: str | None) -> AnalysisResult:
    return AnalysisResult(
        domain=domain_hint or "general",
        sub_domain="",
        source_lang=source_lang,
        summary="",
        retrieved_note_ids=[],
    )


def _string(payload: dict, key: str, *, fallback: str) -> str:
    val = payload.get(key)
    return val.strip() if isinstance(val, str) and val.strip() else fallback


def _string_list(payload: dict, key: str) -> list[str]:
    val = payload.get(key)
    if not isinstance(val, list):
        return []
    return [v.strip() for v in val if isinstance(v, str) and v.strip()]
