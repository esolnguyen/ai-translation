"""Language-specific custom checks — pure functions, per plan §4.

Each check targets a single language's known failure mode. The checks are
dispatched by name via :class:`CustomCheckRegistry`; a profile lists the
names it wants in its ``custom_checks`` section (vault language card).

Checks are light-touch heuristics, not linguistic parsers — false positives
are tolerable, false negatives on obvious regressions are not.
"""

from __future__ import annotations

import re
from typing import Any

from .ports import CustomCheck, CustomCheckResult

_POLISH_DIACRITICS = set("ąęćłńóśźżĄĘĆŁŃÓŚŹŻ")
_DE_FORMAL_RE = re.compile(r"\b(Sie|Ihnen|Ihre?m?s?|Ihr)\b")
_DE_INFORMAL_RE = re.compile(r"\b(du|dich|dir|dein[ea-z]*|euch|euer)\b", re.IGNORECASE)
_PL_FORMAL_RE = re.compile(r"\b(Pan|Pani|Państwo|Pana|Pani[ae]|Panu)\b")
_PL_INFORMAL_RE = re.compile(
    r"\b(ty|cię|tobie|twój|twoja|twoje|wy|wam|was)\b", re.IGNORECASE
)

_VI_CLASSIFIER_WORDS = (
    "chiếc",
    "cái",
    "bộ",
    "hệ thống",
    "thiết bị",
    "con",
)
_VI_CLASSIFIER_TRIGGERS = (
    "device",
    "vehicle",
    "system",
    "machine",
    "tool",
    "apparatus",
    "car",
    "kit",
)

_DE_COMPOUND_TRIGGERS = (
    "Bremsflüssigkeit",
    "Reifendruckkontrollsystem",
    "Bremsbelag",
    "Bremsscheibe",
    "Motorhaube",
    "Bordcomputer",
    "Servolenkung",
)

_PL_NEGATION_RE = re.compile(
    r"\bnie\s+(\w+)\s+(\w+)",
    re.IGNORECASE,
)

_PL_ASPECT_IMPERFECTIVE_HINTS = (
    "monitoruje",
    "kontroluje",
    "sprawdza",
    "obserwuje",
)
_PL_ASPECT_PERFECTIVE_HINTS = (
    "zainstaluj",
    "wymień",
    "sprawdź",
    "usuń",
)


class DiacriticPresenceCheck(CustomCheck):
    """Every non-trivial Polish draft should carry at least one diacritic."""

    name = "diacritic_presence"

    def run(self, draft: str, source: str, context: Any) -> CustomCheckResult:
        stripped = draft.strip()
        if len(stripped) < 20:
            return CustomCheckResult(name=self.name, passed=True)
        if any(ch in _POLISH_DIACRITICS for ch in stripped):
            return CustomCheckResult(name=self.name, passed=True)
        return CustomCheckResult(
            name=self.name,
            passed=False,
            detail="no Polish diacritics in non-trivial draft",
        )


class FormalityConsistencyCheck(CustomCheck):
    """Draft shouldn't mix formal + informal second-person forms."""

    name = "formality_consistency"

    def run(self, draft: str, source: str, context: Any) -> CustomCheckResult:
        from .checks import ChunkContext  # local import avoids circular

        lang = ""
        if isinstance(context, ChunkContext):
            lang = context.target_lang
        if lang == "de":
            formal = bool(_DE_FORMAL_RE.search(draft))
            informal = bool(_DE_INFORMAL_RE.search(draft))
        elif lang == "pl":
            formal = bool(_PL_FORMAL_RE.search(draft))
            informal = bool(_PL_INFORMAL_RE.search(draft))
        else:
            return CustomCheckResult(name=self.name, passed=True)
        if formal and informal:
            return CustomCheckResult(
                name=self.name,
                passed=False,
                detail=f"{lang}: mixed formal/informal second-person",
            )
        return CustomCheckResult(name=self.name, passed=True)


class ClassifierPresenceCheck(CustomCheck):
    """Vietnamese drafts should use a classifier when the source names a countable noun."""

    name = "classifier_presence"

    def run(self, draft: str, source: str, context: Any) -> CustomCheckResult:
        from .checks import ChunkContext

        lang = ""
        if isinstance(context, ChunkContext):
            lang = context.target_lang
        if lang != "vi":
            return CustomCheckResult(name=self.name, passed=True)
        source_lower = source.lower()
        needs_classifier = any(w in source_lower for w in _VI_CLASSIFIER_TRIGGERS)
        if not needs_classifier:
            return CustomCheckResult(name=self.name, passed=True)
        if any(c in draft.lower() for c in _VI_CLASSIFIER_WORDS):
            return CustomCheckResult(name=self.name, passed=True)
        return CustomCheckResult(
            name=self.name,
            passed=False,
            detail="vi: countable-noun draft lacks a classifier",
        )


class CompoundNounIntegrityCheck(CustomCheck):
    """German compound nouns appearing in source must not be split in draft."""

    name = "compound_noun_integrity"

    def run(self, draft: str, source: str, context: Any) -> CustomCheckResult:
        from .checks import ChunkContext

        lang = ""
        if isinstance(context, ChunkContext):
            lang = context.target_lang
        if lang != "de":
            return CustomCheckResult(name=self.name, passed=True)
        missing: list[str] = []
        for compound in _DE_COMPOUND_TRIGGERS:
            if compound in source and compound not in draft:
                missing.append(compound)
        if missing:
            return CustomCheckResult(
                name=self.name,
                passed=False,
                detail="split or missing: " + ", ".join(missing),
            )
        return CustomCheckResult(name=self.name, passed=True)


class CaseAfterNegationCheck(CustomCheck):
    """Light heuristic: flag obvious accusative forms after Polish ``nie``."""

    name = "case_after_negation"

    _ACCUSATIVE_HINTS = ("książkę", "samochód", "filtr", "olej", "płyn")

    def run(self, draft: str, source: str, context: Any) -> CustomCheckResult:
        from .checks import ChunkContext

        lang = ""
        if isinstance(context, ChunkContext):
            lang = context.target_lang
        if lang != "pl":
            return CustomCheckResult(name=self.name, passed=True)
        hits: list[str] = []
        for match in _PL_NEGATION_RE.finditer(draft):
            obj_word = match.group(2).lower()
            if obj_word in self._ACCUSATIVE_HINTS:
                hits.append(match.group(0))
        if hits:
            return CustomCheckResult(
                name=self.name,
                passed=False,
                detail="accusative after negation: " + ", ".join(hits),
            )
        return CustomCheckResult(name=self.name, passed=True)


class AspectConsistencyCheck(CustomCheck):
    """Light heuristic: flag when imperfective + perfective markers coexist."""

    name = "aspect_consistency"

    def run(self, draft: str, source: str, context: Any) -> CustomCheckResult:
        from .checks import ChunkContext

        lang = ""
        if isinstance(context, ChunkContext):
            lang = context.target_lang
        if lang != "pl":
            return CustomCheckResult(name=self.name, passed=True)
        lower = draft.lower()
        has_imp = any(h in lower for h in _PL_ASPECT_IMPERFECTIVE_HINTS)
        has_perf = any(h in lower for h in _PL_ASPECT_PERFECTIVE_HINTS)
        if has_imp and has_perf:
            return CustomCheckResult(
                name=self.name,
                passed=False,
                detail="pl: mixed imperfective + perfective markers",
            )
        return CustomCheckResult(name=self.name, passed=True)
