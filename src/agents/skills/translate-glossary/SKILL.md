---
name: translate-glossary
description: Builds the run's merged glossary by calling `translate kb glossary` and `translate kb entity` for every candidate term and merging with the resolved-terms scratch file (when present). Writes one authoritative glossary per target language to the run scratchpad.
tools: Bash, Read, Write
---

# translate-glossary

Runs **once per run, per target language**, after `translate-resolve-terms` (Full path) or directly after `translate-analyze` (Fast path — resolver is skipped there, but the lookup chain below is identical). Output is the single glossary the translator reads from — no per-chunk KB lookups during prose translation.

## Inputs

- `run_dir` — `.translate-runs/<run-id>/`
- `units_path` — `<run_dir>/units.jsonl`
- `analysis_path` — `<run_dir>/analysis.json`
- `resolved_path` — `<run_dir>/resolved-terms.<target_lang>.json` (optional — present only on Full path; skip the resolved merge when absent)
- `source_lang`, `target_lang`

## Procedure

1. **Candidate extraction.** From `units.jsonl`, collect:
    - Capitalized tokens or multi-word names → candidate entities.
    - Noun phrases matching the analyzer's `domain` vocabulary → candidate glossary terms. Phrase-level fixed expressions (absolute participials, false-friend collocations) are also glossary entries — keep them as glossary candidates, not a separate category.
    - Dedupe and keep the first occurrence position for context.
2. **KB lookups (one subprocess call per candidate, no vault file reads):**
    - `translate kb glossary "<term>" --target <target_lang>` per candidate term.
    - `translate kb entity "<name>"` per candidate entity.
    - On a miss for a glossary candidate, retry with a stemmed / head-noun form (e.g. `chasis del sensor` → `chasis`) before giving up.
3. **Merge precedence** (highest to lowest):
    1. `resolved-terms.<target_lang>.json` when present — document-level polysemy picks are authoritative.
    2. `translate kb entity` — brand/proper-noun decisions.
    3. `translate kb glossary` — canonical term translations.
    - On conflict (same source term), higher precedence wins; log the loser in `conflicts`.
4. **Unknowns.** Any candidate that returned nothing from both KB calls goes into `unknown_terms` with its first-occurrence context. The orchestrator surfaces these to the user — do **not** invent a translation here.

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

- Write to the vault. New entries are surfaced via `unknown_terms` for the user to approve; they go in via `translate kb glossary add` / `translate kb entity add` — not this skill.
- Do per-chunk lookups later. This glossary is frozen for the run once emitted.
- Translate prose. Term-level only.
- Read vault files directly. Lookups always go through `translate kb` so the warm embedder and index discipline are reused across calls.
