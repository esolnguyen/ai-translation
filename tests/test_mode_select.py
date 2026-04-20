"""M7 — simple-mode selection helper.

Covers the three explicit/auto branches of ``should_use_simple``:

- ``simple_mode=True``  → always simple
- ``simple_mode=False`` → always full
- ``simple_mode=None``  → simple iff both thresholds are undershot
"""

from __future__ import annotations

from pathlib import Path

from rag.domain import RunConfig, Unit, UnitKind
from rag.use_cases.mode_select import count_words, should_use_simple


def _cfg(**over: object) -> RunConfig:
    base = RunConfig(source_path=Path("x.txt"), target_langs=["vi"])
    for k, v in over.items():
        setattr(base, k, v)
    return base


def _unit(uid: str, text: str) -> Unit:
    return Unit(id=uid, kind=UnitKind.CHUNK, text=text)


def test_count_words_sums_across_units() -> None:
    units = [_unit("u1", "one two three"), _unit("u2", "four five")]
    assert count_words(units) == 5


def test_auto_selects_simple_for_tiny_input() -> None:
    units = [_unit("u1", "Short note with a handful of words.")]
    assert should_use_simple(_cfg(), units) is True


def test_auto_rejects_simple_when_word_count_exceeds_threshold() -> None:
    long_text = " ".join(["word"] * 600)
    units = [_unit("u1", long_text)]
    assert should_use_simple(_cfg(), units) is False


def test_auto_rejects_simple_when_chunk_count_exceeds_threshold() -> None:
    units = [_unit(f"u{i}", "hi") for i in range(4)]
    assert should_use_simple(_cfg(), units) is False


def test_explicit_true_overrides_thresholds() -> None:
    long_text = " ".join(["word"] * 600)
    many_units = [_unit(f"u{i}", long_text) for i in range(10)]
    assert should_use_simple(_cfg(simple_mode=True), many_units) is True


def test_explicit_false_overrides_auto() -> None:
    units = [_unit("u1", "tiny")]
    assert should_use_simple(_cfg(simple_mode=False), units) is False


def test_custom_thresholds_honoured() -> None:
    units = [_unit("u1", "ten words " * 2)]
    cfg = _cfg(simple_word_threshold=3)
    assert should_use_simple(cfg, units) is False
