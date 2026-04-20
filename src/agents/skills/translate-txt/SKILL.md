---
name: translate-txt
description: Plain-text I/O wrapper. In extract mode, chunks the file on paragraph boundaries (~500–800 tokens per chunk) so the translator's neighbor-context chunking has clean units. In write mode, concatenates chunks in order — preserving paragraph breaks and trailing newlines from the source.
tools: Bash, Read, Write
---

# translate-txt

Thin I/O skill for `.txt`. Simplest of the format handlers — the only real work is chunking.

## Modes

- `extract` — `source_path` → `<run_dir>/units.jsonl`
- `write` — `<run_dir>/<target_lang>/translated-units.jsonl` + `source_path` → `<source_basename>.<target_lang>.txt`

## Procedure — extract

1. Read `source_path` as UTF-8. If the file declares a BOM or non-UTF-8 encoding, honor it and record the encoding in `manifest.json` so `write` round-trips the same way.
2. Split on blank-line paragraph boundaries (`\n\s*\n+`).
3. Group paragraphs into chunks of ~500–800 tokens (approximate — use char-count / 4 as a cheap proxy). A chunk is a list of consecutive paragraphs that fit under the ceiling; never split a paragraph across chunks.
4. Emit one unit per chunk:
    ```json
    {"id": "0001", "kind": "chunk", "text": "Paragraph 1.\n\nParagraph 2.\n\nParagraph 3.", "para_indices": [0, 1, 2], "byte_range": [0, 312]}
    ```
5. Preserve the original separators. If the source uses Windows line endings (`\r\n`), record that and restore on write.

## Procedure — write

1. Read `<run_dir>/<target_lang>/translated-units.jsonl` in `id` order.
2. Join translated chunk texts with `\n\n` (or the source's observed paragraph separator).
3. Preserve the source's line-ending convention (LF vs CRLF) and trailing newline.
4. Write to `<source_basename>.<target_lang>.txt` next to the source. Never modify the source.

## Notes

- `translate-txt` does not strip or normalize. If the source has quirky spacing, so does the output.
- For very long `.txt` files, the chunk ceiling prevents any single translator call from becoming unwieldy. `translate-translate` already passes `{prev, current, next}` so cross-chunk reference drift is handled at the translator layer, not here.
- No markup, no formatting state — this is the simplest path through the pipeline and makes a good smoke test.

## Do not

- Translate per paragraph — chunk first, translate chunks. Too-small units lose the context the translator needs for good register and pronoun choices.
- Re-order chunks on write. `id` order is canonical.
- Normalize encodings silently. Round-trip whatever the source uses.
