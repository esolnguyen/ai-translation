"""Multi-language round-trip driver — translator/back-translator wiring.

The driver itself owns no translation logic; it just composes a user-
supplied translator with a user-supplied scorer suite. These tests pin
that composition: scorer selection, per-leg recording, and the ``ranking``
accessor's behavior when a scorer is absent from some legs.
"""

from __future__ import annotations

from collections.abc import Sequence

from metrics.roundtrip import (
    RoundTripLeg,
    RoundTripReport,
    default_scorers,
    round_trip,
)
from metrics.similarity import SimilarityScore


def _scripted_translator(table: dict[tuple[str, str, str], str]):
    def translate(text: str, src: str, tgt: str) -> str:
        return table[(text, src, tgt)]

    return translate


def test_round_trip_records_forward_and_back_text_per_leg() -> None:
    forward_back = {
        ("Hello world.", "en", "vi"): "Chào thế giới.",
        ("Chào thế giới.", "vi", "en"): "Hello world.",
        ("Hello world.", "en", "pl"): "Witaj świecie.",
        ("Witaj świecie.", "pl", "en"): "Hello world.",
    }
    translator = _scripted_translator(forward_back)

    report = round_trip(
        "Hello world.",
        "en",
        ["vi", "pl"],
        translator=translator,
    )

    assert isinstance(report, RoundTripReport)
    assert [leg.target_lang for leg in report.legs] == ["vi", "pl"]
    vi, pl = report.legs
    assert vi.forward_text == "Chào thế giới."
    assert vi.back_text == "Hello world."
    assert pl.forward_text == "Witaj świecie."
    # chrF + BLEU always included in the default scorer suite.
    assert set(vi.scores) == {"chrf", "bleu"}


def test_round_trip_accepts_separate_back_translator() -> None:
    forward = {("x", "en", "fr"): "X-forward"}
    back = {("X-forward", "fr", "en"): "x-return"}
    forward_calls: list[tuple[str, str, str]] = []
    back_calls: list[tuple[str, str, str]] = []

    def fwd(text: str, src: str, tgt: str) -> str:
        forward_calls.append((text, src, tgt))
        return forward[(text, src, tgt)]

    def bwd(text: str, src: str, tgt: str) -> str:
        back_calls.append((text, src, tgt))
        return back[(text, src, tgt)]

    round_trip("x", "en", ["fr"], translator=fwd, back_translator=bwd)
    assert forward_calls == [("x", "en", "fr")]
    assert back_calls == [("X-forward", "fr", "en")]


def test_default_scorers_excludes_embedding_when_no_embedder() -> None:
    scorers = default_scorers()
    names = {fn("a", "a").name for fn in scorers}
    assert names == {"chrf", "bleu"}


def test_default_scorers_adds_embedding_when_embedder_given() -> None:
    def embedder(texts: Sequence[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    scorers = default_scorers(embedder=embedder)
    names = {fn("a", "b").name for fn in scorers}
    assert names == {"chrf", "bleu", "embedding_cosine"}


def test_ranking_sorts_by_scorer_value_descending() -> None:
    legs = [
        RoundTripLeg(
            target_lang="vi",
            forward_text="",
            back_text="",
            scores={"chrf": SimilarityScore(name="chrf", value=0.4)},
        ),
        RoundTripLeg(
            target_lang="pl",
            forward_text="",
            back_text="",
            scores={"chrf": SimilarityScore(name="chrf", value=0.9)},
        ),
        RoundTripLeg(
            target_lang="de",
            forward_text="",
            back_text="",
            scores={"chrf": SimilarityScore(name="chrf", value=0.7)},
        ),
    ]
    report = RoundTripReport(source_text="", source_lang="en", legs=legs)
    assert report.ranking("chrf") == [("pl", 0.9), ("de", 0.7), ("vi", 0.4)]


def test_ranking_drops_legs_missing_the_requested_scorer() -> None:
    # A missing cosine score must not be treated as 0.0 — the leg is
    # simply absent from the ranking.
    legs = [
        RoundTripLeg(
            target_lang="vi",
            forward_text="",
            back_text="",
            scores={"chrf": SimilarityScore(name="chrf", value=0.4)},
        ),
        RoundTripLeg(
            target_lang="pl",
            forward_text="",
            back_text="",
            scores={
                "chrf": SimilarityScore(name="chrf", value=0.9),
                "embedding_cosine": SimilarityScore(name="embedding_cosine", value=0.85),
            },
        ),
    ]
    report = RoundTripReport(source_text="", source_lang="en", legs=legs)
    assert report.ranking("embedding_cosine") == [("pl", 0.85)]


def test_round_trip_with_empty_target_list_returns_empty_report() -> None:
    def translator(text: str, src: str, tgt: str) -> str:  # pragma: no cover - unreachable
        raise AssertionError("translator should not be called")

    report = round_trip("hello", "en", [], translator=translator)
    assert report.legs == []
    assert report.ranking("chrf") == []


def test_round_trip_custom_scorers_replace_defaults() -> None:
    def constant_scorer(ref: str, hyp: str) -> SimilarityScore:
        return SimilarityScore(name="constant", value=0.42)

    translator = _scripted_translator(
        {
            ("x", "en", "fr"): "y",
            ("y", "fr", "en"): "x",
        }
    )
    report = round_trip(
        "x",
        "en",
        ["fr"],
        translator=translator,
        scorers=[constant_scorer],
    )
    (leg,) = report.legs
    assert set(leg.scores) == {"constant"}
    assert leg.score("constant") == 0.42
    assert leg.score("chrf") is None
