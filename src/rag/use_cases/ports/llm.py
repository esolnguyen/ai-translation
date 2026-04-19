"""LLMClient port — single abstraction for every model call."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal


type Role = Literal["system", "user", "assistant"]


@dataclass(slots=True, frozen=True)
class LLMMessage:
    role: Role
    content: str


class LLMClient(ABC):
    """Turn a list of messages into an assistant response.

    Concrete adapters wrap Claude, OpenAI, a local vLLM, or a test double.
    The use-case layer depends only on this shape.
    """

    @abstractmethod
    def complete(
        self,
        messages: Sequence[LLMMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        """Return the assistant text for ``messages``."""
