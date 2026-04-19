---
name: translate-docx
description: DOCX I/O wrapper. Extracts runs (not paragraphs) so bold/italic/style spans survive translation. In write mode, writes text back into the same runs, preserving every style, table, list, image, and section property of the source document.
tools: Bash, Read, Write
---

# translate-docx

Thin I/O skill for `.docx`. Uses `python-docx` via Bash. The DOCX stays on disk; Claude only sees run text.

## Modes

- `extract` — `source_path` → `<run_dir>/units.jsonl`
- `write` — `<run_dir>/<target_lang>/translated-units.jsonl` + `source_path` → `<source_basename>.<target_lang>.docx`

## Dependencies

`python-docx` via Bash (listed in pyproject.toml optional deps for format handling).

## Procedure — extract

1. Open the document: `Document(source_path)`.
2. For each paragraph, emit translatable units at the **run** level:
    - A run is a stretch of text sharing the same formatting (bold, italic, font, highlight). Emitting per run preserves inline emphasis across translation.
    - Merge adjacent runs with identical formatting into a single unit to reduce fragmentation.
    - A unit carries `{id, kind: "run", text, para_index, run_indices, style}`.
3. Table cells: emit cell paragraphs with the same per-run granularity, keyed by `{table_index, row, col, para_index, run_indices}`.
4. Headers, footers, footnotes: emit under `kind: "header" | "footer" | "footnote"` with their own indexing keys.
5. Skip entirely:
    - Images (positions preserved in the docx, not in units).
    - Embedded objects.
    - Fields (`{MERGEFIELD}`, page numbers) — passed through as-is.
6. Write `<run_dir>/units.jsonl`. Persist enough location metadata to round-trip (para_index, run_indices).

## Procedure — write

1. Copy `source_path` → `<source_basename>.<target_lang>.docx` (never mutate the source).
2. Open the copy with `python-docx`.
3. For each translated unit, write `translated.text` into the identified runs:
    - If the translation is a single run, collapse back into the first run of the merged set; clear the rest.
    - Preserve the run's style — only `text` changes.
4. Save the copy. Tables, images, styles, headers/footers, list numbering, section breaks all survive because we only touched run `.text`.

## Notes on inline emphasis

Because extraction is per run, the translator sees something like:
```
{"id": "0073", "text": "The D/C cut fuse", "style": "bold"}
{"id": "0074", "text": " must be reinstalled.", "style": "regular"}
```
This is better than `[bold]The D/C cut fuse[/bold] must be reinstalled.` because the translator never has to re-emit markup. It just writes the Vietnamese text; the DOCX keeps the bold run as bold.

## Do not

- Rebuild the DOCX from scratch. Open the copied file, edit runs in place, save.
- Merge runs that have different formatting. Preserving per-run style is the whole point of using `python-docx` over a plain-text extractor.
- Translate field codes (`MERGEFIELD`, `HYPERLINK`, page numbers).
