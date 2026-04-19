"""Null LLM — returns an empty string. Used in dry-run and tests."""

from __future__ import annotations

from collections.abc import Sequence

from ...use_cases.ports import LLMClient, LLMMessage


class NullLLMClient(LLMClient):
    """No-op client; valid wherever the graph must walk without real model calls."""

    def complete(
        self,
        messages: Sequence[LLMMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        return ""
