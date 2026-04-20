"""SRT subtitle adapter — one ``Unit`` per cue; timing preserved verbatim."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from ...domain import TranslatedUnit, Unit, UnitKind
from ...use_cases.ports import DocumentAdapter

_TIMING_RE = re.compile(
    r"^\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d{3}.*$"
)


class SrtAdapter(DocumentAdapter):
    extension = ".srt"

    def extract(self, source_path: Path) -> list[Unit]:
        raw = source_path.read_bytes()
        has_bom = raw.startswith(b"\xef\xbb\xbf")
        text = raw.decode("utf-8-sig" if has_bom else "utf-8")
        line_ending = "\r\n" if "\r\n" in text else "\n"
        normalised = text.replace("\r\n", "\n").replace("\r", "\n")

        units: list[Unit] = []
        blocks = _split_blocks(normalised)
        for idx, block_lines in enumerate(blocks):
            cue = _parse_block(block_lines)
            if cue is None:
                continue
            index_token, timing_line, text_lines = cue
            units.append(
                Unit(
                    id=f"{idx:04d}",
                    kind=UnitKind.CUE,
                    text="\n".join(text_lines),
                    meta={
                        "index": index_token,
                        "timing": timing_line,
                        "position": idx,
                    },
                )
            )
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
        cues = sorted(
            translated,
            key=lambda u: u.meta.get("position", 0),
        )
        if not cues:
            output_path.write_text("", encoding="utf-8")
            return
        file_meta = cues[0].meta.get("_file", {})
        line_ending = file_meta.get("line_ending", "\n")
        trailing = file_meta.get("trailing_newline", True)
        bom = file_meta.get("bom", False)

        rendered: list[str] = []
        for cue in cues:
            block = "\n".join(
                filter(
                    None,
                    [
                        cue.meta.get("index", ""),
                        cue.meta.get("timing", ""),
                        cue.target_text,
                    ],
                )
            )
            rendered.append(block)
        body = "\n\n".join(rendered)
        if trailing:
            body += "\n"
        body = body.replace("\n", line_ending)
        data = body.encode("utf-8-sig" if bom else "utf-8")
        output_path.write_bytes(data)


def _split_blocks(text: str) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in text.split("\n"):
        if line.strip() == "":
            if current:
                blocks.append(current)
                current = []
        else:
            current.append(line)
    if current:
        blocks.append(current)
    return blocks


def _parse_block(lines: list[str]) -> tuple[str, str, list[str]] | None:
    if len(lines) < 2:
        return None
    index_token = lines[0].strip()
    timing_line = lines[1].strip()
    if not _TIMING_RE.match(timing_line):
        # Tolerate missing index — some SRTs skip them.
        if _TIMING_RE.match(index_token):
            return "", index_token, lines[1:]
        return None
    return index_token, timing_line, lines[2:]
