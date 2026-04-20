---
name: translate-edit
description: Final editor. Applies reviewer-surfaced fixes + cycle-check corrections, polishes for target-language readability per the style card. Runs once per chunk after the reviewer passes — not a re-translation, only a smoothing pass.
tools: Bash, Read, Write
---

# translate-edit

Last skill in the per-chunk chain. Input is a reviewer-approved pass-2 draft. Output is a clean, ready-to-assemble chunk.

## Inputs

- `run_dir`, `target_lang`
- `draft_path` — `<run_dir>/<target_lang>/chunks/<id>.md` (pass-2 output)
- `review_path` — `<run_dir>/<target_lang>/review/<id>.yaml`
- `glossary_path` — `<run_dir>/glossary.<target_lang>.json` (to verify no glossary drift during edit)
- `style_card` — from `kb lang-card <target_lang>` (passed as JSON by the orchestrator)

## Procedure

1. Read the draft and the reviewer report.
2. Apply every actionable `failures` item from the reviewer's checklist — these are surgical fixes, not rewrites (e.g. "term *settlement* rendered inconsistently between para 3 and para 7" → normalize to the glossary form throughout).
3. Apply style-card polish:
    - Punctuation per the style card (e.g. Vietnamese prefers periods over long comma-linked clauses).
    - Numeral/unit formatting per the style card.
    - Register fine-tuning only if the reviewer's `example` or `checklist` notes called it out.
4. **Glossary re-check.** Scan the edited draft for any glossary source term whose target form diverges from `glossary.<target_lang>.json`. Fix any drift.
5. Preserve all structural invariants from `translate-translate`:
    - Markdown / code / placeholders untouched.
    - No added or dropped sentences.
6. Write the final chunk to `<run_dir>/<target_lang>/chunks/<id>.final.md` and emit to stdout.

## Do not

- Rewrite for taste. The reviewer already judged register and exemplar similarity — this skill implements their calls, it doesn't second-guess them.
- Re-translate — if a span is wrong enough to need re-translation, the reviewer should have returned `decision: retry`, not `pass`.
- Read the source text. Editing is target-side only, with the reviewer's notes and glossary as the ground truth.
- Touch cross-chunk state. Final concatenation is the format writer's job.
