"""Per-language round-trip scorer selection.

Covers the wiring between ``MetricProfile.roundtrip_scorer_names`` (loaded
from the vault language cards) and the concrete scorer callables the
driver runs. The scorer picks are language-specific because no single
metric wins across morphology / tokenization regimes — see the rationale
baked into each language card.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from metrics import (
    MetricProfile,
    MetricWeights,
    VaultMetricProfileRegistry,
    default_profile,
    resolve_scorers,
    scorers_for_profile,
)

VAULT_ROOT = Path(__file__).resolve().parent.parent / "vault"


def _empty_embedder(texts: Sequence[str]) -> list[list[float]]:
    return [[1.0, 0.0, 0.0] for _ in texts]


def test_default_profile_for_vi_picks_chrf_plus_cosine() -> None:
    profile = default_profile("vi")
    assert profile.roundtrip_scorer_names == ["chrf", "embedding_cosine"]


def test_default_profile_for_pl_picks_chrf_plus_cosine() -> None:
    profile = default_profile("pl")
    assert profile.roundtrip_scorer_names == ["chrf", "embedding_cosine"]


def test_default_profile_for_de_picks_chrf_plus_cosine() -> None:
    profile = default_profile("de")
    assert profile.roundtrip_scorer_names == ["chrf", "embedding_cosine"]


def test_default_profile_for_es_includes_bleu_because_word_order_is_rigid() -> None:
    profile = default_profile("es")
    assert profile.roundtrip_scorer_names == ["bleu", "chrf", "embedding_cosine"]


def test_default_profile_for_unknown_language_falls_back_to_chrf_bleu() -> None:
    profile = default_profile("xx")
    assert profile.roundtrip_scorer_names == ["chrf", "bleu"]


def test_vault_loader_reads_roundtrip_scorers_from_vi_card() -> None:
    reg = VaultMetricProfileRegistry(VAULT_ROOT)
    profile = reg.get("vi")
    assert profile.roundtrip_scorer_names == ["chrf", "embedding_cosine"]


def test_vault_loader_reads_roundtrip_scorers_from_de_card() -> None:
    reg = VaultMetricProfileRegistry(VAULT_ROOT)
    profile = reg.get("de")
    assert profile.roundtrip_scorer_names == ["chrf", "embedding_cosine"]


def test_vault_loader_reads_roundtrip_scorers_from_pl_card() -> None:
    reg = VaultMetricProfileRegistry(VAULT_ROOT)
    profile = reg.get("pl")
    assert profile.roundtrip_scorer_names == ["chrf", "embedding_cosine"]


def test_vault_loader_reads_roundtrip_scorers_from_es_card() -> None:
    reg = VaultMetricProfileRegistry(VAULT_ROOT)
    profile = reg.get("es")
    assert profile.roundtrip_scorer_names == ["bleu", "chrf", "embedding_cosine"]


def test_vault_loader_falls_back_when_key_missing(tmp_path: Path) -> None:
    langs = tmp_path / "languages"
    langs.mkdir()
    card = langs / "nl.md"
    card.write_text(
        """## Metric profile

```yaml
weights:
  checklist: 0.5
  similarity: 0.3
  custom: 0.2
custom_checks:
  - glossary_adherence
```
""",
        encoding="utf-8",
    )
    reg = VaultMetricProfileRegistry(tmp_path)
    profile = reg.get("nl")
    # nl isn't in the hardcoded table either; falls through to the
    # language-agnostic default.
    assert profile.roundtrip_scorer_names == ["chrf", "bleu"]


def test_resolve_scorers_drops_cosine_when_no_embedder() -> None:
    resolved = resolve_scorers(["chrf", "embedding_cosine", "bleu"])
    names = {fn("a", "a").name for fn in resolved}
    assert names == {"chrf", "bleu"}


def test_resolve_scorers_includes_cosine_when_embedder_supplied() -> None:
    resolved = resolve_scorers(
        ["chrf", "embedding_cosine"], embedder=_empty_embedder
    )
    names = {fn("a", "b").name for fn in resolved}
    assert names == {"chrf", "embedding_cosine"}


def test_resolve_scorers_silently_drops_unknown_names() -> None:
    resolved = resolve_scorers(["chrf", "labse_v2"])
    names = {fn("a", "a").name for fn in resolved}
    assert names == {"chrf"}


def test_resolve_scorers_strict_raises_on_unknown_name() -> None:
    with pytest.raises(ValueError, match="unknown roundtrip scorer"):
        resolve_scorers(["chrf", "labse_v2"], strict=True)


def test_resolve_scorers_strict_raises_when_cosine_missing_embedder() -> None:
    with pytest.raises(ValueError, match="no embedder supplied"):
        resolve_scorers(["embedding_cosine"], strict=True)


def test_resolve_scorers_ignores_case_and_whitespace() -> None:
    resolved = resolve_scorers(["  CHRF  ", "BLEU"])
    names = {fn("a", "a").name for fn in resolved}
    assert names == {"chrf", "bleu"}


def test_scorers_for_profile_uses_profile_names() -> None:
    profile = MetricProfile(
        lang="pl",
        weights=MetricWeights(checklist=0.5, similarity=0.15, custom=0.35),
        roundtrip_scorer_names=["chrf", "bleu"],
    )
    resolved = scorers_for_profile(profile)
    names = {fn("a", "a").name for fn in resolved}
    assert names == {"chrf", "bleu"}


def test_scorers_for_profile_falls_back_when_names_empty() -> None:
    # A legacy profile without roundtrip_scorer_names should still yield a
    # usable suite — otherwise any vault card predating this field would
    # hand the driver an empty list.
    profile = MetricProfile(
        lang="xx",
        weights=MetricWeights(checklist=0.5, similarity=0.3, custom=0.2),
        roundtrip_scorer_names=[],
    )
    resolved = scorers_for_profile(profile)
    names = {fn("a", "a").name for fn in resolved}
    assert names == {"chrf", "bleu"}


def test_scorers_for_profile_honors_embedder() -> None:
    profile = default_profile("vi")  # chrf + embedding_cosine
    resolved = scorers_for_profile(profile, embedder=_empty_embedder)
    names = {fn("a", "b").name for fn in resolved}
    assert names == {"chrf", "embedding_cosine"}
