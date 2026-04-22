"""Multi-language round-trip driver.

Given a source text and a list of target languages, translate to each
target, translate each back to the source language, and score the drift
between the original source and every back-translation. Useful as an
informational QA signal across languages — which target leg degraded
meaning most, and on which scorer.

The translator and back-translator are injected as callables so this
module stays free of rag-pipeline imports — the same invariant the other
files in :mod:`metrics` already honor. Callers wire in concrete adapters
(e.g. ``rag.use_cases.BackTranslate`` wrapped as a callable) at the seam.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from .similarity import Embedder, SimilarityScore, bleu_lite, chrf, embedding_cosine

Translator = Callable[[str, str, str], str]
"""``(text, source_lang, target_lang) -> translated_text``."""

Scorer = Callable[[str, str], SimilarityScore]
"""``(reference, hypothesis) -> SimilarityScore``."""


@dataclass(slots=True, frozen=True)
class RoundTripLeg:
    """Result for one source → target → source' round-trip."""

    target_lang: str
    forward_text: str
    back_text: str
    scores: dict[str, SimilarityScore]

    def score(self, name: str) -> float | None:
        """Return the value of the named scorer, or ``None`` if absent."""
        found = self.scores.get(name)
        return found.value if found else None


@dataclass(slots=True, frozen=True)
class RoundTripReport:
    """Full multi-language round-trip verdict for one source."""

    source_text: str
    source_lang: str
    legs: list[RoundTripLeg] = field(default_factory=list)

    def ranking(self, scorer: str) -> list[tuple[str, float]]:
        """Languages ranked by the given scorer, best first.

        Legs missing the scorer are dropped rather than sorted to 0.0 —
        a missing cosine score (no embedder) is not the same signal as
        a 0.0 score (embedder ran, found no overlap).
        """
        scored = [
            (leg.target_lang, leg.score(scorer))
            for leg in self.legs
            if leg.score(scorer) is not None
        ]
        return sorted(
            ((lang, value) for lang, value in scored if value is not None),
            key=lambda pair: pair[1],
            reverse=True,
        )


def default_scorers(embedder: Embedder | None = None) -> list[Scorer]:
    """Assemble the default scorer suite.

    chrF + BLEU always included. The embedding cosine scorer is added
    only when an ``embedder`` is provided — it's the semantic signal,
    but LaBSE / multilingual SBERT can be too heavy to load for quick
    CLI runs, so we keep it opt-in.
    """
    scorers: list[Scorer] = [chrf, bleu_lite]
    if embedder is not None:
        scorers.append(lambda ref, hyp: embedding_cosine(ref, hyp, embedder=embedder))
    return scorers


def round_trip(
    source_text: str,
    source_lang: str,
    target_langs: Iterable[str],
    *,
    translator: Translator,
    back_translator: Translator | None = None,
    scorers: Sequence[Scorer] | None = None,
) -> RoundTripReport:
    """Drive source → {targets} → source' and score each round-trip.

    ``back_translator`` defaults to ``translator`` — callers that want a
    different provider for the return leg (common: use a strong model
    for forward translation, a neutral one for back-translation to
    avoid the "same model remembers its own wording" bias) pass both.

    ``scorers`` defaults to chrF + BLEU (no embedder) via
    :func:`default_scorers`. Pass in an embedder-aware scorer when you
    want the semantic signal.
    """
    back = back_translator or translator
    run_scorers = list(scorers) if scorers is not None else default_scorers()
    legs: list[RoundTripLeg] = []
    for target in target_langs:
        forward = translator(source_text, source_lang, target)
        back_text = back(forward, target, source_lang)
        scores = {
            score.name: score for score in (fn(source_text, back_text) for fn in run_scorers)
        }
        legs.append(
            RoundTripLeg(
                target_lang=target,
                forward_text=forward,
                back_text=back_text,
                scores=scores,
            )
        )
    return RoundTripReport(
        source_text=source_text,
        source_lang=source_lang,
        legs=legs,
    )
