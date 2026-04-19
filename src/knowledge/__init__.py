"""Shared knowledge base for the AI translation system.

Owns the vault (source of truth), the indexer (vault -> vector DB + structured
stores), and the retrieval API that both translation paths consume.
"""

__version__ = "0.1.0"
