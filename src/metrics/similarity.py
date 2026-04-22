"""Pure similarity scorers — two strings in, a float in [0, 1] out.

Used by :mod:`metrics.roundtrip` to quantify drift between a source text
and its back-translation across one or more target languages, but the
scorers are standalone: no dependency on the rag pipeline, translator,
embedder, or vault. Anything that can hand two strings to a function can
score them.

The scorers intentionally live here (not in ``rag``) so the ``kb`` CLI
and the reviewer can import them without loading the translation stack.
See the invariant called out in :mod:`metrics`'s package docstring.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass

Embedder = Callable[[Sequence[str]], Sequence[Sequence[float]]]


@dataclass(slots=True, frozen=True)
class SimilarityScore:
    """One scorer's verdict on a (reference, hypothesis) pair."""

    name: str
    value: float
    detail: str | None = None


def chrf(
    reference: str,
    hypothesis: str,
    *,
    n: int = 6,
    beta: float = 2.0,
) -> SimilarityScore:
    """Character n-gram F-beta (chrF / chrF++ family).

    Default ``n=6, beta=2.0`` matches sacrebleu's chrF2 defaults. Pure
    Python — no sacrebleu dep — because the implementation is 20 lines
    and the scorer is hot enough to want avoiding a heavy import.

    Robust to morphology (Polish inflection, German compounds) and to
    tokenization-free languages (Vietnamese, Chinese) because it works
    on character n-grams rather than word tokens.
    """
    ref = _normalize(reference)
    hyp = _normalize(hypothesis)
    if not ref and not hyp:
        return SimilarityScore(name="chrf", value=1.0)
    if not ref or not hyp:
        return SimilarityScore(name="chrf", value=0.0)

    precisions: list[float] = []
    recalls: list[float] = []
    for order in range(1, n + 1):
        ref_ngrams = _char_ngrams(ref, order)
        hyp_ngrams = _char_ngrams(hyp, order)
        if not ref_ngrams or not hyp_ngrams:
            continue
        overlap = sum((ref_ngrams & hyp_ngrams).values())
        precisions.append(overlap / max(sum(hyp_ngrams.values()), 1))
        recalls.append(overlap / max(sum(ref_ngrams.values()), 1))
    if not precisions:
        return SimilarityScore(name="chrf", value=0.0)

    precision = sum(precisions) / len(precisions)
    recall = sum(recalls) / len(recalls)
    if precision == 0.0 and recall == 0.0:
        return SimilarityScore(name="chrf", value=0.0)
    beta_sq = beta * beta
    f = (1 + beta_sq) * precision * recall / (beta_sq * precision + recall)
    return SimilarityScore(
        name="chrf",
        value=f,
        detail=f"P={precision:.3f} R={recall:.3f} n={n} beta={beta}",
    )


def bleu_lite(
    reference: str,
    hypothesis: str,
    *,
    max_n: int = 4,
) -> SimilarityScore:
    """Corpus-free BLEU on a single pair, with +1 smoothing.

    Simple Papineni-style BLEU: modified n-gram precision (1..``max_n``)
    geometric mean, brevity penalty. Whitespace-tokenized, lowercased.
    Good enough as a cheap lexical baseline for Romance/Germanic target
    languages; use :func:`chrf` for morphologically rich or segmentation-
    hostile languages (pl, vi, zh, ja).
    """
    ref_tokens = _word_tokens(reference)
    hyp_tokens = _word_tokens(hypothesis)
    if not ref_tokens and not hyp_tokens:
        return SimilarityScore(name="bleu", value=1.0)
    if not ref_tokens or not hyp_tokens:
        return SimilarityScore(name="bleu", value=0.0)

    log_precisions: list[float] = []
    for order in range(1, max_n + 1):
        ref_ngrams = _word_ngrams(ref_tokens, order)
        hyp_ngrams = _word_ngrams(hyp_tokens, order)
        overlap = sum((ref_ngrams & hyp_ngrams).values())
        total = sum(hyp_ngrams.values())
        # +1 smoothing keeps zero-match orders from collapsing the product.
        smoothed = (overlap + 1) / (total + 1)
        log_precisions.append(math.log(smoothed))
    geo_mean = math.exp(sum(log_precisions) / max_n)

    ref_len = len(ref_tokens)
    hyp_len = len(hyp_tokens)
    if hyp_len >= ref_len:
        brevity = 1.0
    else:
        brevity = math.exp(1 - ref_len / hyp_len) if hyp_len > 0 else 0.0
    return SimilarityScore(
        name="bleu",
        value=geo_mean * brevity,
        detail=f"bp={brevity:.3f} max_n={max_n}",
    )


def embedding_cosine(
    reference: str,
    hypothesis: str,
    *,
    embedder: Embedder,
) -> SimilarityScore:
    """Cosine similarity of two texts under a user-supplied embedder.

    ``embedder`` takes a list of strings and returns parallel vectors.
    The caller picks the model — LaBSE / multilingual MiniLM for cross-
    lingual work, a monolingual SBERT model for source-vs-back-translation
    scoring (back-translation is in the source language, so monolingual
    is fine). Returns a value in [-1, 1], clamped to [0, 1] by convention
    so it composes with :func:`chrf` / :func:`bleu_lite`.
    """
    if not reference or not hypothesis:
        return SimilarityScore(name="embedding_cosine", value=0.0)
    vectors = embedder([reference, hypothesis])
    if len(vectors) < 2:
        return SimilarityScore(name="embedding_cosine", value=0.0)
    raw = _cosine(list(vectors[0]), list(vectors[1]))
    # Translation similarity is almost always >= 0; negative values are
    # numerical noise for this use case — clamp so downstream averaging
    # isn't skewed by outliers.
    clamped = max(0.0, raw)
    return SimilarityScore(
        name="embedding_cosine",
        value=clamped,
        detail=f"raw={raw:.3f}",
    )


def _normalize(text: str) -> str:
    # NFKC folds compatibility forms (fullwidth CJK, ligatures) so two
    # visually equivalent strings score the same. Whitespace is
    # collapsed so line-break differences don't perturb chrF.
    normalized = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", normalized).strip().lower()


def _char_ngrams(text: str, n: int) -> Counter[str]:
    if len(text) < n:
        return Counter()
    return Counter(text[i : i + n] for i in range(len(text) - n + 1))


def _word_tokens(text: str) -> list[str]:
    return _normalize(text).split()


def _word_ngrams(tokens: Sequence[str], n: int) -> Counter[tuple[str, ...]]:
    if len(tokens) < n:
        return Counter()
    return Counter(tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1))


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
