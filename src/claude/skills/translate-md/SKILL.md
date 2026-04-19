---
name: translate-md
description: Markdown I/O wrapper. In extract mode, parses the source to an AST and emits translatable text nodes as JSONL. In write mode, reassembles the target file from translated units — preserving headings, lists, code fences, emphasis, links, and YAML frontmatter untouched.
tools: Bash, Read, Write
---

# translate-md

Thin I/O skill for `.md` files. Keeps the AST on disk; Claude only sees text nodes via JSONL (DESIGN-agent.md §Execution model — format handlers are I/O wrappers, not AST dumpers).

## Modes

- `extract` — `source_path` → `<run_dir>/units.jsonl`
- `write` — `<run_dir>/<target_lang>/translated-units.jsonl` + `source_path` → `<source_basename>.<target_lang>.md`

## Dependencies (via Bash)

Uses `markdown-it-py` (already a project dep per pyproject.toml) via a small inline Python one-liner.

## Procedure — extract

1. Parse `source_path` with `markdown_it.MarkdownIt("commonmark")`.
2. Preserve YAML frontmatter (`---...---` at file start) as a pass-through block — do **not** emit for translation.
3. Walk the token stream. Emit one unit per translatable text node:
    - Paragraphs, list items, blockquote contents, table cells, heading text.
    - Link **label** is translatable; link **URL** is not.
    - Image **alt text** is translatable; image path is not.
4. Do not emit:
    - Fenced/indented code blocks (`kind: "code"` — passes through unchanged).
    - Inline code (`` `...` `` — passes through).
    - HTML blocks (pass through; if translation inside is desired the user edits the source).
5. Write `<run_dir>/units.jsonl`, one line per unit:
    ```json
    {"id": "0001", "kind": "heading", "level": 2, "text": "Pre-Delivery Service", "position": {...}}
    {"id": "0002", "kind": "paragraph", "text": "The D/C cut fuse (30A) has been removed...", "position": {...}}
    {"id": "0003", "kind": "list_item", "text": "Reinstall the fuse during PDS.", "position": {...}}
    ```
    Each `position` records the byte range in the source so `write` can splice back in-place.

## Procedure — write

1. Read the original `source_path` as bytes.
2. Read `<run_dir>/<target_lang>/translated-units.jsonl` — maps unit `id` → translated `text`.
3. For each unit, replace the byte range at `position` with the translated text. Walk right-to-left so offsets stay valid.
4. Preserve frontmatter, code, HTML, link URLs, image paths — all untouched.
5. Write `<source_basename>.<target_lang>.md` next to the source. Never modify the source.

## Do not

- Pass the full AST or token list through Claude's context. The translator reads unit `text` only.
- Translate fenced code or inline code. Users who need code-comment translation can mark it explicitly.
- Touch YAML frontmatter. If metadata needs localizing, the user handles that out-of-band.
