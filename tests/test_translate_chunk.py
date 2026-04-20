"""TranslateChunk — prompt assembly + flag extraction from LLM output."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from rag.domain import (
    AnalysisResult,
    FlagKind,
    GlossaryEntry,
    Unit,
    UnitKind,
)
from rag.use_cases.ports import KnowledgeRetriever, LLMClient, LLMMessage
from rag.use_cases.translate_chunk import TranslateChunk


class _EchoLLM(LLMClient):
    """Returns ``script[n]`` for the n-th call, records every message list."""

    def __init__(self, script: list[str]) -> None:
        self._script = list(script)
        self.calls: list[list[LLMMessage]] = []

    def complete(
        self,
        messages: Sequence[LLMMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        self.calls.append(list(messages))
        if not self._script:
            return ""
        return self._script.pop(0)


class _NoExamplesRetriever(KnowledgeRetriever):
    def search(
        self, query: str, domain: str | None = None, k: int = 5
    ) -> list[dict[str, Any]]:
        return []

    def glossary(self, term: str, target_lang: str) -> dict[str, Any] | None:
        return None

    def examples(
        self,
        source_text: str,
        source_lang: str,
        target_lang: str,
        domain: str | None = None,
        k: int = 3,
    ) -> list[dict[str, Any]]:
        return []

    def language_card(self, lang: str) -> dict[str, Any] | None:
        return None

    def entity(self, name: str) -> dict[str, Any] | None:
        return None

    def idiom(
        self,
        phrase: str,
        source_lang: str,
        target_lang: str,
    ) -> dict[str, Any] | None:
        return None


def _unit() -> Unit:
    return Unit(
        id="u1",
        kind=UnitKind.PARAGRAPH,
        text="Deposit the bank statement tomorrow.",
    )


def test_clean_draft_has_no_flags() -> None:
    llm = _EchoLLM(["Nộp sao kê ngân hàng vào ngày mai."])
    translator = TranslateChunk(llm=llm, retriever=_NoExamplesRetriever())

    out = translator.execute(
        _unit(),
        target_lang="vi",
        source_lang="en",
        analysis=None,
        glossary=[],
    )

    assert out.translated.target_text == "Nộp sao kê ngân hàng vào ngày mai."
    assert out.flags == []
    assert out.translated.meta["flags"] == []


def test_flagged_draft_produces_structured_flags() -> None:
    llm = _EchoLLM(
        ["Nộp <unsure>sao kê</unsure> ngân hàng vào <sense>ngày mai|near future</sense>."]
    )
    translator = TranslateChunk(llm=llm, retriever=_NoExamplesRetriever())

    out = translator.execute(
        _unit(),
        target_lang="vi",
        source_lang="en",
        analysis=None,
        glossary=[],
    )

    assert out.translated.target_text == "Nộp sao kê ngân hàng vào ngày mai."
    kinds = [f.kind for f in out.flags]
    assert kinds == [FlagKind.UNSURE, FlagKind.SENSE]
    assert out.flags[1].reason == "near future"


def test_glossary_filters_to_terms_in_source() -> None:
    llm = _EchoLLM(["Dummy output."])
    translator = TranslateChunk(llm=llm, retriever=_NoExamplesRetriever())

    glossary = [
        GlossaryEntry(source="bank", target="ngân hàng", kind="glossary"),
        GlossaryEntry(source="chassis", target="khung gầm", kind="glossary"),
    ]
    translator.execute(
        _unit(),
        target_lang="vi",
        source_lang="en",
        analysis=None,
        glossary=glossary,
    )

    user_msg = next(m for m in llm.calls[0] if m.role == "user")
    assert "bank → ngân hàng" in user_msg.content
    assert "chassis" not in user_msg.content


def test_analysis_injected_into_user_prompt() -> None:
    llm = _EchoLLM(["ok"])
    translator = TranslateChunk(llm=llm, retriever=_NoExamplesRetriever())

    analysis = AnalysisResult(
        domain="finance",
        sub_domain="retail banking",
        source_lang="en",
        summary="End-of-quarter account reconciliation.",
    )
    translator.execute(
        _unit(),
        target_lang="vi",
        source_lang="en",
        analysis=analysis,
        glossary=[],
    )

    user_msg = next(m for m in llm.calls[0] if m.role == "user")
    assert "Domain: finance / retail banking" in user_msg.content
    assert "End-of-quarter" in user_msg.content
