"""Universal custom checks — each gate in isolation."""

from __future__ import annotations

from rag.adapters.metrics.checks import (
    ChunkContext,
    GlossaryAdherenceCheck,
    LengthSanityCheck,
    MarkdownIntegrityCheck,
    PlaceholderRoundTripCheck,
    TagBalanceCheck,
)
from rag.domain import GlossaryEntry


def _ctx(**kw) -> ChunkContext:
    return ChunkContext(**kw)


def test_glossary_adherence_passes_when_all_locked_terms_present() -> None:
    check = GlossaryAdherenceCheck()
    ctx = _ctx(
        glossary=[GlossaryEntry(source="bank", target="ngân hàng", kind="glossary")]
    )
    result = check.run(
        draft="Gặp ở ngân hàng tối nay.",
        source="Meet at the bank tonight.",
        context=ctx,
    )
    assert result.passed is True


def test_glossary_adherence_fails_when_term_missing() -> None:
    check = GlossaryAdherenceCheck()
    ctx = _ctx(
        glossary=[GlossaryEntry(source="bank", target="ngân hàng", kind="glossary")]
    )
    result = check.run(
        draft="Gặp ở bờ sông tối nay.",
        source="Meet at the bank tonight.",
        context=ctx,
    )
    assert result.passed is False
    assert "ngân hàng" in (result.detail or "")


def test_glossary_adherence_ignores_entries_not_in_source() -> None:
    check = GlossaryAdherenceCheck()
    ctx = _ctx(
        glossary=[GlossaryEntry(source="airport", target="sân bay", kind="glossary")]
    )
    result = check.run(
        draft="Gặp ở bờ sông.",
        source="Meet at the river.",
        context=ctx,
    )
    assert result.passed is True


def test_placeholder_round_trip_detects_dropped_token() -> None:
    check = PlaceholderRoundTripCheck()
    result = check.run(
        draft="Chào thế giới!",
        source="Hello {name}!",
        context=_ctx(),
    )
    assert result.passed is False
    assert "{name}" in (result.detail or "")


def test_placeholder_round_trip_passes_when_preserved() -> None:
    check = PlaceholderRoundTripCheck()
    result = check.run(
        draft="Xin chào, {name}!",
        source="Hello, {name}!",
        context=_ctx(),
    )
    assert result.passed is True


def test_markdown_integrity_flags_missing_heading() -> None:
    check = MarkdownIntegrityCheck()
    result = check.run(
        draft="Phần giới thiệu",
        source="# Introduction",
        context=_ctx(),
    )
    assert result.passed is False


def test_markdown_integrity_passes_when_structure_matches() -> None:
    check = MarkdownIntegrityCheck()
    result = check.run(
        draft="# Phần giới thiệu\n\n- mục một\n- mục hai",
        source="# Introduction\n\n- item one\n- item two",
        context=_ctx(),
    )
    assert result.passed is True


def test_tag_balance_detects_unclosed_tag() -> None:
    check = TagBalanceCheck()
    result = check.run(
        draft="Xin chào <b>thế giới",
        source="Hello <b>world</b>",
        context=_ctx(),
    )
    assert result.passed is False


def test_tag_balance_passes_on_balanced_tags() -> None:
    check = TagBalanceCheck()
    result = check.run(
        draft="Xin chào <b>thế giới</b>",
        source="Hello <b>world</b>",
        context=_ctx(),
    )
    assert result.passed is True


def test_length_sanity_rejects_empty_draft() -> None:
    check = LengthSanityCheck()
    result = check.run(draft="", source="Meaningful content.", context=_ctx())
    assert result.passed is False


def test_length_sanity_flags_runaway_ratio() -> None:
    check = LengthSanityCheck()
    result = check.run(
        draft="x" * 400,
        source="Hello.",
        context=_ctx(length_ratio_range=(0.3, 3.0)),
    )
    assert result.passed is False


def test_length_sanity_passes_within_range() -> None:
    check = LengthSanityCheck()
    result = check.run(
        draft="Chào thế giới.",
        source="Hello world.",
        context=_ctx(),
    )
    assert result.passed is True
