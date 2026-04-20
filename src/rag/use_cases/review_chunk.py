"""ReviewChunk — pure-code reviewer (Rev 3).

Combines three zero-LLM signals into a single :class:`ReviewResult`:

- **Checklist**: universal rule-based gates (glossary adherence, placeholder
  round-trip, markdown integrity, tag balance, length sanity).
- **Similarity**: mean cosine between the draft embedding and the retrieved
  example-target embeddings.
- **Custom**: language-specific gates named in the active ``MetricProfile``.

Any failing gate forces a retry regardless of composite score (plan §4).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from ..domain import GlossaryEntry, ReviewDecision, ReviewResult
from .ports import (
    CustomCheck,
    CustomCheckRegistry,
    CustomCheckResult,
    Embedder,
    MetricProfile,
)


@dataclass(slots=True, frozen=True)
class ReviewInputs:
    unit_id: str
    draft_text: str
    source_text: str
    target_lang: str
    source_lang: str
    glossary: list[GlossaryEntry] = field(default_factory=list)
    examples: list[dict[str, Any]] = field(default_factory=list)


class ReviewChunk:
    """Composite reviewer over checklist + similarity + custom checks."""

    def __init__(
        self,
        *,
        profile: MetricProfile,
        universal_checks: Sequence[CustomCheck],
        custom_registry: CustomCheckRegistry,
        embedder: Embedder | None,
        pass_threshold: float = 0.75,
    ) -> None:
        self._profile = profile
        self._universal = list(universal_checks)
        self._custom = custom_registry.resolve(profile.custom_check_names)
        self._embedder = embedder
        self._pass_threshold = pass_threshold

    @property
    def profile(self) -> MetricProfile:
        return self._profile

    def execute(self, inputs: ReviewInputs) -> ReviewResult:
        from ..adapters.metrics.checks import ChunkContext

        ctx = ChunkContext(
            target_lang=inputs.target_lang,
            source_lang=inputs.source_lang,
            glossary=list(inputs.glossary),
        )

        checklist_results = [
            c.run(inputs.draft_text, inputs.source_text, ctx) for c in self._universal
        ]
        custom_results = [
            c.run(inputs.draft_text, inputs.source_text, ctx) for c in self._custom
        ]

        checklist_score = _pass_rate(checklist_results)
        custom_score = _pass_rate(custom_results)
        similarity_score = self._similarity(inputs.draft_text, inputs.examples)

        weights = self._profile.weights
        composite = (
            weights.checklist * checklist_score
            + weights.similarity * similarity_score
            + weights.custom * custom_score
        )

        failures = [
            r.name for r in (*checklist_results, *custom_results) if not r.passed
        ]
        decision = (
            ReviewDecision.PASS
            if not failures and composite >= self._pass_threshold
            else ReviewDecision.RETRY
        )

        return ReviewResult(
            checklist_score=round(checklist_score, 4),
            similarity_score=round(similarity_score, 4),
            custom_score=round(custom_score, 4),
            composite=round(composite, 4),
            decision=decision,
            failures=failures,
        )

    def _similarity(self, draft: str, examples: list[dict[str, Any]]) -> float:
        if not self._embedder or not examples or not draft.strip():
            return 1.0
        targets = [_example_target(ex) for ex in examples]
        targets = [t for t in targets if t]
        if not targets:
            return 1.0
        vectors = self._embedder.embed([draft, *targets])
        draft_vec = vectors[0]
        cosines = [_cosine(draft_vec, v) for v in vectors[1:]]
        if not cosines:
            return 1.0
        mean = sum(cosines) / len(cosines)
        return max(0.0, min(1.0, mean))


def _pass_rate(results: list[CustomCheckResult]) -> float:
    if not results:
        return 1.0
    passed = sum(1 for r in results if r.passed)
    return passed / len(results)


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _example_target(example: dict[str, Any]) -> str:
    val = example.get("target") or ""
    if not val:
        meta = example.get("metadata")
        if isinstance(meta, dict):
            val = meta.get("target") or ""
    return str(val).strip()
