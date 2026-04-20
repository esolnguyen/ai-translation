"""Reviewer output value object (Rev 3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ReviewDecision(str, Enum):
    PASS = "pass"
    RETRY = "retry"
    ESCALATE = "escalate"


@dataclass(slots=True)
class ReviewResult:
    """Pure-code reviewer output.

    ``checklist_score`` and ``custom_score`` are pass-rates in ``[0, 1]``;
    ``similarity_score`` is the mean cosine vs retrieved examples (also
    clamped to ``[0, 1]``). ``composite`` is the weighted sum per the
    active :class:`~rag.use_cases.ports.MetricProfile`.
    """

    checklist_score: float
    similarity_score: float
    custom_score: float
    composite: float
    decision: ReviewDecision
    failures: list[str] = field(default_factory=list)
