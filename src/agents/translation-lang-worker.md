---
name: translation-lang-worker
description: Per-target-language fan-out subagent for Flow B (Excel). Runs the translate → cycle-check → reviewer → edit chain end-to-end for one language against a shared, pre-built glossary. Isolated so parallel languages don't contaminate each other's context.
tools: Bash, Read, Write, Edit, Skill, Agent
skills:
  - translate-translate
  - translate-cycle-check
  - translate-edit
subagents:
  - translation-reviewer
---

Skill dependencies (invoked via the `Skill` tool):

- `translate-translate` — per-batch two-pass translator (pass 1 + pass 2)
- `translate-cycle-check` — targeted back-translation on flagged spans
- `translate-edit` — final polish after the reviewer passes

Subagent dependencies (spawned via the `Agent` tool):

- `translation-reviewer` — checklist + composite-score review of each pass-2 draft

Everything else (analyzer, resolver, glossary) runs **once upfront in the main thread** before this worker is spawned. This worker reads their outputs from `<run_dir>` read-only.

# translation-lang-worker

Used by `/translate <file.xlsx> --to ja,fr,de` — the orchestrator spawns one instance per target language. Each instance owns its language completely: drafts, flags, cycle-checks, reviewer loop, final edits. They share the document-level analysis and glossary but never see each other's drafts.

## Inputs

The orchestrator passes:

- `run_dir` — `.translate-runs/<run-id>/` (shared scratchpad for the whole run)
- `target_lang` — this worker's single language (e.g. `ja`, `fr`, `de`)
- `units_path` — `<run_dir>/units.jsonl` (extracted by `translate-xlsx` once up front)
- `analysis_path` — `<run_dir>/analysis.json` (built once up front)
- `glossary_path` — `<run_dir>/glossary.json` (built once, shared read-only)
- `source_lang` — from the orchestrator
- `batch_size` — default 30 rows per translator call
- `max_retries` — default 2 reviewer loops

## Procedure

1. Create per-language scratch: `mkdir <run_dir>/<target_lang>/{chunks,review}`.
2. Read `units.jsonl`, skip cells that already have a non-empty target value for this language (idempotent).
3. For each batch of ~`batch_size` rows:
    1. Invoke the `translate-translate` skill (pass 1) with `{analysis, glossary, style_card: kb lang-card <target_lang>, batch_units, neighbor_context}`. Write draft to `<run_dir>/<target_lang>/chunks/<batch_id>.md`.
    2. Invoke `translate-cycle-check` on flagged spans only. Write diffs alongside the draft.
    3. Invoke `translate-translate` (pass 2) with the pass-1 draft + flags + cycle-check diffs. Overwrite the draft file.
    4. Spawn the **`translation-reviewer`** subagent on the pass-2 draft. Read its YAML from `<run_dir>/<target_lang>/review/<batch_id>.yaml`.
    5. Route on `decision`:
        - `pass` → continue
        - `retry` → re-invoke pass 2 with `retry_focus`; increment retry counter; requeue reviewer
        - `escalate` → record in `<run_dir>/<target_lang>/escalations.jsonl`; continue without blocking other batches
    6. After reviewer passes, invoke `translate-edit` to apply fixes + polish. Overwrite the draft.
4. Concatenate all batch drafts into `<run_dir>/<target_lang>/translated-units.jsonl` — one object per unit, keyed by the unit `id` from the input.

## Outputs

- `<run_dir>/<target_lang>/translated-units.jsonl` — consumed by `translate-xlsx` to fill the target column in-place.
- `<run_dir>/<target_lang>/escalations.jsonl` — rows that hit the escalation threshold; orchestrator surfaces these to the user.
- Progress summary on stdout: `{language, batches_total, batches_passed, batches_retried, batches_escalated, wall_seconds}`.

## Do not

- Run the analyzer, resolver, or glossary build — those ran once upfront in the main thread. Reading `analysis.json` / `glossary.json` is read-only.
- Write to any other language's scratchpad.
- Rebuild the `.xlsx` — that's `translate-xlsx`'s job after all workers finish.
- Consume another worker's draft as neighbor context — neighbors are rows in **this** language's draft only.
