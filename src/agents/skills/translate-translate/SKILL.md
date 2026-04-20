---
name: translate-translate
description: Translator with three modes — `fast` (single pass, no flagging; for short docs), pass `1` (draft with `<unsure>`/`<sense>` self-flagging), and pass `2` (rewrite only flagged spans using cycle-check diffs). Stateless per chunk — document-level state (domain prime, glossary, style card) is passed in per call; prior chunk drafts never ride in context.
tools: Bash, Read, Write
---

# translate-translate

The core translation skill. Re-entered per chunk/batch, never as one rolling conversation. Three modes live here — the orchestrator picks one:

- `--pass fast` — Fast path (≤100 units, single target). Single shot, no flagging, writes final chunk directly.
- `--pass 1` — Full path, first draft with self-flagging.
- `--pass 2` — Full path, rewrite only spans the cycle-check / reviewer flagged.

## Inputs (all modes)

- `run_dir`, `target_lang`
- `analysis_path` — `<run_dir>/analysis.json` (domain prime — injected **verbatim**)
- `glossary_path` — `<run_dir>/glossary.<target_lang>.json`
- `style_card` — from `kb lang-card <target_lang>` (fetched by orchestrator, passed as JSON string)
- `chunk` — `{id, prev_text, current_text, next_text}` (neighbor-context chunking, DESIGN-agent.md §Accuracy #4)
- `pass` — `fast` | `1` | `2`

Pass-2-only:
- `pass1_draft_path` — `<run_dir>/<lang>/chunks/<id>.pass1.md`
- `cycle_check_path` — optional `<run_dir>/<lang>/chunks/<id>.cycle.json` (diffs for flagged spans)
- `reviewer_retry_focus` — optional, when the reviewer kicked the chunk back with `retry_focus`

## System prompt (assembled by the skill itself)

Injected in order, each section labeled:

1. `## Domain prime` — full contents of `analysis.json`, verbatim.
2. `## Style card` — full `kb lang-card` JSON.
3. `## Glossary (authoritative)` — `glossary.<target_lang>.json` entries; translator must use these exact target-language forms and is forbidden from choosing alternatives.
4. `## Neighbor context` — prev + next chunk. **Do not translate.** Only the current chunk is translated.
5. `## Task` — pass-specific (below).

## Procedure — Pass fast

1. Translate **only** `chunk.current_text` into `target_lang`, applying the domain prime, style card, and glossary in one shot.
2. Do **not** emit `<unsure>` / `<sense>` tags — no downstream consumer reads them on this path.
3. When a glossary term is ambiguous or the translation is uncertain, pick the best-fit target form using the domain prime and move on. Do not back-translate or self-critique here — that's what the Full path exists for; Fast path accepts a small quality floor in exchange for ~10× latency reduction.
4. Preserve source formatting — markdown, inline code, placeholders, HTML tags pass through unchanged.
5. Write directly to `<run_dir>/<target_lang>/chunks/<id>.md` (the final path — no `.pass1` / `.pass2` stages). Emit the same text on stdout.

## Procedure — Pass 1

1. Translate **only** `chunk.current_text` into `target_lang`.
2. Wrap uncertain spans in `<unsure>...</unsure>`.
3. Wrap polysemous picks in `<sense word="<source>" chose="<target>" because="<1-line reason>">...</sense>`.
4. Preserve source formatting — markdown, inline code, placeholders, HTML tags pass through unchanged.
5. Write the draft to `<run_dir>/<target_lang>/chunks/<id>.pass1.md`. Emit the same text on stdout.

## Procedure — Pass 2

1. Read the pass-1 draft.
2. Read `cycle_check_path` if present — each entry lists a `<unsure>` / `<sense>` span, its back-translation, and a drift score. Spans with score ≤ 3 are the **only** ones to rewrite.
3. If `reviewer_retry_focus` is present, also rewrite the spans it lists, using the reviewer's `reason` as the instruction.
4. For every rewrite, re-check against the glossary — never introduce a target form that isn't in `glossary.<target_lang>.json` unless the term is newly encountered (in which case flag it, don't invent).
5. Strip all `<unsure>` / `<sense>` / `<span>` tags from the final output — they were internal signals.
6. Write the final draft to `<run_dir>/<target_lang>/chunks/<id>.md` (overwriting any pass-1 file) and emit to stdout.

## Formatting invariants

- Markdown: headings, lists, code fences, inline code, emphasis all preserved. Never translate fenced code content.
- Placeholders (`{name}`, `%s`, `{{var}}`, `<tag>`) pass through unchanged.
- Numbers, units, and dates follow the style card's locale rules (e.g. Vietnamese decimal comma per `vault/languages/vi.md`).
- Do not add or drop sentences. A `<unsure>` tag around an uncertain span is always preferable to rewriting it into something the reviewer can't check.

## Do not

- Read prior chunks' drafts — stateless per chunk, the orchestrator passes what you need.
- Invent glossary entries. Unknown terms stay in the source form wrapped in `<unsure>`, surfaced to `translate-glossary` via the reviewer's `failures` list.
- Translate the neighbor-context chunks. They are read-only reference.
- Back-translate here. That's `translate-cycle-check`'s job.
