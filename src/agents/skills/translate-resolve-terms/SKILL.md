---
name: translate-resolve-terms
description: Document-level polysemy lock. Scans the full source for words with multiple common senses in the target language, picks the right sense once per document using the domain prime, and writes the choices to the run's scratch glossary so the translator can't drift between paragraphs.
tools: Bash, Read, Write
---

# translate-resolve-terms

Runs **once per document, per target language**, before any prose is translated. The #3 accuracy lever in DESIGN-agent.md.

## Inputs

- `run_dir` — `.translate-runs/<run-id>/`
- `units_path` — `<run_dir>/units.jsonl`
- `analysis_path` — `<run_dir>/analysis.json`
- `source_lang`, `target_lang`

## Procedure

1. Read `units.jsonl` (full document — polysemy lock needs global context) and `analysis.json` (for `domain`, `sub_domain`, `register`).
2. Identify polysemy candidates — source words/phrases that have ≥2 common senses mapping to different target-language words. Heuristics:
    - High-frequency ambiguous nouns (`bank`, `strike`, `run`, `table`, `mouse`, `seal`).
    - Domain-overloaded terms (`disc`, `shoe`, `pad`, `fluid` — medical vs automotive).
    - Words that appear multiple times in this document in what **might** be different senses.
    - Do **not** burn tokens on unambiguous words; a short, high-signal list beats exhaustive.
3. For each candidate, look it up:
    - `translate kb glossary "<term>" --target <target_lang>` — if the vault already has a canonical pick, that's authoritative; record and move on.
    - `translate kb entity "<term>"` — if it's a known proper noun, defer to the entity decision.
    - `translate kb search "<term>" --domain <domain> --k 3` — to see how the term is used in the domain's vault notes.
4. Decide one sense per candidate using the analyzer's `domain` + `sub_domain` + `register`. Record the rationale briefly — future-you needs to know *why* `strike` was locked to `cú đá`, not `đình công`.
5. Cache invalidation: hash the source text (sha256 of `units.jsonl`). If `<run_dir>/resolved-terms.json` already exists with a matching hash, reuse it and skip.

## Output

Write `<run_dir>/resolved-terms.<target_lang>.json`:

```json
{
  "source_hash": "sha256:...",
  "source_lang": "en",
  "target_lang": "vi",
  "domain": "automotive",
  "resolutions": [
    {
      "term": "disc",
      "sense": "brake disc (rotor)",
      "target": "đĩa phanh",
      "rationale": "automotive/brake-service-bulletin context; source mentions pad replacement",
      "source_kb": ["glossary-brake-disc"]
    },
    {
      "term": "shoe",
      "sense": "brake shoe (drum brake)",
      "target": "guốc phanh",
      "rationale": "document references rear drum brakes on the Corolla",
      "source_kb": ["glossary-brake-shoe"]
    }
  ]
}
```

Emit to stdout so the orchestrator can hand it straight to `translate-glossary`.

## Do not

- Resolve every word — only ambiguous ones. Non-polysemous terms go through `translate-glossary` unchanged.
- Translate prose here — this skill only locks **term-level** choices.
- Modify the vault. New terms surfaced by this step are passed to the user (and optionally queued for `translate kb glossary add`) — they're never auto-written.
- Run per chunk. Document-level state, runs once.
