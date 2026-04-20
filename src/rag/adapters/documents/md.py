"""Markdown adapter — block-range extraction via ``markdown-it-py``.

Each translatable block (paragraph, heading, list-item paragraph) becomes one
``Unit`` carrying its source line range in meta. Non-translatable ranges
(fenced code, HTML blocks, YAML frontmatter) are preserved verbatim by the
writer — they never leave the adapter.

Round-trip contract: ``write(extract(src))`` equals ``src`` when every
``TranslatedUnit.target_text`` equals the unit's source ``Unit.text``.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from markdown_it import MarkdownIt

from ...domain import TranslatedUnit, Unit, UnitKind
from ...use_cases.ports import DocumentAdapter

_BLOCK_KIND: dict[str, UnitKind] = {
    "paragraph_open": UnitKind.PARAGRAPH,
    "heading_open": UnitKind.HEADING,
}


class MarkdownAdapter(DocumentAdapter):
    extension = ".md"

    def extract(self, source_path: Path) -> list[Unit]:
        raw = source_path.read_bytes()
        has_bom = raw.startswith(b"\xef\xbb\xbf")
        text = raw.decode("utf-8-sig" if has_bom else "utf-8")
        line_ending = "\r\n" if "\r\n" in text else "\n"
        normalised = text.replace("\r\n", "\n")
        lines = normalised.split("\n")

        frontmatter_end = _detect_frontmatter_end(lines)
        blocks = _extract_blocks(normalised, skip_before=frontmatter_end)
        units: list[Unit] = []
        for idx, (kind, start, end) in enumerate(blocks):
            block_text = "\n".join(lines[start:end])
            units.append(
                Unit(
                    id=f"{idx:04d}",
                    kind=kind,
                    text=block_text,
                    meta={"line_start": start, "line_end": end},
                )
            )
        if units:
            units[0].meta["_file"] = {
                "bom": has_bom,
                "line_ending": line_ending,
                "trailing_newline": normalised.endswith("\n"),
                "source_line_count": len(lines),
            }
        return units

    def write(
        self,
        source_path: Path,
        translated: Iterable[TranslatedUnit],
        target_lang: str,
        output_path: Path,
    ) -> None:
        raw = source_path.read_bytes()
        has_bom = raw.startswith(b"\xef\xbb\xbf")
        text = raw.decode("utf-8-sig" if has_bom else "utf-8")
        line_ending = "\r\n" if "\r\n" in text else "\n"
        normalised = text.replace("\r\n", "\n")
        lines = normalised.split("\n")

        cues = sorted(
            translated,
            key=lambda u: u.meta.get("line_start", 0),
        )
        rebuilt: list[str] = []
        cursor = 0
        for unit in cues:
            start = int(unit.meta.get("line_start", cursor))
            end = int(unit.meta.get("line_end", start))
            if start < cursor:
                continue
            rebuilt.extend(lines[cursor:start])
            rebuilt.extend(unit.target_text.split("\n"))
            cursor = end
        rebuilt.extend(lines[cursor:])

        body = "\n".join(rebuilt)
        body = body.replace("\n", line_ending)
        data = body.encode("utf-8-sig" if has_bom else "utf-8")
        output_path.write_bytes(data)


def _detect_frontmatter_end(lines: list[str]) -> int:
    if not lines or lines[0].strip() != "---":
        return 0
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return i + 1
    return 0


def _extract_blocks(
    text: str, *, skip_before: int
) -> list[tuple[UnitKind, int, int]]:
    parser = MarkdownIt("commonmark").enable("table")
    tokens = parser.parse(text)
    blocks: list[tuple[UnitKind, int, int]] = []
    for i, tok in enumerate(tokens):
        kind = _BLOCK_KIND.get(tok.type)
        if kind is None or tok.map is None:
            continue
        start, end = tok.map
        if start < skip_before:
            continue
        next_idx = i + 1
        if next_idx >= len(tokens) or tokens[next_idx].type != "inline":
            continue
        if not tokens[next_idx].content.strip():
            continue
        blocks.append((kind, start, end))
    blocks.sort(key=lambda b: b[1])
    return _dedupe_overlapping(blocks)


def _dedupe_overlapping(
    blocks: list[tuple[UnitKind, int, int]],
) -> list[tuple[UnitKind, int, int]]:
    result: list[tuple[UnitKind, int, int]] = []
    for kind, start, end in blocks:
        if result and start < result[-1][2]:
            continue
        result.append((kind, start, end))
    return result
