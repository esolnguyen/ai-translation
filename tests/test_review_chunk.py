"""ReviewChunk — composite score across checklist + similarity + custom."""

from __future__ import annotations

import math

from metrics import (
    DefaultMetricProfileRegistry,
    default_custom_check_registry,
)
from metrics.checks import (
    GlossaryAdherenceCheck,
    LengthSanityCheck,
    MarkdownIntegrityCheck,
    PlaceholderRoundTripCheck,
    TagBalanceCheck,
)
from rag.domain import GlossaryEntry, ReviewDecision
from rag.use_cases.ports import Embedder, MetricProfile, MetricWeights
from rag.use_cases.review_chunk import ReviewChunk, ReviewInputs


class _UnitEmbedder(Embedder):
    """Returns canned cosine values by bucketing text into fixed vectors."""

    def __init__(self, canned: dict[str, list[float]]) -> None:
        self._canned = canned

    @property
    def name(self) -> str:
        return "fake-embedder"

    @property
    def dimension(self) -> int:
        return 3

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._canned.get(t, [1.0, 0.0, 0.0]) for t in texts]


def _universal_checks() -> list:
    return [
        GlossaryAdherenceCheck(),
        PlaceholderRoundTripCheck(),
        MarkdownIntegrityCheck(),
        TagBalanceCheck(),
        LengthSanityCheck(),
    ]


def _profile(weights=None) -> MetricProfile:
    return MetricProfile(
        lang="vi",
        weights=weights or MetricWeights(checklist=0.4, similarity=0.3, custom=0.3),
        repair_max_passes=1,
        custom_check_names=[],
    )


def test_clean_draft_passes_without_embedder() -> None:
    reviewer = ReviewChunk(
        profile=_profile(),
        universal_checks=_universal_checks(),
        custom_registry=default_custom_check_registry(),
        embedder=None,
        pass_threshold=0.75,
    )
    result = reviewer.execute(
        ReviewInputs(
            unit_id="u1",
            draft_text="Chào thế giới.",
            source_text="Hello world.",
            target_lang="vi",
            source_lang="en",
        )
    )
    assert result.decision == ReviewDecision.PASS
    assert result.checklist_score == 1.0
    assert result.similarity_score == 1.0
    assert result.custom_score == 1.0
    assert math.isclose(result.composite, 1.0)


def test_missing_placeholder_fails() -> None:
    reviewer = ReviewChunk(
        profile=_profile(),
        universal_checks=_universal_checks(),
        custom_registry=default_custom_check_registry(),
        embedder=None,
    )
    result = reviewer.execute(
        ReviewInputs(
            unit_id="u1",
            draft_text="Xin chào bạn!",
            source_text="Hello, {name}!",
            target_lang="vi",
            source_lang="en",
        )
    )
    assert result.decision == ReviewDecision.RETRY
    assert "placeholder_round_trip" in result.failures
    assert result.checklist_score < 1.0


def test_missing_glossary_term_fails() -> None:
    reviewer = ReviewChunk(
        profile=_profile(),
        universal_checks=_universal_checks(),
        custom_registry=default_custom_check_registry(),
        embedder=None,
    )
    result = reviewer.execute(
        ReviewInputs(
            unit_id="u1",
            draft_text="Gặp ở bờ sông tối nay.",
            source_text="Meet at the bank tonight.",
            target_lang="vi",
            source_lang="en",
            glossary=[
                GlossaryEntry(
                    source="bank", target="ngân hàng", kind="glossary"
                )
            ],
        )
    )
    assert result.decision == ReviewDecision.RETRY
    assert "glossary_adherence" in result.failures


def test_similarity_contributes_to_composite() -> None:
    # Identical example vectors -> cosine 1.0; mismatched -> lower.
    match_embedder = _UnitEmbedder(
        {
            "Chào thế giới.": [1.0, 0.0, 0.0],
            "Chào thế giới.ex": [1.0, 0.0, 0.0],
        }
    )
    reviewer = ReviewChunk(
        profile=_profile(),
        universal_checks=_universal_checks(),
        custom_registry=default_custom_check_registry(),
        embedder=match_embedder,
    )
    result = reviewer.execute(
        ReviewInputs(
            unit_id="u1",
            draft_text="Chào thế giới.",
            source_text="Hello world.",
            target_lang="vi",
            source_lang="en",
            examples=[{"source": "Hello world.", "target": "Chào thế giới.ex"}],
        )
    )
    assert result.similarity_score == 1.0
    assert result.decision == ReviewDecision.PASS


def test_similarity_orthogonal_vectors_lower_score() -> None:
    orth_embedder = _UnitEmbedder(
        {
            "Chào.": [1.0, 0.0, 0.0],
            "Khác.": [0.0, 1.0, 0.0],
        }
    )
    profile = _profile(
        weights=MetricWeights(checklist=0.0, similarity=1.0, custom=0.0)
    )
    reviewer = ReviewChunk(
        profile=profile,
        universal_checks=_universal_checks(),
        custom_registry=default_custom_check_registry(),
        embedder=orth_embedder,
        pass_threshold=0.5,
    )
    result = reviewer.execute(
        ReviewInputs(
            unit_id="u1",
            draft_text="Chào.",
            source_text="Hi.",
            target_lang="vi",
            source_lang="en",
            examples=[{"source": "Hi.", "target": "Khác."}],
        )
    )
    assert math.isclose(result.similarity_score, 0.0, abs_tol=1e-6)
    # Even without failures, low similarity + threshold → retry.
    assert result.decision == ReviewDecision.RETRY


def test_default_profile_registry_falls_back() -> None:
    reg = DefaultMetricProfileRegistry()
    vi = reg.get("vi")
    pl_default = reg.get("pl")  # not registered — falls back
    assert vi.lang == "vi"
    assert pl_default.lang == "pl"
    assert vi.weights.checklist > 0
