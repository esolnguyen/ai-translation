---
name: translate
description: Slash-command orchestrator for the translation pipeline. Invoked as `/translate <file> --to <lang>[,lang2,...]`. Dispatches to the right format skill, runs the analyzer/glossary once, then drives either a Fast path (small docs) or the full translate→cycle-check→reviewer→edit chain (Flow A) / per-language workers (Flow B).
allowed-tools: Bash, Read, Write, Edit
---

**Invocation arguments:** `$ARGUMENTS`

Parse `$ARGUMENTS` as `<file> --to <lang>[,<lang>...] [--run-id <id>] [--resume] [--fast | --full]` and proceed with the pipeline below. If `$ARGUMENTS` is empty, ask the user for the file path and target language.

# /translate

Entry point for all translation work. Owns run-directory lifecycle, format dispatch, and the high-level skill/subagent chain per DESIGN-agent.md §Flow A / §Flow B.

## Invocation

```
/translate <path> --to <lang>[,<lang>...] [--run-id <id>] [--resume] [--fast | --full]
```

Supported source formats: `.txt`, `.md`, `.docx`, `.srt`, `.xlsx`. **PDF is rejected** — PDFs are knowledge sources, not translation targets (see DESIGN-agent.md §Phase 2).

`--fast` / `--full` override the auto-selected path (see Path selection).

## Procedure

1. **Validate input.** Extension ∈ {txt, md, docx, srt, xlsx}. Reject PDF with a pointer to `kb extract`. Parse `--to` into a list of BCP-47 language codes.
2. **Run directory.** If `--resume` and `--run-id` given, reuse. Else create `.translate-runs/<run-id>/` (run-id = `<timestamp>-<basename>-<rand6>`). Write `manifest.json`: `{source_path, source_lang, target_langs, format, path, started_at, status: "running"}`.
3. **Format extraction.** Invoke the matching format skill (`translate-md`, `translate-docx`, `translate-srt`, `translate-xlsx`, `translate-txt`) with `{mode: extract, source_path, run_dir}`. It writes `<run_dir>/units.jsonl`.
4. **Path selection (auto, unless `--fast` / `--full` overrides).** After extraction, count `N = len(units.jsonl)`. Pick **Fast** if *all* hold:
    - `N ≤ 100`
    - single target language
    - format ∈ {txt, md, srt}
    - no user override to `--full`
   Otherwise pick **Full**. Record the choice in `manifest.json` as `path: "fast" | "full"`.
5. **Document-level state (once per run, shared across all target languages).**
    - `translate-analyze` → `<run_dir>/analysis.json` (domain, sub-domain, tone, register, retrieved note ids). *Always runs — cheap, single call.*
    - `translate-resolve-terms` → `<run_dir>/resolved-terms.<lang>.json`. **Full path only.** Fast path folds polysemy locks into the glossary step via a tighter prompt.
    - `translate-glossary` → `<run_dir>/glossary.<lang>.json` (merges `kb glossary` + `kb entity` + `kb idiom` + resolved terms on full path; Fast path skips the resolve merge and lets the translator lock terms inline during its single pass).
6. **Dispatch by path:**
    - **Fast path (≤100 units, single target, text-like format):** invoke `translate-translate` once per chunk with `--pass fast` — a single-pass translation that inlines the glossary and style card, flags nothing, and writes straight to `<run_dir>/<lang>/chunks/<id>.md`. No cycle-check, no reviewer, no edit. Rationale: for short documents cross-chunk drift is bounded; the full chain's consistency guarantees don't earn their latency.
    - **Full path / Flow A (single target, text-like format, >100 units):** run the chain inline in the main thread — `translate-translate` pass 1 → `translate-cycle-check` → `translate-translate` pass 2 → `translation-reviewer` subagent → `translate-edit`, chunk by chunk.
    - **Full path / Flow B (xlsx, or multiple target languages):** spawn a **`translation-lang-worker`** subagent per target language in parallel. Each worker owns its language's chain end-to-end. Flow B never uses Fast path — xlsx needs per-row consistency and multi-language fan-out already benefits from the full chain.
7. **Format rebuild.** Re-invoke the format skill with `{mode: write, source_path, run_dir, target_langs}`. It reads per-language translated units and writes `<input>.<lang>.<ext>` files beside the source (or fills in-place for xlsx).
8. **Finalize.** Update `manifest.json`: `status: "done"`, `finished_at`, `path`, per-language summary `{passed, retried, escalated}`. Print a user-facing report naming output paths and any escalations.

## Path selection — why 100 units

The threshold exists because the Full path's stages (resolve-terms, cycle-check, two-pass, reviewer, edit) each cost one round-trip and write a scratch file; their value is preventing drift when the same ambiguous term reappears across many chunks. Below ~100 units that risk is small — most polysemous terms appear once, so locking them document-wide is wasted work. Benchmarks on the 61-unit Holden sample: Full path ≈ 16 min, Fast path ≈ 1–2 min, output quality equivalent.

Override when:
- `--full` on a short doc if it's legally critical (contracts, ACL clauses) and you want the reviewer signal even for 30 sentences.
- `--fast` on a longer doc if you've already translated it once and just need a quick retranslation of a revised source.

## Neighbor context

For every chunk/batch passed to `translate-translate`, the orchestrator attaches `{prev, current, next}` drawn from `units.jsonl` (prev/next may be empty at boundaries). This kills cross-chunk reference drift (DESIGN-agent.md §Accuracy technique #4).

## Resume semantics

`--resume` re-reads `manifest.json` and skips any stage whose output file already exists. Reviewer escalations and partially translated chunks are replayed, not restarted.

## Outputs

- `<input>.<lang>.<ext>` for each target language (Flow A) — next to the source file, source file untouched.
- For xlsx (Flow B), target columns filled in-place in a copy: `<input>.translated.xlsx`.
- `.translate-runs/<run-id>/` retained for audit.
- Stdout summary: `{run_id, outputs, escalations, wall_seconds}`.

## Do not

- Touch the source file directly — all output goes to a sibling file.
- Run analyzer / resolver / glossary per language — they're document-level, shared across languages in the same run.
- Stream partial chunk drafts back to the user — they ride on disk; user sees the final file.
