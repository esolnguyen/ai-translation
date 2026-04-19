---
name: translate-glossary
description: Builds the run's merged glossary. Calls `kb glossary`, `kb entity`, and `kb idiom` for every candidate term in the source, merges with the resolved-terms scratch file, and writes one authoritative glossary per target language to the run scratchpad.
tools: Bash, Read, Write
---

# translate-glossary

Runs **once per run, per target language**, after `translate-resolve-terms` (Full path) or directly after `translate-analyze` (Fast path). Output is the single glossary the translator reads from — no per-chunk KB lookups during prose translation.

## Inputs

- `run_dir` — `.translate-runs/<run-id>/`
- `units_path` — `<run_dir>/units.jsonl`
- `analysis_path` — `<run_dir>/analysis.json`
- `resolved_path` — `<run_dir>/resolved-terms.<target_lang>.json` **(Full path only; omitted on Fast path)**
- `source_lang`, `target_lang`
- `mode` — `full` (default) or `fast`. On `fast`, skip merge-precedence step #1 (resolved-terms) and build the glossary directly from KB lookups; the translator's single pass handles any polysemy inline.

## Procedure

1. **Candidate extraction.** From `units.jsonl`, collect:
    - Capitalized tokens or multi-word names → candidate entities.
    - Noun phrases matching the analyzer's `domain` vocabulary → candidate glossary terms.
    - Common idiom patterns (verb-noun collocations, fixed expressions) → candidate idioms.
    - Dedupe and keep the first occurrence position for context.
2. **KB lookups (batched where possible):**
    - `kb glossary "<term>" --target <target_lang>` per candidate term.
    - `kb entity "<name>"` per candidate entity.
    - `kb idiom "<phrase>" --src <source_lang> --tgt <target_lang>` per candidate idiom.
3. **Merge precedence** (highest to lowest):
    1. `resolved-terms.<target_lang>.json` — document-level polysemy picks are authoritative.
    2. `kb entity` — brand/proper-noun decisions.
    3. `kb glossary` — canonical term translations.
    4. `kb idiom` — idiom renderings.
    - On conflict (same source term), higher precedence wins; log the loser in `conflicts`.
4. **Unknowns.** Any candidate that returned nothing from all three KB calls goes into `unknown_terms` with its first-occurrence context. The orchestrator surfaces these to the user — do **not** invent a translation here.

## Output

Write `<run_dir>/glossary.<target_lang>.json`:

```json
{
  "source_lang": "en",
  "target_lang": "vi",
  "domain": "automotive",
  "entries": [
    {"source": "brake pad",  "target": "má phanh",    "kind": "glossary", "kb_id": "glossary-brake-pad"},
    {"source": "brake disc", "target": "đĩa phanh",   "kind": "glossary", "kb_id": "glossary-brake-disc"},
    {"source": "Toyota",     "target": "Toyota",      "kind": "entity",   "kb_id": "entity-toyota", "rule": "keep-as-is"},
    {"source": "bed in",     "target": "rà phanh",    "kind": "idiom",    "kb_id": "idiom-en-vi-bed-in"},
    {"source": "disc",       "target": "đĩa phanh",   "kind": "resolved", "rationale": "brake context"}
  ],
  "unknown_terms": [
    {"source": "QuietCast", "first_seen": "unit:042", "suggestion": "keep-as-is (product sub-brand?)"}
  ],
  "conflicts": []
}
```

Emit to stdout.

## Do not

- Write to the vault. New entries are surfaced via `unknown_terms` for the user to approve; they go in via `kb glossary add` / `kb entity add` — not this skill.
- Do per-chunk lookups later. This glossary is frozen for the run once emitted.
- Translate prose. Term-level only.
