"""Retrieval adapters — bridge to the knowledge-base retrieval surface."""

from __future__ import annotations

from .knowledge_base import KnowledgeBaseRetriever, make_retriever

__all__ = ["KnowledgeBaseRetriever", "make_retriever"]
