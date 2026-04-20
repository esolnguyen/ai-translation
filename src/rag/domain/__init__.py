"""Domain layer — pure value objects, no I/O, no frameworks.

Importable by every other layer. Depends only on stdlib + ``collections.abc``.
"""

from __future__ import annotations

from .analysis import AnalysisResult
from .flags import FlagKind, TranslationFlag
from .glossary import GlossaryEntry
from .review import ReviewDecision, ReviewResult
from .run import RunConfig, RunPaths
from .units import TranslatedUnit, Unit, UnitKind

__all__ = [
    "AnalysisResult",
    "FlagKind",
    "GlossaryEntry",
    "ReviewDecision",
    "ReviewResult",
    "RunConfig",
    "RunPaths",
    "TranslatedUnit",
    "TranslationFlag",
    "Unit",
    "UnitKind",
]
