"""Robust JSON extraction from LLM responses.

LLMs often wrap JSON in ```json fences or prose. This helper pulls the first
balanced ``{...}`` block out of a response and parses it. On failure it
returns ``None`` — callers decide the fallback.
"""

from __future__ import annotations

import json
from typing import Any


def extract_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None
