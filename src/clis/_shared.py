"""Helpers shared across the ``translate`` subcommands."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def read_text_argument(raw: str) -> str:
    """Support ``@file`` for passing file contents as an argument."""
    if raw.startswith("@"):
        return Path(raw[1:]).read_text(encoding="utf-8")
    return raw


def vault_path(override: str | None = None) -> Path:
    if override:
        return Path(override)
    return Path(os.environ.get("KB_VAULT", "vault"))


def emit_json(payload: Any) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
