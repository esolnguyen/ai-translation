"""LLM client adapters.

Factory: ``make_llm_client(kind)`` dispatches on env-selected provider.
Default is ``"null"`` for dry-run harness.

Supported kinds (also selectable via ``RAG_LLM``):

- ``null``          — no-op, returns empty string
- ``claude``        — Claude Agent SDK (stub)
- ``azure-openai``  — Azure OpenAI chat completions
- ``gemini``        — Google Gemini (``google-genai``)
"""

from __future__ import annotations

import os
from typing import Literal

from ...use_cases.ports import LLMClient
from .null import NullLLMClient

type ClientKind = Literal["null", "claude", "azure-openai", "gemini"]


def make_llm_client(kind: ClientKind | None = None) -> LLMClient:
    resolved = kind or os.environ.get("RAG_LLM", "null")
    if resolved == "null":
        return NullLLMClient()
    if resolved == "claude":
        from .claude import ClaudeLLMClient
        return ClaudeLLMClient.from_env()
    if resolved == "azure-openai":
        from .azure_openai import AzureOpenAIClient
        return AzureOpenAIClient.from_env()
    if resolved == "gemini":
        from .gemini import GeminiClient
        return GeminiClient.from_env()
    raise ValueError(f"unknown LLM client kind: {resolved}")


__all__ = ["NullLLMClient", "make_llm_client"]
