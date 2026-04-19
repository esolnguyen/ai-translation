"""Domain layer — pure value objects, no I/O, no frameworks.

Importable by every other layer. Depends only on stdlib + ``collections.abc``.
"""

from __future__ import annotations

from .analysis import AnalysisResult
from .glossary import GlossaryEntry
from .review import ReviewResult
from .run import RunConfig, RunPaths
from .units import TranslatedUnit, Unit, UnitKind

__all__ = [
    "AnalysisResult",
    "GlossaryEntry",
    "ReviewResult",
    "RunConfig",
    "RunPaths",
    "TranslatedUnit",
    "Unit",
    "UnitKind",
]
