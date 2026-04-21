---
name: translate-glossary
description: Builds the run's merged glossary. On Full path, calls `translate kb glossary` and `translate kb entity` for every candidate term and merges with the resolved-terms scratch file. On Fast path, reads vault files directly (Glob + Read on `vault/{glossary,entities}/`) — same output schema, no embedder cold-start. Writes one authoritative glossary per target language to the run scratchpad.
tools: Bash, Read, Write, Glob, Grep
---

# translate-glossary

Runs **once per run, per target language**, after `translate-resolve-terms` (Full path) or directly after `translate-analyze` (Fast path). Output is the single glossary the translator reads from — no per-chunk KB lookups during prose translation.

## Inputs

- `run_dir` — `.translate-runs/<run-id>/`
- `units_path` — `<run_dir>/units.jsonl`
- `analysis_path` — `<run_dir>/analysis.json`
- `resolved_path` — `<run_dir>/resolved-terms.<target_lang>.json` **(Full path only; omitted on Fast path)**
- `source_lang`, `target_lang`
- `mode` — `full` (default) or `fast`. On `fast`, skip resolved-terms merge **and** skip the `translate kb` subprocess chain entirely — read vault notes directly. Output schema is identical either way, so the translator's system prompt is unchanged.
- `vault_root` — default `$KB_VAULT` or `./vault`. Only consulted in `fast` mode.

## Procedure — Full mode

1. **Candidate extraction.** From `units.jsonl`, collect:
    - Capitalized tokens or multi-word names → candidate entities.
    - Noun phrases matching the analyzer's `domain` vocabulary → candidate glossary terms. Phrase-level fixed expressions (absolute participials, false-friend collocations) are also glossary entries — keep them as glossary candidates, not a separate category.
    - Dedupe and keep the first occurrence position for context.
2. **KB lookups (batched where possible):**
    - `translate kb glossary "<term>" --target <target_lang>` per candidate term.
    - `translate kb entity "<name>"` per candidate entity.
3. **Merge precedence** (highest to lowest):
    1. `resolved-terms.<target_lang>.json` — document-level polysemy picks are authoritative.
    2. `translate kb entity` — brand/proper-noun decisions.
    3. `translate kb glossary` — canonical term translations.
    - On conflict (same source term), higher precedence wins; log the loser in `conflicts`.
4. **Unknowns.** Any candidate that returned nothing from both KB calls goes into `unknown_terms` with its first-occurrence context. The orchestrator surfaces these to the user — do **not** invent a translation here.

## Procedure — Fast mode

Designed for small vaults (≲200 notes total). Replaces every `translate kb` subprocess — each of which re-loads the bge-m3 embedder from scratch on cold start (~10s for `search`) — with direct filesystem reads. Quality parity: the `translate kb glossary/entity` commands are already exact-key lookups against a JSON store derived from these same markdown files, so direct reads return the same data with no approximation.

1. **Load vault surfaces (single pass, no subprocess):**
    - `Glob <vault_root>/glossary/terms/*.md` → Read each. Parse frontmatter `term` + body `## Translations` section. Build `glossary_index: { normalize(term) → {id, term, translations: {lang: rendering}, body_excerpt, notes, path} }`.
    - `Glob <vault_root>/entities/*.md` → Read each. Parse frontmatter `name` (or fall back to filename stem) and body. Build `entity_index: { normalize(name) → {id, name, body_excerpt, rule, path} }`.
    - Read `<vault_root>/languages/<target_lang>.md` once — this is style-card territory, consumed by the translator via `translate kb lang-card`, not this skill. Don't include it in the glossary output; only mentioned here so you know not to duplicate it.
2. **Candidate extraction** — same rules as Full mode (capitalized tokens, domain noun phrases, phrase-level fixed expressions). Dedupe, keep first-occurrence position.
3. **Match candidates against vault indices:**
    - For each glossary candidate: lookup `glossary_index[normalize(candidate)]`. On miss, also try stemmed / head-noun match (e.g. `chasis del sensor` → try `chasis`). On hit, emit `{source, target: translations[target_lang], kind: "glossary", kb_id: id}`.
    - For each entity candidate: lookup `entity_index[normalize(candidate)]`. On hit, emit `{source, target, kind: "entity", kb_id: id, rule}`.
4. **Merge precedence** (highest to lowest): entity → glossary. On same-source conflict, higher precedence wins; log the loser in `conflicts`.
5. **Unknowns.** Any candidate that missed both indices goes into `unknown_terms` with first-occurrence context. Surface to the user — do **not** invent a translation.

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
- **In Fast mode:** do not shell out to `translate kb glossary` or `translate kb entity` — the whole point of Fast mode is to bypass the subprocess cold-start. If you need data that isn't in `<vault_root>/{glossary,entities}/`, fall back to Full mode instead of mixing paths.
