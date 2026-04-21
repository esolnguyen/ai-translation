"""Default ``MetricProfileRegistry`` + starter profiles.

Rev 3 starter weights for vi per plan §4. Other languages fall back to the
default profile until M5.5 loads per-language cards from ``vault/languages``.
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


def default_profile(lang: str = "vi") -> MetricProfile:
    return MetricProfile(
        lang=lang,
        weights=MetricWeights(checklist=0.40, similarity=0.30, custom=0.30),
        repair_max_passes=1,
        custom_check_names=list(_DEFAULT_CHECKS),
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
