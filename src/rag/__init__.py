"""RAG translation pipeline — clean-architecture layout.

Layers (dependencies point inward):

    frameworks/  →  adapters/  →  use_cases/  →  domain/

Public surface:

    from rag import translate, RunConfig
"""

from __future__ import annotations

from .domain import RunConfig
from .router import translate

__all__ = ["RunConfig", "translate"]
