"""Persistence adapters — implementations of ``RunRepository``.

Factory: ``make_run_repository(kind)`` selects between filesystem (default,
``.translate-runs/<run-id>/``) and Mongo (shared-state deployments). Mongo is
a stub until the shared-state path is needed.
"""

from __future__ import annotations

from typing import Literal

from ...use_cases.ports import RunRepository
from .filesystem import FilesystemRunRepository

type RepositoryKind = Literal["filesystem", "mongo"]


def make_run_repository(kind: RepositoryKind = "filesystem") -> RunRepository:
    if kind == "filesystem":
        return FilesystemRunRepository()
    if kind == "mongo":
        from .mongo import MongoRunRepository
        return MongoRunRepository.from_env()
    raise ValueError(f"unknown repository kind: {kind}")


__all__ = ["FilesystemRunRepository", "make_run_repository"]
