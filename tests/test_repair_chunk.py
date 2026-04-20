"""RepairChunk — targeted span rewrites + escalation at max passes."""

from __future__ import annotations

from collections.abc import Sequence

from rag.domain import FlagKind, TranslatedUnit, TranslationFlag
from rag.use_cases.ports import LLMClient, LLMMessage
from rag.use_cases.repair_chunk import RepairChunk


class _ScriptedLLM(LLMClient):
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


def _draft(text: str = "Nộp sao kê ngân hàng vào ngày mai.") -> TranslatedUnit:
    return TranslatedUnit(
        id="u1",
        source_text="Deposit the bank statement tomorrow.",
        target_text=text,
        target_lang="vi",
        meta={"flags": []},
    )


def test_noop_when_no_flags_and_no_failures() -> None:
    repairer = RepairChunk(llm=_ScriptedLLM([]), max_passes=1)

    out = repairer.execute(
        _draft(),
        flags=[],
        failures=[],
        source_text="Deposit the bank statement tomorrow.",
        source_lang="en",
        target_lang="vi",
    )

    assert out.report.actions == []
    assert out.report.escalated is False
    assert out.translated.target_text == "Nộp sao kê ngân hàng vào ngày mai."


def test_rewrites_only_flagged_span() -> None:
    draft = _draft("Meet at the bank tonight.")
    flag = TranslationFlag(
        kind=FlagKind.SENSE,
        text="bank",
        start=draft.target_text.index("bank"),
        end=draft.target_text.index("bank") + len("bank"),
        reason="river, not financial",
    )
    llm = _ScriptedLLM(["bờ sông"])
    repairer = RepairChunk(llm=llm, max_passes=1)

    out = repairer.execute(
        draft,
        flags=[flag],
        failures=[],
        source_text="Meet at the bank tonight.",
        source_lang="en",
        target_lang="vi",
    )

    assert out.translated.target_text == "Meet at the bờ sông tonight."
    assert len(out.report.actions) == 1
    action = out.report.actions[0]
    assert action.original == "bank"
    assert action.replacement == "bờ sông"
    assert action.reason == "river, not financial"
    assert out.report.escalated is False


def test_escalation_writes_verbatim_after_max_passes() -> None:
    draft = _draft()
    flag = TranslationFlag(
        kind=FlagKind.UNSURE,
        text="sao kê",
        start=4,
        end=10,
        reason="",
    )
    llm = _ScriptedLLM([])  # Should not be called — escalated immediately.
    repairer = RepairChunk(llm=llm, max_passes=1)

    out = repairer.execute(
        draft,
        flags=[flag],
        failures=[],
        source_text="Deposit the bank statement tomorrow.",
        source_lang="en",
        target_lang="vi",
        pass_count=1,
    )

    assert out.report.escalated is True
    assert out.translated.target_text == draft.target_text
    assert llm.calls == []


def test_multiple_flags_apply_right_to_left_preserving_offsets() -> None:
    draft = _draft("The gizmo connects to the port.")
    flag_a = TranslationFlag(
        kind=FlagKind.UNSURE, text="gizmo", start=4, end=9, reason=""
    )
    flag_b = TranslationFlag(
        kind=FlagKind.SENSE,
        text="port",
        start=26,
        end=30,
        reason="maritime pier",
    )
    llm = _ScriptedLLM(["cảng biển", "bộ phận"])  # flag_b applied first (higher start).
    repairer = RepairChunk(llm=llm, max_passes=1)

    out = repairer.execute(
        draft,
        flags=[flag_a, flag_b],
        failures=[],
        source_text="The gizmo connects to the port.",
        source_lang="en",
        target_lang="vi",
    )

    assert out.translated.target_text == "The bộ phận connects to the cảng biển."
    assert [a.replacement for a in out.report.actions] == ["cảng biển", "bộ phận"]


def test_failures_propagate_when_no_flags() -> None:
    draft = _draft()
    llm = _ScriptedLLM([])
    repairer = RepairChunk(llm=llm, max_passes=1)

    out = repairer.execute(
        draft,
        flags=[],
        failures=["glossary_adherence"],
        source_text="Deposit the bank statement tomorrow.",
        source_lang="en",
        target_lang="vi",
        pass_count=0,
    )

    # No flags → no span rewrites, but it still counts as a repair pass;
    # with no actionable flag the text is unchanged but pass_count advances.
    assert out.report.pass_count == 1
    assert out.report.actions == []
