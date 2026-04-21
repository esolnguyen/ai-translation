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


def _units(ids: list[str]) -> list[Unit]:
    return [
        Unit(id=uid, kind=UnitKind.PARAGRAPH, text=f"Source text for {uid}.")
        for uid in ids
    ]


def test_execute_batch_single_unit_uses_single_prompt() -> None:
    llm = _EchoLLM(["translation one"])
    translator = TranslateChunk(llm=llm, retriever=_NoExamplesRetriever())

    outputs = translator.execute_batch(
        _units(["u1"]),
        target_lang="vi",
        source_lang="en",
        analysis=None,
        glossary=[],
    )

    assert len(outputs) == 1
    assert outputs[0].translated.target_text == "translation one"
    user_msg = next(m for m in llm.calls[0] if m.role == "user")
    assert "<<<SRC" not in user_msg.content


def test_execute_batch_splits_envelope_output_in_order() -> None:
    raw = (
        '<<<TGT id="u2">>>\nbeta translation\n'
        '<<<TGT id="u1">>>\nalpha translation\n'
        '<<<TGT id="u3">>>\ngamma translation\n'
    )
    llm = _EchoLLM([raw])
    translator = TranslateChunk(llm=llm, retriever=_NoExamplesRetriever())

    outputs = translator.execute_batch(
        _units(["u1", "u2", "u3"]),
        target_lang="vi",
        source_lang="en",
        analysis=None,
        glossary=[],
    )

    assert [o.translated.id for o in outputs] == ["u1", "u2", "u3"]
    assert outputs[0].translated.target_text == "alpha translation"
    assert outputs[1].translated.target_text == "beta translation"
    assert outputs[2].translated.target_text == "gamma translation"
    assert len(llm.calls) == 1


def test_execute_batch_falls_back_to_singleton_for_missing_ids() -> None:
    batch_raw = '<<<TGT id="u1">>>\nalpha translation\n'
    single_raw = "gamma singleton"
    llm = _EchoLLM([batch_raw, single_raw])
    translator = TranslateChunk(llm=llm, retriever=_NoExamplesRetriever())

    outputs = translator.execute_batch(
        _units(["u1", "u3"]),
        target_lang="vi",
        source_lang="en",
        analysis=None,
        glossary=[],
    )

    assert [o.translated.id for o in outputs] == ["u1", "u3"]
    assert outputs[0].translated.target_text == "alpha translation"
    assert outputs[1].translated.target_text == "gamma singleton"
    assert len(llm.calls) == 2
    fallback_user = next(m for m in llm.calls[1] if m.role == "user")
    assert "<<<SRC" not in fallback_user.content


def test_execute_batch_preserves_inline_flags_per_unit() -> None:
    raw = (
        '<<<TGT id="u1">>>\nalpha <unsure>word</unsure> end\n'
        '<<<TGT id="u2">>>\nbeta <sense>pick|because</sense> end\n'
    )
    llm = _EchoLLM([raw])
    translator = TranslateChunk(llm=llm, retriever=_NoExamplesRetriever())

    outputs = translator.execute_batch(
        _units(["u1", "u2"]),
        target_lang="vi",
        source_lang="en",
        analysis=None,
        glossary=[],
    )

    kinds_u1 = [f.kind for f in outputs[0].flags]
    kinds_u2 = [f.kind for f in outputs[1].flags]
    assert kinds_u1 == [FlagKind.UNSURE]
    assert kinds_u2 == [FlagKind.SENSE]
    assert outputs[1].flags[0].reason == "because"
