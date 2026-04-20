"""JSON-file adapter for :class:`TermLookupCache`.

Writes to a single JSON file under the KB store directory. The cache is
loaded into memory on construction, mutated in place, and flushed back on
``flush()``. Entries carry a ``kb_version`` tag; reads drop entries whose
version does not match the current one, so an updated KB index invalidates
stale lookups automatically.
"""

from __future__ import annotations
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ...use_cases.ports import TermLookupCache


class JsonTermLookupCache(TermLookupCache):
    def __init__(self, path: Path, *, kb_version: str | None = None) -> None:
        self._path = path
        self._kb_version = kb_version
        self._entries: dict[str, dict[str, Any]] = {}
        self._dirty = False
        self._load()

    def get(
        self,
        term: str,
        *,
        domain: str | None,
        target_lang: str | None,
    ) -> dict[str, Any] | None:
        key = _make_key(term, domain, target_lang)
        entry = self._entries.get(key)
        if entry is None:
            return None
        if self._kb_version is not None and entry.get("kb_version") != self._kb_version:
            self._entries.pop(key, None)
            self._dirty = True
            return None
        payload = entry.get("payload")
        return dict(payload) if isinstance(payload, dict) else None

    def put(
        self,
        term: str,
        *,
        domain: str | None,
        target_lang: str | None,
        payload: Mapping[str, Any],
    ) -> None:
        key = _make_key(term, domain, target_lang)
        self._entries[key] = {
            "term": term,
            "domain": domain,
            "target_lang": target_lang,
            "kb_version": self._kb_version,
            "payload": dict(payload),
        }
        self._dirty = True

    def flush(self) -> None:
        if not self._dirty:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"entries": self._entries}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._dirty = False

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        entries = data.get("entries") if isinstance(data, dict) else None
        if isinstance(entries, dict):
            self._entries = {
                k: dict(v) for k, v in entries.items() if isinstance(v, dict)
            }


def _make_key(term: str, domain: str | None, target_lang: str | None) -> str:
    return f"{target_lang or '*'}::{domain or '*'}::{term}"


def make_term_cache(kb_store_path: Path) -> TermLookupCache:
    """Factory — builds a JSON cache under ``<kb_store_path>/lookup-cache.json``.

    The KB version is derived from a stable digest of the top-level file
    listing (name + mtime) so ``kb index`` mutations invalidate entries
    without requiring a hand-maintained version file.
    """

    cache_path = kb_store_path / "lookup-cache.json"
    return JsonTermLookupCache(cache_path, kb_version=_kb_version(kb_store_path))


def _kb_version(root: Path) -> str | None:
    if not root.exists():
        return None
    digest = hashlib.sha256()
    for item in sorted(root.rglob("*")):
        if item.name == "lookup-cache.json":
            continue
        try:
            stat = item.stat()
        except OSError:
            continue
        digest.update(str(item.relative_to(root)).encode("utf-8"))
        digest.update(f"{stat.st_mtime_ns}:{stat.st_size}".encode("ascii"))
    return digest.hexdigest()[:16]
