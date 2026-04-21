"""Azure OpenAI-backed ``LLMClient``.

Uses the ``openai`` SDK's ``AzureOpenAI`` client. Deployment name, endpoint,
api version and key are read from env by ``from_env()``.
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
    from openai.types.chat import ChatCompletionMessageParam
    from openai.types.responses import ResponseInputParam

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class AzureOpenAIConfig:
    endpoint: str
    api_key: str
    deployment: str
    api_version: str
    base_url: str | None = None  # set → plain OpenAI client (Foundry v1 mode)


class AzureOpenAIClient(LLMClient):
    """Chat-completions wrapper for an Azure OpenAI deployment."""

    def __init__(self, config: AzureOpenAIConfig) -> None:
        self._config = config
        self._client = self._build_client(config)

    @staticmethod
    def _build_client(config: AzureOpenAIConfig):
        if config.base_url:
            from openai import OpenAI

            return OpenAI(base_url=config.base_url, api_key=config.api_key)
        from openai import AzureOpenAI

        return AzureOpenAI(
            azure_endpoint=config.endpoint,
            api_key=config.api_key,
            api_version=config.api_version,
        )

    @classmethod
    def from_env(cls) -> AzureOpenAIClient:
        base_url = os.environ.get("AZURE_OPENAI_BASE_URL")
        required = ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT") if base_url else (
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_API_KEY",
            "AZURE_OPENAI_DEPLOYMENT",
        )
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise RuntimeError(f"Azure OpenAI env vars missing: {', '.join(missing)}")
        return cls(
            AzureOpenAIConfig(
                endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT", ""),
                api_key=os.environ["AZURE_OPENAI_API_KEY"],
                deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
                api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
                base_url=base_url,
            )
        )

    def complete(
        self,
        messages: Sequence[LLMMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        if self._is_reasoning_model(self._config.deployment):
            return self._complete_responses(messages, max_tokens=max_tokens)
        return self._complete_chat(
            messages, temperature=temperature, max_tokens=max_tokens
        )

    def _complete_chat(
        self,
        messages: Sequence[LLMMessage],
        *,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        payload = cast(
            "list[ChatCompletionMessageParam]",
            [{"role": m.role, "content": m.content} for m in messages],
        )
        logger.info(
            "llm chat request deployment=%s messages=%d max_tokens=%s temperature=%s",
            self._config.deployment,
            len(payload),
            max_tokens,
            temperature,
        )
        t0 = time.monotonic()
        response = self._client.chat.completions.create(
            model=self._config.deployment,
            messages=payload,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        elapsed = time.monotonic() - t0
        usage = getattr(response, "usage", None)
        logger.info(
            "llm chat deployment=%s elapsed=%.2fs in=%s out=%s",
            self._config.deployment,
            elapsed,
            getattr(usage, "prompt_tokens", "?"),
            getattr(usage, "completion_tokens", "?"),
        )
        return response.choices[0].message.content or ""

    def _complete_responses(
        self,
        messages: Sequence[LLMMessage],
        *,
        max_tokens: int | None,
    ) -> str:
        payload = cast(
            "ResponseInputParam",
            [
                {"type": "message", "role": m.role, "content": m.content}
                for m in messages
            ],
        )
        kwargs: dict = {"model": self._config.deployment, "input": payload}
        if max_tokens is not None:
            kwargs["max_output_tokens"] = max_tokens
        logger.info(
            "llm responses request deployment=%s messages=%d max_tokens=%s",
            self._config.deployment,
            len(messages),
            max_tokens,
        )
        t0 = time.monotonic()
        response = self._client.responses.create(**kwargs)
        elapsed = time.monotonic() - t0
        usage = getattr(response, "usage", None)
        logger.info(
            "llm responses deployment=%s elapsed=%.2fs in=%s out=%s",
            self._config.deployment,
            elapsed,
            getattr(usage, "input_tokens", "?"),
            getattr(usage, "output_tokens", "?"),
        )
        return getattr(response, "output_text", "") or ""

    @staticmethod
    def _is_reasoning_model(deployment: str) -> bool:
        name = deployment.lower()
        return name.startswith(("gpt-5", "o1", "o3", "o4"))
