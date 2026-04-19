"""Document adapters — concrete implementations of ``DocumentAdapter``.

Factory: ``make_document_adapter(path)`` dispatches on file extension.
PDFs are deliberately rejected — they are knowledge sources, not translation
targets (``kb extract`` ingests them into the vault).
"""

from __future__ import annotations

from pathlib import Path

from ...use_cases.ports import DocumentAdapter
from .docx import DocxAdapter
from .md import MarkdownAdapter
from .srt import SrtAdapter
from .txt import TxtAdapter
from .xlsx import XlsxAdapter

_REGISTRY: dict[str, type[DocumentAdapter]] = {
    ".txt": TxtAdapter,
    ".md": MarkdownAdapter,
    ".docx": DocxAdapter,
    ".srt": SrtAdapter,
    ".xlsx": XlsxAdapter,
}


def make_document_adapter(path: Path) -> DocumentAdapter:
    """Return the adapter responsible for ``path``."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        raise ValueError(
            "PDF is a knowledge source, not a translation target. "
            "Use `kb extract` to ingest it into the vault."
        )
    try:
        return _REGISTRY[ext]()
    except KeyError as exc:
        supported = ", ".join(sorted(_REGISTRY))
        raise ValueError(
            f"Unsupported format: {ext}. Supported: {supported}"
        ) from exc


__all__ = ["make_document_adapter"]
