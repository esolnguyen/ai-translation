"""Adapter layer — concrete implementations of use-case ports.

Subpackages:

- ``documents/``     — file-format adapters (txt, md, docx, srt, xlsx)
- ``retrieval/``     — bridges to ``knowledge.core.retrieval``
- ``persistence/``   — run repository (filesystem + Mongo)
- ``pipeline/``      — pipeline runners (simple hand-rolled, future LangGraph)
- ``llm/``           — LLM client backends
"""

from __future__ import annotations
