"""Parse ``<unsure>`` / ``<sense>`` spans out of a translator draft.

The translator self-flags ambiguous spans inline:

- ``<unsure>…</unsure>`` — "I am not sure this is right; please verify".
- ``<sense>…|reason</sense>`` — "this word has multiple senses; I picked
  one for the reason that follows the pipe".

This module converts one raw draft into ``(clean_text, flags)`` where
``clean_text`` has all tags removed and each ``TranslationFlag`` carries
character offsets **into that cleaned text** so Repair can substitute
exactly the flagged span.

Pure function — no I/O, no LLM. Kept small and deterministic.
"""

from __future__ import annotations

import re

from ..domain import FlagKind, TranslationFlag

# Tolerant of whitespace inside tags; forbids nested tags (greedy-safe).
_FLAG_RE = re.compile(
    r"<(?P<kind>unsure|sense)>(?P<body>[^<]*)</(?P=kind)>",
    re.DOTALL,
)


def parse_flags(raw: str) -> tuple[str, list[TranslationFlag]]:
    """Strip tags and return ``(clean_text, flags)``.

    Offsets in each flag point into ``clean_text``. Malformed or
    unmatched tags are left untouched in ``clean_text`` and produce no
    flag — Repair will see them as failed gate-checks downstream.
    """

    if not raw:
        return "", []

    out: list[str] = []
    flags: list[TranslationFlag] = []
    cursor = 0
    for match in _FLAG_RE.finditer(raw):
        out.append(raw[cursor : match.start()])
        kind_literal = match.group("kind")
        body = match.group("body")
        text, reason = _split_reason(kind_literal, body)
        start = sum(len(p) for p in out)
        out.append(text)
        end = start + len(text)
        flags.append(
            TranslationFlag(
                kind=FlagKind(kind_literal),
                text=text,
                start=start,
                end=end,
                reason=reason,
            )
        )
        cursor = match.end()
    out.append(raw[cursor:])
    return "".join(out), flags


def _split_reason(kind: str, body: str) -> tuple[str, str]:
    if kind == "sense" and "|" in body:
        text, _, reason = body.partition("|")
        return text.strip(), reason.strip()
    return body, ""
