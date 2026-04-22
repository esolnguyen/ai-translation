"""Default ``MetricProfileRegistry`` + starter profiles.

Rev 3 starter weights for vi per plan §4. Other languages fall back to the
default profile until M5.5 loads per-language cards from ``vault/languages``.

Per-language round-trip scorer picks follow the guidance in the scorer
docstrings: chrF for morphology-heavy targets (pl/de) and tokenization-
hostile ones (vi, zh, ja); BLEU where word-order is rigid (en, Romance);
embedding cosine as the semantic drift signal layered on top when an
embedder is available at runtime. Fallback is the language-agnostic
chrF + BLEU pair — safe but uninformative on the hard languages.
"""

from __future__ import annotations

from .ports import MetricProfile, MetricProfileRegistry, MetricWeights

_DEFAULT_CHECKS: list[str] = [
    "glossary_adherence",
    "placeholder_round_trip",
    "markdown_integrity",
    "tag_balance",
    "length_sanity",
]

_DEFAULT_ROUNDTRIP_SCORERS: list[str] = ["chrf", "bleu"]

# Per-language scorer picks — see module docstring for the rationale.
# "embedding_cosine" is only activated when the caller supplies an embedder
# (see :func:`metrics.roundtrip.scorers_for_profile`), so it is safe to
# include here even when we run without a model loaded.
_ROUNDTRIP_SCORERS_BY_LANG: dict[str, list[str]] = {
    "vi": ["chrf", "embedding_cosine"],
    "pl": ["chrf", "embedding_cosine"],
    "de": ["chrf", "embedding_cosine"],
    "es": ["bleu", "chrf", "embedding_cosine"],
    "fr": ["bleu", "chrf", "embedding_cosine"],
    "it": ["bleu", "chrf", "embedding_cosine"],
    "en": ["bleu", "chrf", "embedding_cosine"],
    "zh": ["chrf", "embedding_cosine"],
    "ja": ["chrf", "embedding_cosine"],
}


def _default_roundtrip_scorers(lang: str) -> list[str]:
    return list(_ROUNDTRIP_SCORERS_BY_LANG.get(lang, _DEFAULT_ROUNDTRIP_SCORERS))


def default_profile(lang: str = "vi") -> MetricProfile:
    return MetricProfile(
        lang=lang,
        weights=MetricWeights(checklist=0.40, similarity=0.30, custom=0.30),
        repair_max_passes=1,
        custom_check_names=list(_DEFAULT_CHECKS),
        roundtrip_scorer_names=_default_roundtrip_scorers(lang),
    )


_STARTER_PROFILES: dict[str, MetricProfile] = {
    "vi": default_profile("vi"),
}


class DefaultMetricProfileRegistry(MetricProfileRegistry):
    def __init__(self, profiles: dict[str, MetricProfile] | None = None) -> None:
        self._profiles: dict[str, MetricProfile] = (
            dict(_STARTER_PROFILES) if profiles is None else dict(profiles)
        )

    def register(self, profile: MetricProfile) -> None:
        self._profiles[profile.lang] = profile

    def get(self, lang: str) -> MetricProfile:
        if lang in self._profiles:
            return self._profiles[lang]
        return default_profile(lang)
