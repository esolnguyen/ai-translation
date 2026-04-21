"""M5.5 — per-language metric profiles + language-specific custom checks."""

from __future__ import annotations

from pathlib import Path

from metrics import VaultMetricProfileRegistry, default_custom_check_registry
from metrics.checks import ChunkContext
from metrics.lang_checks import (
    AspectConsistencyCheck,
    ClassifierPresenceCheck,
    CompoundNounIntegrityCheck,
    DiacriticPresenceCheck,
    FormalityConsistencyCheck,
)

VAULT_ROOT = Path(__file__).resolve().parent.parent / "vault"


def _ctx(lang: str = "") -> ChunkContext:
    return ChunkContext(target_lang=lang)


def test_vault_registry_loads_vi_profile() -> None:
    reg = VaultMetricProfileRegistry(VAULT_ROOT)
    profile = reg.get("vi")
    assert profile.lang == "vi"
    assert profile.weights.checklist == 0.40
    assert profile.weights.similarity == 0.30
    assert profile.weights.custom == 0.30
    assert profile.repair_max_passes == 1
    assert "classifier_presence" in profile.custom_check_names


def test_vault_registry_loads_de_profile() -> None:
    reg = VaultMetricProfileRegistry(VAULT_ROOT)
    profile = reg.get("de")
    assert profile.weights.checklist == 0.45
    assert profile.weights.similarity == 0.20
    assert profile.weights.custom == 0.35
    assert profile.repair_max_passes == 1
    assert "compound_noun_integrity" in profile.custom_check_names


def test_vault_registry_loads_pl_profile() -> None:
    reg = VaultMetricProfileRegistry(VAULT_ROOT)
    profile = reg.get("pl")
    assert profile.weights.checklist == 0.50
    assert profile.weights.similarity == 0.15
    assert profile.weights.custom == 0.35
    assert profile.repair_max_passes == 2
    assert "diacritic_presence" in profile.custom_check_names
    assert "case_after_negation" in profile.custom_check_names


def test_vault_registry_falls_back_on_missing_card(tmp_path: Path) -> None:
    reg = VaultMetricProfileRegistry(tmp_path)
    profile = reg.get("fr")
    # Default fallback profile for unknown lang.
    assert profile.lang == "fr"


def test_vault_registry_falls_back_on_malformed_yaml(tmp_path: Path) -> None:
    langs = tmp_path / "languages"
    langs.mkdir()
    card = langs / "xx.md"
    card.write_text(
        "## Metric profile\n\n```yaml\nnot: [valid\n```\n",
        encoding="utf-8",
    )
    reg = VaultMetricProfileRegistry(tmp_path)
    profile = reg.get("xx")
    assert profile.lang == "xx"  # fallback default


def test_diacritic_presence_fires_when_stripped() -> None:
    check = DiacriticPresenceCheck()
    stripped = (
        "Sprawdz plyn hamulcowy przed jazda i wymien go jesli to konieczne."
    )
    result = check.run(stripped, "Check brake fluid.", _ctx("pl"))
    assert result.passed is False


def test_diacritic_presence_passes_with_diacritics() -> None:
    check = DiacriticPresenceCheck()
    result = check.run(
        "Sprawdź płyn hamulcowy przed jazdą i wymień go jeśli to konieczne.",
        "Check brake fluid.",
        _ctx("pl"),
    )
    assert result.passed is True


def test_diacritic_presence_skips_short_draft() -> None:
    check = DiacriticPresenceCheck()
    result = check.run("OK.", "OK.", _ctx("pl"))
    assert result.passed is True


def test_formality_consistency_flags_mixed_german() -> None:
    check = FormalityConsistencyCheck()
    result = check.run(
        "Sie müssen dein Fahrzeug prüfen.",
        "You must check your vehicle.",
        _ctx("de"),
    )
    assert result.passed is False


def test_formality_consistency_passes_clean_german() -> None:
    check = FormalityConsistencyCheck()
    result = check.run(
        "Sie müssen Ihr Fahrzeug prüfen.",
        "You must check your vehicle.",
        _ctx("de"),
    )
    assert result.passed is True


def test_formality_consistency_flags_mixed_polish() -> None:
    check = FormalityConsistencyCheck()
    result = check.run(
        "Pan musi sprawdzić twój samochód.",
        "You must check your car.",
        _ctx("pl"),
    )
    assert result.passed is False


def test_compound_noun_integrity_fires_when_split() -> None:
    check = CompoundNounIntegrityCheck()
    result = check.run(
        draft="Prüfen Sie das Brems flüssigkeit.",
        source="Check the Bremsflüssigkeit.",
        context=_ctx("de"),
    )
    assert result.passed is False


def test_compound_noun_integrity_passes_when_preserved() -> None:
    check = CompoundNounIntegrityCheck()
    result = check.run(
        draft="Prüfen Sie die Bremsflüssigkeit.",
        source="Check the Bremsflüssigkeit.",
        context=_ctx("de"),
    )
    assert result.passed is True


def test_classifier_presence_flags_missing_vi_classifier() -> None:
    check = ClassifierPresenceCheck()
    result = check.run(
        draft="Kỹ thuật viên kiểm tra phanh.",
        source="The technician inspects the vehicle.",
        context=_ctx("vi"),
    )
    assert result.passed is False


def test_classifier_presence_passes_with_classifier() -> None:
    check = ClassifierPresenceCheck()
    result = check.run(
        draft="Kỹ thuật viên kiểm tra chiếc xe.",
        source="The technician inspects the vehicle.",
        context=_ctx("vi"),
    )
    assert result.passed is True


def test_aspect_consistency_flags_mixed_polish_markers() -> None:
    check = AspectConsistencyCheck()
    result = check.run(
        draft="System monitoruje ciśnienie. Zainstaluj filtr.",
        source="The system monitors pressure. Install the filter.",
        context=_ctx("pl"),
    )
    assert result.passed is False


def test_default_registry_exposes_language_checks() -> None:
    reg = default_custom_check_registry()
    checks = reg.resolve(
        [
            "diacritic_presence",
            "formality_consistency",
            "classifier_presence",
            "compound_noun_integrity",
            "case_after_negation",
            "aspect_consistency",
        ]
    )
    assert [c.name for c in checks] == [
        "diacritic_presence",
        "formality_consistency",
        "classifier_presence",
        "compound_noun_integrity",
        "case_after_negation",
        "aspect_consistency",
    ]
