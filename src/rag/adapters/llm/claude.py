"""Claude Agent SDK-backed LLM client — stub.

Wired in when live translation calls are needed (M2+). The Agent SDK dep is
declared in ``pyproject.toml`` under the ``rag`` extras.
"""

from __future__ import annotations

from collections.abc import Sequence

from ...use_cases.ports import LLMClient, LLMMessage


class ClaudeLLMClient(LLMClient):
    def __init__(self, model: str) -> None:
        self._model = model

    @classmethod
    def from_env(cls) -> ClaudeLLMClient:
        raise NotImplementedError("ClaudeLLMClient is not wired up yet")

    def complete(
        self,
        messages: Sequence[LLMMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        raise NotImplementedError
