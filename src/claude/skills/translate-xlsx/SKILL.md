---
name: translate-xlsx
description: Excel template I/O wrapper for Flow B. In extract mode, reads the designated source column and detects empty target columns per language. In write mode, fills each target column in-place — idempotent (already-filled cells skipped), preserving all other sheets, styles, and formulas.
tools: Bash, Read, Write
---

# translate-xlsx

Thin I/O skill for `.xlsx`. Uses `openpyxl` via Bash. Owns the column-detection convention that makes Flow B possible.

## Modes

- `extract` — `source_path` → `<run_dir>/units.jsonl` (+ column mapping in `manifest.json`)
- `write` — `<run_dir>/<target_lang>/translated-units.jsonl` (one per target lang) + `source_path` → `<source_basename>.translated.xlsx`

## Dependencies

`openpyxl` via Bash (optional dep).

## Column convention

Header row (row 1 by default, configurable via `--header-row`) names each column by a language code or a domain label:

| source (en) | ja | fr | de | notes |
|---|---|---|---|---|

- The **source** column is the one whose header equals the configured source lang (default `en`, or matches a header like `source (en)` / `english`).
- Any other column whose header matches a BCP-47 code (`ja`, `fr`, `de`, `vi`, ...) or maps via a language-alias table is a **target column**.
- All other columns pass through untouched (notes, IDs, metadata).

## Procedure — extract

1. Open the workbook: `load_workbook(source_path, data_only=False)` (keep formulas intact).
2. Choose the active sheet (or `--sheet <name>`). Detect header row; map headers → language codes.
3. For each data row:
    - Read the source cell. Skip if empty.
    - For each target lang in the run's `--to` list:
        - If the target column's cell is **non-empty** → skip (idempotent).
        - Else → emit a unit.
4. Emit one unit per (row, target_lang) so per-language workers can scope their work:
    ```json
    {"id": "R042-ja", "kind": "cell", "text": "Brake fluid reservoir", "row": 42, "col": "ja", "source_col": "en"}
    ```
    Workers filter on the `col` suffix matching their `target_lang`.
5. Write column mapping + source/target column ids into `manifest.json` so `write` mode can find the right columns without re-detecting.

## Procedure — write

1. Clone `source_path` → `<source_basename>.translated.xlsx`.
2. Open the clone. For each target language, read `<run_dir>/<target_lang>/translated-units.jsonl`.
3. For each translated unit, write `text` into `sheet.cell(row=unit.row, column=<col-for-unit.col>)`.
4. Never overwrite a non-empty cell in a target column (safety net — idempotency).
5. Save the clone. All other cells, sheets, formulas, named ranges, and conditional formatting are untouched because `openpyxl` only modifies the cells we write.

## Batching for translators

`translate-translate` works in ~30-row batches (DESIGN-agent.md §Key design decisions). The orchestrator groups units by `row` ranges; this skill doesn't need to know about batching — it extracts per row, writes per row.

## Do not

- Touch non-target columns. Notes, IDs, and pass-through data are sacred.
- Normalize or trim source cells. Users sometimes embed meaningful leading/trailing whitespace for alignment.
- Re-evaluate formulas. `data_only=False` on load and a pure cell-value write keep formulas intact.
- Overwrite a cell that already has content in the target column — even on `--resume` of a failed run. The user may have hand-filled it.
