"""Pure similarity scorers — identity, robustness, and language cues.

Covers the scorers that back :mod:`metrics.roundtrip`. The scorers live
outside the rag pipeline on purpose (so ``kb`` CLI and the reviewer can
import them without loading the translation stack), which makes them
unit-testable with plain strings and no fixtures.
"""

from __future__ import annotations

from collections.abc import Sequence

from metrics.similarity import (
    SimilarityScore,
    bleu_lite,
    chrf,
    embedding_cosine,
)


def test_chrf_identity_returns_one() -> None:
    score = chrf("The quick brown fox.", "The quick brown fox.")
    assert score.name == "chrf"
    assert score.value == 1.0


def test_chrf_is_case_and_whitespace_insensitive() -> None:
    a = chrf("Hello   World", "hello world").value
    b = chrf("hello world", "hello world").value
    assert a == b == 1.0


def test_chrf_handles_empty_strings() -> None:
    assert chrf("", "").value == 1.0
    assert chrf("non-empty", "").value == 0.0
    assert chrf("", "non-empty").value == 0.0


def test_chrf_tolerates_polish_morphology() -> None:
    # "dom" (house) vs "domu" (house, genitive) — word-level BLEU would
    # penalize hard; character n-grams overlap heavily.
    score = chrf("Wracam do dom.", "Wracam do domu.").value
    assert score > 0.7


def test_chrf_works_for_vietnamese_without_tokenization() -> None:
    # Vietnamese has no word-level whitespace the way English does; chrF
    # should still score high for a near-identical sentence.
    score = chrf("Chào thế giới.", "Chào thế giới!").value
    assert score > 0.8


def test_bleu_lite_identity_is_one() -> None:
    score = bleu_lite("the cat sat on the mat", "the cat sat on the mat")
    assert score.name == "bleu"
    assert score.value == 1.0


def test_bleu_lite_brevity_penalty_kicks_in_for_short_hypothesis() -> None:
    full = bleu_lite("the cat sat on the mat", "the cat sat on the mat").value
    short = bleu_lite("the cat sat on the mat", "the cat").value
    assert short < full


def test_bleu_lite_handles_empty_strings() -> None:
    assert bleu_lite("", "").value == 1.0
    assert bleu_lite("hello", "").value == 0.0
    assert bleu_lite("", "hello").value == 0.0


def test_bleu_lite_disjoint_text_is_low_but_nonzero_due_to_smoothing() -> None:
    # +1 smoothing keeps the geometric mean above 0, but the score should
    # still be clearly below an exact match.
    score = bleu_lite("alpha beta gamma delta", "epsilon zeta eta theta").value
    assert 0.0 < score < 0.5


def test_embedding_cosine_identical_vectors_score_one() -> None:
    def embedder(texts: Sequence[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]

    score = embedding_cosine("a", "b", embedder=embedder)
    assert score.name == "embedding_cosine"
    assert score.value == 1.0


def test_embedding_cosine_orthogonal_vectors_score_zero() -> None:
    def embedder(texts: Sequence[str]) -> list[list[float]]:
        return [[1.0, 0.0], [0.0, 1.0]]

    score = embedding_cosine("a", "b", embedder=embedder).value
    assert score == 0.0


def test_embedding_cosine_clamps_negative_values_to_zero() -> None:
    def embedder(texts: Sequence[str]) -> list[list[float]]:
        return [[1.0, 0.0], [-1.0, 0.0]]

    result = embedding_cosine("a", "b", embedder=embedder)
    assert result.value == 0.0
    # The raw negative is still surfaced in detail so callers can debug.
    assert result.detail is not None and "raw=-1.000" in result.detail


def test_embedding_cosine_empty_input_returns_zero_without_calling_embedder() -> None:
    calls: list[Sequence[str]] = []

    def embedder(texts: Sequence[str]) -> list[list[float]]:
        calls.append(texts)
        return [[1.0]] * len(texts)

    assert embedding_cosine("", "hello", embedder=embedder).value == 0.0
    assert embedding_cosine("hello", "", embedder=embedder).value == 0.0
    assert calls == []


def test_similarity_score_is_immutable() -> None:
    score = SimilarityScore(name="chrf", value=0.5)
    try:
        score.value = 0.6  # type: ignore[misc]
    except (AttributeError, TypeError):
        return
    raise AssertionError("SimilarityScore should be frozen")
