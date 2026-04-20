"""BackTranslate — optional round-trip QA leg (M8).

Translates a draft's ``target_text`` back to the original source language and,
when an embedder is available, scores the round-trip by cosine similarity
between the source text and the back-translation. The result is informational
only — it is recorded in ``roundtrip.<lang>.json`` and aggregated into the
manifest for QA; it does not drive repair or escalation decisions.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from ..domain import TranslatedUnit
from .ports import Embedder, LLMClient, LLMMessage

_BACKTRANSLATE_SYSTEM = (
    "You are a professional translator performing a round-trip quality check. "
    "Translate the user message from {target_lang} back to {source_lang}. "
    "Render the meaning faithfully, in neutral register, without adding or "
    "omitting information. Return only the translation — no prefix, suffix, "
    "or commentary."
)


@dataclass(slots=True, frozen=True)
class BackTranslateOutput:
    unit_id: str
    source_text: str
    back_text: str
    similarity: float | None
    raw_response: str


class BackTranslate:
    """Translate ``target_text`` back into the source language + score it."""

    def __init__(
        self,
        *,
        llm: LLMClient,
        embedder: Embedder | None = None,
    ) -> None:
        self._llm = llm
        self._embedder = embedder

    def execute(
        self,
        translation: TranslatedUnit,
        *,
        source_lang: str,
    ) -> BackTranslateOutput:
        system = _BACKTRANSLATE_SYSTEM.format(
            source_lang=source_lang,
            target_lang=translation.target_lang,
        )
        messages: Sequence[LLMMessage] = [
            LLMMessage(role="system", content=system),
            LLMMessage(role="user", content=translation.target_text),
        ]
        raw = self._llm.complete(messages, temperature=0.0)
        back_text = raw.strip()
        similarity = self._score_similarity(translation.source_text, back_text)
        return BackTranslateOutput(
            unit_id=translation.id,
            source_text=translation.source_text,
            back_text=back_text,
            similarity=similarity,
            raw_response=raw,
        )

    def _score_similarity(self, source_text: str, back_text: str) -> float | None:
        if self._embedder is None or not back_text:
            return None
        vectors = self._embedder.embed([source_text, back_text])
        return _cosine(vectors[0], vectors[1])


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
