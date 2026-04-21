"""Google Gemini-backed ``LLMClient``.

Uses the ``google-genai`` SDK. System messages are folded into the
``system_instruction`` param; user/assistant turns map to Gemini's
``user`` / ``model`` roles.
"""

from __future__ import annotations
import logging
import os
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast
from ...use_cases.ports import LLMClient, LLMMessage

if TYPE_CHECKING:
    from google.genai.types import ContentListUnionDict

logger = logging.getLogger(__name__)
_ROLE_MAP = {"user": "user", "assistant": "model"}


@dataclass(slots=True, frozen=True)
class GeminiConfig:
    api_key: str
    model: str


class GeminiClient(LLMClient):
    """Chat wrapper for Google's Generative AI API."""

    def __init__(self, config: GeminiConfig) -> None:
        self._config = config
        self._client = self._build_client(config)

    @staticmethod
    def _build_client(config: GeminiConfig):
        from google import genai

        return genai.Client(api_key=config.api_key)

    @classmethod
    def from_env(cls) -> GeminiClient:
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY (or GOOGLE_API_KEY) must be set")
        return cls(
            GeminiConfig(
                api_key=api_key,
                model=os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
            )
        )

    def complete(
        self,
        messages: Sequence[LLMMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        from google.genai import types

        system_parts = [m.content for m in messages if m.role == "system"]
        contents: list[types.Content] = [
            types.Content(
                role=_ROLE_MAP[m.role],
                parts=[types.Part.from_text(text=m.content)],
            )
            for m in messages
            if m.role in _ROLE_MAP
        ]
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction="\n\n".join(system_parts) or None,
        )
        logger.info(
            "llm gemini request model=%s messages=%d max_tokens=%s temperature=%s",
            self._config.model,
            len(contents),
            max_tokens,
            temperature,
        )
        t0 = time.monotonic()
        response = self._client.models.generate_content(
            model=self._config.model,
            contents=cast("ContentListUnionDict", contents),
            config=config,
        )
        elapsed = time.monotonic() - t0
        usage = getattr(response, "usage_metadata", None)
        logger.info(
            "llm gemini model=%s elapsed=%.2fs in=%s out=%s",
            self._config.model,
            elapsed,
            getattr(usage, "prompt_token_count", "?"),
            getattr(usage, "candidates_token_count", "?"),
        )
        return response.text or ""
