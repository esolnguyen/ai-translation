"""Reviewer output value object."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ReviewDecision(str, Enum):
    PASS = "pass"
    RETRY = "retry"
    ESCALATE = "escalate"


@dataclass(slots=True)
class ReviewResult:
    """Reviewer output — composite score + routing decision."""

    ground_score: float
    example_score: float
    checklist_score: float
    composite: float
    decision: ReviewDecision
    failures: list[str] = field(default_factory=list)
    retry_focus: str | None = None
