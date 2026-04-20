"""parse_flags — strip <unsure>/<sense> tags and emit clean-text offsets."""

from __future__ import annotations

from rag.domain import FlagKind
from rag.use_cases.flag_parser import parse_flags


def test_empty_input() -> None:
    clean, flags = parse_flags("")
    assert clean == ""
    assert flags == []


def test_no_flags_passes_through() -> None:
    raw = "The quick brown fox."
    clean, flags = parse_flags(raw)
    assert clean == raw
    assert flags == []


def test_unsure_tag_produces_offsets_in_clean_text() -> None:
    raw = "Deposit the <unsure>bank</unsure> statement tomorrow."
    clean, flags = parse_flags(raw)
    assert clean == "Deposit the bank statement tomorrow."
    assert len(flags) == 1
    (f,) = flags
    assert f.kind is FlagKind.UNSURE
    assert f.text == "bank"
    assert clean[f.start : f.end] == "bank"
    assert f.reason == ""


def test_sense_tag_splits_on_pipe() -> None:
    raw = "Meet at the <sense>bank|river, not financial</sense> tonight."
    clean, flags = parse_flags(raw)
    assert clean == "Meet at the bank tonight."
    assert len(flags) == 1
    (f,) = flags
    assert f.kind is FlagKind.SENSE
    assert f.text == "bank"
    assert f.reason == "river, not financial"
    assert clean[f.start : f.end] == "bank"


def test_multiple_tags_preserve_relative_offsets() -> None:
    raw = (
        "The <unsure>gizmo</unsure> connects to the "
        "<sense>port|maritime pier</sense>."
    )
    clean, flags = parse_flags(raw)
    assert clean == "The gizmo connects to the port."
    assert [f.text for f in flags] == ["gizmo", "port"]
    for f in flags:
        assert clean[f.start : f.end] == f.text


def test_unmatched_tag_left_in_clean_text_no_flag() -> None:
    raw = "Uneven <unsure>start of trouble and no closing tag."
    clean, flags = parse_flags(raw)
    assert clean == raw
    assert flags == []
