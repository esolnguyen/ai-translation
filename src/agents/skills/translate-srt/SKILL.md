---
name: translate-srt
description: SRT subtitle I/O wrapper. Extracts cue text only — indices and timestamps pass through. On write, enforces the ~42 char/line convention and splits long translations across two lines when required. Never renumbers or retimes.
tools: Bash, Read, Write
---

# translate-srt

Thin I/O skill for `.srt` (SubRip) subtitle files. Uses `pysrt` via Bash.

## Modes

- `extract` — `source_path` → `<run_dir>/units.jsonl`
- `write` — `<run_dir>/<target_lang>/translated-units.jsonl` + `source_path` → `<source_basename>.<target_lang>.srt`

## Dependencies

`pysrt` via Bash (optional dep).

## Procedure — extract

1. Parse the file with `pysrt.open(source_path, encoding="utf-8")`.
2. Emit one unit per subtitle cue:
    ```json
    {"id": "0001", "kind": "cue", "text": "Hello — can you hear me?\nI'm on my way.", "index": 1, "start": "00:00:01,200", "end": "00:00:03,800"}
    ```
    - `text` preserves the cue's original line breaks so the translator can see how the source was broken.
    - `index`, `start`, `end` are metadata — never changed.
3. HTML-like markup inside cues (`<i>`, `<b>`, `{\an8}` position tags) passes through in the unit text — the translator preserves it verbatim.

## Procedure — write

1. Open the source, clone it (never mutate).
2. For each cue, write the translated text:
    - Enforce a **soft** 42-char-per-line ceiling. If the translation exceeds it, split on natural boundaries (clause, punctuation, space) into at most 2 lines.
    - If splitting requires breaking mid-word or mid-particle, leave the cue as one longer line — the user can rebalance in their subtitle editor.
    - Keep every inline tag (`<i>`, `<b>`, `{\an8}`) intact.
3. Leave `index`, `start`, `end` untouched — same N cues, same timing, localized text only.
4. Save as `<source_basename>.<target_lang>.srt`.

## Notes passed to the translator (via neighbor context)

For subtitles, the translator pulls prev/next cues as context because subtitle lines are short and isolated — a single cue often can't be disambiguated without knowing the line before and after it. The orchestrator already supplies `{prev, current, next}` to `translate-translate`, so this works automatically for SRT.

## Do not

- Renumber cues. Preserve `index` and timing.
- Merge or split cues. One source cue → one target cue.
- Drop inline markup or positioning tags.
- Translate timestamps. They are not language-dependent.
