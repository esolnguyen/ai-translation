"""RepairChunk — unified repair for self-flagged spans and reviewer failures.

Called once per flagged draft. For every :class:`TranslationFlag` in the
draft, re-prompts the LLM to replace just that span — the rest of the
text is untouched. If ``pass_count >= max_passes`` the chunk is
**escalated**: the verbatim translator draft is returned and the
:class:`RepairReport` records ``escalated=True`` so the pipeline can
flag it in the manifest.

Editor is folded in here (Rev 3): polishing passes on failed chunks are
repair actions, not a separate node.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from ..domain import AnalysisResult, GlossaryEntry, TranslatedUnit, TranslationFlag
from .ports import LLMClient, LLMMessage

_REPAIR_SYSTEM = (
    "You are a translation repair specialist. The user will show you a "
    "translated sentence, highlight one flagged span, and explain why it "
    "was flagged. Return ONLY the corrected text that should replace the "
    "flagged span — no tags, no quotes, no prose."
)


@dataclass(slots=True)
class RepairAction:
    flag_kind: str
    original: str
    replacement: str
    reason: str = ""


@dataclass(slots=True)
class RepairReport:
    unit_id: str
    pass_count: int
    actions: list[RepairAction] = field(default_factory=list)
    escalated: bool = False
    remaining_failures: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RepairOutput:
    translated: TranslatedUnit
    report: RepairReport


class RepairChunk:
    def __init__(self, *, llm: LLMClient, max_passes: int = 1) -> None:
        self._llm = llm
        self._max_passes = max_passes

    def execute(
        self,
        translated: TranslatedUnit,
        *,
        flags: list[TranslationFlag],
        failures: list[str],
        source_text: str,
        source_lang: str,
        target_lang: str,
        analysis: AnalysisResult | None = None,
        glossary: list[GlossaryEntry] | None = None,
        pass_count: int = 0,
    ) -> RepairOutput:
        report = RepairReport(unit_id=translated.id, pass_count=pass_count)
        if not flags and not failures:
            return RepairOutput(translated=translated, report=report)

        if pass_count >= self._max_passes:
            report.escalated = True
            report.remaining_failures = list(failures)
            return RepairOutput(translated=translated, report=report)

        new_text = translated.target_text
        # Apply replacements in reverse offset order so earlier offsets stay valid.
        for flag in sorted(flags, key=lambda f: f.start, reverse=True):
            replacement = self._rewrite_span(
                flag=flag,
                draft=new_text,
                source_text=source_text,
                source_lang=source_lang,
                target_lang=target_lang,
                analysis=analysis,
                glossary=glossary or [],
                failures=failures,
            )
            if replacement is None:
                continue
            new_text = new_text[: flag.start] + replacement + new_text[flag.end :]
            report.actions.append(
                RepairAction(
                    flag_kind=flag.kind.value,
                    original=flag.text,
                    replacement=replacement,
                    reason=flag.reason,
                )
            )

        repaired = TranslatedUnit(
            id=translated.id,
            source_text=translated.source_text,
            target_text=new_text.strip(),
            target_lang=translated.target_lang,
            meta={**translated.meta, "flags": [], "repair_pass": pass_count + 1},
        )
        report.pass_count = pass_count + 1
        return RepairOutput(translated=repaired, report=report)

    def _rewrite_span(
        self,
        *,
        flag: TranslationFlag,
        draft: str,
        source_text: str,
        source_lang: str,
        target_lang: str,
        analysis: AnalysisResult | None,
        glossary: list[GlossaryEntry],
        failures: list[str],
    ) -> str | None:
        context = (
            f"Draft ({target_lang}): {draft}\n"
            f"Source ({source_lang}): {source_text}\n"
            f"Flagged span: '{flag.text}' ({flag.kind.value})"
        )
        if flag.reason:
            context += f"\nFlag reason: {flag.reason}"
        if analysis is not None and analysis.domain:
            context += f"\nDomain: {analysis.domain}"
        if glossary:
            lines = "\n".join(f"- {g.source} → {g.target}" for g in glossary)
            context += f"\nGlossary:\n{lines}"
        if failures:
            context += "\nReviewer failures:\n" + "\n".join(f"- {f}" for f in failures)
        response = self._llm.complete(
            [
                LLMMessage(role="system", content=_REPAIR_SYSTEM),
                LLMMessage(role="user", content=context),
            ],
            temperature=0.0,
        )
        replacement = response.strip()
        return replacement or None


def report_to_dict(report: RepairReport) -> dict:
    return asdict(report)
