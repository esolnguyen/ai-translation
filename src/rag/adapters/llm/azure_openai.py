"""Azure OpenAI-backed ``LLMClient``.

Uses the ``openai`` SDK's ``AzureOpenAI`` client. Deployment name, endpoint,
api version and key are read from env by ``from_env()``.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass

from ...use_cases.ports import LLMClient, LLMMessage


@dataclass(slots=True, frozen=True)
class AzureOpenAIConfig:
    endpoint: str
    api_key: str
    deployment: str
    api_version: str


class AzureOpenAIClient(LLMClient):
    """Chat-completions wrapper for an Azure OpenAI deployment."""

    def __init__(self, config: AzureOpenAIConfig) -> None:
        self._config = config
        self._client = self._build_client(config)

    @staticmethod
    def _build_client(config: AzureOpenAIConfig):
        from openai import AzureOpenAI

        return AzureOpenAI(
            azure_endpoint=config.endpoint,
            api_key=config.api_key,
            api_version=config.api_version,
        )

    @classmethod
    def from_env(cls) -> AzureOpenAIClient:
        missing = [
            name
            for name in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT")
            if not os.environ.get(name)
        ]
        if missing:
            raise RuntimeError(f"Azure OpenAI env vars missing: {', '.join(missing)}")
        return cls(
            AzureOpenAIConfig(
                endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
                api_key=os.environ["AZURE_OPENAI_API_KEY"],
                deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
                api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
            )
        )

    def complete(
        self,
        messages: Sequence[LLMMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        response = self._client.chat.completions.create(
            model=self._config.deployment,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""
