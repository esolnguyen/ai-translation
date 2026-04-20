"""Mode selection — decide whether a run should use the simple short-circuit.

The simple path skips Analyzer, ResolveTerms, Glossary, Repair, and Reviewer.
It is intended for tiny inputs where the overhead of the full pipeline (six
LLM-heavy nodes) would dominate the cost of translating a handful of words.

Selection rule:
- explicit ``config.simple_mode=True``  → simple
- explicit ``config.simple_mode=False`` → full
- ``None`` (auto)                       → simple iff below both thresholds
"""

from __future__ import annotations
from collections.abc import Iterable
from ..domain import RunConfig, Unit


def count_words(units: Iterable[Unit]) -> int:
    return sum(len(u.text.split()) for u in units)


def should_use_simple(config: RunConfig, units: list[Unit]) -> bool:
    if config.simple_mode is True:
        return True
    if config.simple_mode is False:
        return False
    words = count_words(units)
    return (
        words < config.simple_word_threshold
        and len(units) < config.simple_chunk_threshold
    )
