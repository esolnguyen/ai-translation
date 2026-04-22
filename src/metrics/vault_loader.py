"""Vault-backed ``MetricProfileRegistry``.

Reads ``<vault_root>/languages/<lang>.md``, finds the ``## Metric profile``
section, extracts its fenced YAML block, and materializes a
:class:`MetricProfile`. Falls back to :class:`DefaultMetricProfileRegistry`
when the card is missing or malformed.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from .ports import (
    MetricProfile,
    MetricProfileRegistry,
    MetricWeights,
)
from .profile_registry import DefaultMetricProfileRegistry, default_profile

_SECTION_RE = re.compile(
    r"^##\s+Metric profile\s*$(.*?)(?=^##\s|\Z)",
    re.MULTILINE | re.DOTALL,
)
_YAML_FENCE_RE = re.compile(r"```ya?ml\s*$(.*?)^```", re.MULTILINE | re.DOTALL)


class VaultMetricProfileRegistry(MetricProfileRegistry):
    def __init__(
        self,
        vault_root: Path,
        *,
        fallback: MetricProfileRegistry | None = None,
    ) -> None:
        self._languages_dir = vault_root / "languages"
        self._fallback = fallback or DefaultMetricProfileRegistry()
        self._cache: dict[str, MetricProfile] = {}

    def get(self, lang: str) -> MetricProfile:
        if lang in self._cache:
            return self._cache[lang]
        card = self._languages_dir / f"{lang}.md"
        if card.exists():
            profile = _parse_card(lang, card.read_text(encoding="utf-8"))
            if profile is not None:
                self._cache[lang] = profile
                return profile
        profile = self._fallback.get(lang)
        self._cache[lang] = profile
        return profile


def _parse_card(lang: str, body: str) -> MetricProfile | None:
    section_match = _SECTION_RE.search(body)
    if section_match is None:
        return None
    fence_match = _YAML_FENCE_RE.search(section_match.group(1))
    if fence_match is None:
        return None
    try:
        data = yaml.safe_load(fence_match.group(1)) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    return _build_profile(lang, data)


def _build_profile(lang: str, data: dict[str, Any]) -> MetricProfile:
    weights_raw = data.get("weights") or {}
    weights = MetricWeights(
        checklist=_float(weights_raw.get("checklist"), 0.40),
        similarity=_float(weights_raw.get("similarity"), 0.30),
        custom=_float(weights_raw.get("custom"), 0.30),
    )
    repair = data.get("repair") or {}
    max_passes = int(repair.get("max_passes", 1)) if isinstance(repair, dict) else 1
    raw_checks = data.get("custom_checks") or []
    checks = [str(name) for name in raw_checks if isinstance(name, str)]
    if not checks:
        checks = list(default_profile(lang).custom_check_names)
    raw_scorers = data.get("roundtrip_scorers") or []
    scorers = [str(name) for name in raw_scorers if isinstance(name, str)]
    if not scorers:
        scorers = list(default_profile(lang).roundtrip_scorer_names)
    return MetricProfile(
        lang=lang,
        weights=weights,
        repair_max_passes=max(1, max_passes),
        custom_check_names=checks,
        roundtrip_scorer_names=scorers,
    )


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
