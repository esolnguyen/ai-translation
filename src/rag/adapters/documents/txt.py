"""Plain-text adapter. Chunks on blank-line paragraph boundaries."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from ...domain import TranslatedUnit, Unit, UnitKind
from ...use_cases.ports import DocumentAdapter

_PARA_SPLIT = re.compile(r"\n\s*\n+")
_CHUNK_TARGET_CHARS = 2800  # ~700 tokens @ ~4 chars/token


class TxtAdapter(DocumentAdapter):
    extension = ".txt"

    def extract(self, source_path: Path) -> list[Unit]:
        raw = source_path.read_bytes()
        has_bom = raw.startswith(b"\xef\xbb\xbf")
        text = raw.decode("utf-8-sig" if has_bom else "utf-8")
        line_ending = "\r\n" if "\r\n" in text else "\n"
        normalised = text.replace("\r\n", "\n")

        paragraphs = [p for p in _PARA_SPLIT.split(normalised) if p.strip()]
        units: list[Unit] = []
        buf: list[str] = []
        buf_chars = 0
        idx = 0
        para_indices: list[int] = []

        def flush() -> None:
            nonlocal buf, buf_chars, para_indices, idx
            if not buf:
                return
            units.append(
                Unit(
                    id=f"{idx:04d}",
                    kind=UnitKind.CHUNK,
                    text="\n\n".join(buf),
                    meta={"para_indices": para_indices.copy()},
                )
            )
            idx += 1
            buf = []
            buf_chars = 0
            para_indices = []

        for p_i, para in enumerate(paragraphs):
            if buf and buf_chars + len(para) > _CHUNK_TARGET_CHARS:
                flush()
            buf.append(para)
            buf_chars += len(para)
            para_indices.append(p_i)
        flush()

        if units:
            units[0].meta["_file"] = {
                "bom": has_bom,
                "line_ending": line_ending,
                "trailing_newline": normalised.endswith("\n"),
            }
        return units

    def write(
        self,
        source_path: Path,
        translated: Iterable[TranslatedUnit],
        target_lang: str,
        output_path: Path,
    ) -> None:
        translated_list = list(translated)
        if not translated_list:
            output_path.write_text("", encoding="utf-8")
            return
        file_meta = translated_list[0].meta.get("_file", {})
        line_ending = file_meta.get("line_ending", "\n")
        trailing = file_meta.get("trailing_newline", True)
        bom = file_meta.get("bom", False)

        body = "\n\n".join(u.target_text for u in translated_list)
        if trailing:
            body += "\n"
        body = body.replace("\n", line_ending)
        data = body.encode("utf-8-sig" if bom else "utf-8")
        output_path.write_bytes(data)
