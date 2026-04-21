"""Universal custom checks — pure functions wrapped as :class:`CustomCheck`.

These five gates apply to every target language. Language-specific gates
(e.g. Polish ``case_after_negation``) register alongside these in the
:class:`CustomCheckRegistry` and layer on top per the profile.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from .ports import CustomCheck, CustomCheckResult


class GlossaryEntryLike(Protocol):
    """Structural type for glossary entries passed to checks.

    Matches ``rag.domain.GlossaryEntry`` but keeps ``metrics`` free of any
    runtime dependency on the RAG package — so the CLI can import
    ``metrics`` without loading the translation pipeline.
    """

    source: str
    target: str


@dataclass(slots=True)
class ChunkContext:
    """Structured context passed to every custom check."""

    target_lang: str = ""
    source_lang: str = ""
    glossary: list[GlossaryEntryLike] = field(default_factory=list)
    length_ratio_range: tuple[float, float] = (0.3, 3.0)


_PLACEHOLDER_PATTERNS = (
    re.compile(r"\{[A-Za-z0-9_.]+\}"),  # {name} / {user.id}
    re.compile(r"%[sdif]"),  # %s %d %i %f
    re.compile(r"%\([A-Za-z0-9_]+\)[sdif]"),  # %(name)s
    re.compile(r"\$\{[A-Za-z0-9_.]+\}"),  # ${foo}
)

_FENCE_RE = re.compile(r"^```", re.MULTILINE)
_HEADING_RE = re.compile(r"^(#{1,6})\s", re.MULTILINE)
_LIST_RE = re.compile(r"^[ \t]*([-*+]|\d+\.)\s", re.MULTILINE)
_TAG_RE = re.compile(r"<(/?)([A-Za-z][A-Za-z0-9_-]*)(\s[^>]*)?>")


class GlossaryAdherenceCheck(CustomCheck):
    name = "glossary_adherence"

    def run(self, draft: str, source: str, context: Any) -> CustomCheckResult:
        ctx = _require_context(context)
        missing: list[str] = []
        source_lower = source.lower()
        for entry in ctx.glossary:
            if not entry.source or not entry.target:
                continue
            if entry.source.lower() not in source_lower:
                continue
            if entry.target not in draft:
                missing.append(f"{entry.source} → {entry.target}")
        if missing:
            return CustomCheckResult(
                name=self.name,
                passed=False,
                detail="missing: " + "; ".join(missing),
            )
        return CustomCheckResult(name=self.name, passed=True)


class PlaceholderRoundTripCheck(CustomCheck):
    name = "placeholder_round_trip"

    def run(self, draft: str, source: str, context: Any) -> CustomCheckResult:
        source_tokens = _placeholders(source)
        draft_tokens = _placeholders(draft)
        if source_tokens == draft_tokens:
            return CustomCheckResult(name=self.name, passed=True)
        dropped = sorted(source_tokens - draft_tokens)
        added = sorted(draft_tokens - source_tokens)
        parts: list[str] = []
        if dropped:
            parts.append("dropped: " + ", ".join(dropped))
        if added:
            parts.append("added: " + ", ".join(added))
        return CustomCheckResult(name=self.name, passed=False, detail="; ".join(parts))


class MarkdownIntegrityCheck(CustomCheck):
    name = "markdown_integrity"

    def run(self, draft: str, source: str, context: Any) -> CustomCheckResult:
        src_fences = len(_FENCE_RE.findall(source))
        dft_fences = len(_FENCE_RE.findall(draft))
        src_headings = len(_HEADING_RE.findall(source))
        dft_headings = len(_HEADING_RE.findall(draft))
        src_lists = len(_LIST_RE.findall(source))
        dft_lists = len(_LIST_RE.findall(draft))
        mismatches: list[str] = []
        if src_fences != dft_fences:
            mismatches.append(f"fences {src_fences}→{dft_fences}")
        if src_headings != dft_headings:
            mismatches.append(f"headings {src_headings}→{dft_headings}")
        if src_lists != dft_lists:
            mismatches.append(f"list_items {src_lists}→{dft_lists}")
        if mismatches:
            return CustomCheckResult(
                name=self.name, passed=False, detail="; ".join(mismatches)
            )
        return CustomCheckResult(name=self.name, passed=True)


class TagBalanceCheck(CustomCheck):
    name = "tag_balance"

    def run(self, draft: str, source: str, context: Any) -> CustomCheckResult:
        stack: list[str] = []
        for match in _TAG_RE.finditer(draft):
            closing, name, _attrs = match.group(1), match.group(2), match.group(3)
            if closing:
                if not stack or stack[-1] != name:
                    return CustomCheckResult(
                        name=self.name,
                        passed=False,
                        detail=f"unbalanced </{name}>",
                    )
                stack.pop()
            else:
                stack.append(name)
        if stack:
            return CustomCheckResult(
                name=self.name, passed=False, detail=f"unclosed <{stack[-1]}>"
            )
        return CustomCheckResult(name=self.name, passed=True)


class LengthSanityCheck(CustomCheck):
    name = "length_sanity"

    def run(self, draft: str, source: str, context: Any) -> CustomCheckResult:
        src_len = len(source.strip())
        dft_len = len(draft.strip())
        if src_len == 0:
            if dft_len == 0:
                return CustomCheckResult(name=self.name, passed=True)
            return CustomCheckResult(
                name=self.name, passed=False, detail="empty source, non-empty draft"
            )
        if dft_len == 0:
            return CustomCheckResult(name=self.name, passed=False, detail="empty draft")
        ctx = _require_context(context)
        low, high = ctx.length_ratio_range
        ratio = dft_len / src_len
        if low <= ratio <= high:
            return CustomCheckResult(name=self.name, passed=True)
        return CustomCheckResult(
            name=self.name,
            passed=False,
            detail=f"ratio {ratio:.2f} outside [{low:.2f}, {high:.2f}]",
        )


def _placeholders(text: str) -> set[str]:
    tokens: set[str] = set()
    for pattern in _PLACEHOLDER_PATTERNS:
        tokens.update(pattern.findall(text))
    return tokens


def _require_context(context: Any) -> ChunkContext:
    if isinstance(context, ChunkContext):
        return context
    return ChunkContext()
