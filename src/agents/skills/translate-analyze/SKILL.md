---
name: translate-analyze
description: Document analyzer. Reads the extracted units, calls `translate kb search` for semantic domain context, and produces a domain prime (domain, sub-domain, tone, register, audience, retrieved note ids). Output is injected verbatim into later skills — this is the single most important prompt anchor in the pipeline.
tools: Bash, Read, Write
---

# translate-analyze

First skill in the chain. Runs **once per run**, before resolver / glossary / translator.

## Inputs

- `run_dir` — `.translate-runs/<run-id>/`
- `units_path` — `<run_dir>/units.jsonl`
- `source_lang` — from the orchestrator

Optional:
- `domain_hint` — user-supplied domain guess (e.g. `legal`, `automotive`). Biases `translate kb search` but is not authoritative.

## Procedure

1. Read the first ~2000 tokens of `units.jsonl` — enough to establish domain / register without dragging the whole document through context. If the document is shorter, read all of it.
2. Summarize the corpus in one paragraph (**internal only** — do not emit). Use the summary as the query for KB search.
3. `translate kb search "<summary>" --domain <domain_hint if any> --k 5` — parse the JSON response for the top-5 note ids and their excerpts.
4. Decide:
    - `domain` — single canonical domain string (prefer one that matches the vault's `domains/<domain>/` folder names). If none fits, `general`.
    - `sub_domain` — narrower slice (e.g. domain=`automotive`, sub_domain=`brake-service-bulletin`).
    - `tone` — one of `formal | neutral | casual | marketing`.
    - `register` — one of `technical | legal | encyclopedic | procedural | narrative | conversational | advertorial`.
    - `audience` — short phrase (e.g. `dealer technicians`, `retail consumers`, `compliance officers`).
    - `notes` — one- or two-sentence rationale referencing the retrieved note ids.
5. Sanity check: if `translate kb search` returned nothing in the claimed domain, downgrade `domain` to `general` and note the miss — callers will see the weak grounding.

## Output

Write `<run_dir>/analysis.json`:

```json
{
  "domain": "automotive",
  "sub_domain": "brake-service-bulletin",
  "tone": "formal",
  "register": "technical",
  "audience": "dealer technicians performing PDS inspections",
  "source_lang": "en",
  "retrieved_notes": [
    {"id": "pre-delivery-service", "score": 0.81, "excerpt": "..."},
    {"id": "dc-cut-fuse",          "score": 0.78, "excerpt": "..."}
  ],
  "notes": "Matches Toyota TSB register; retrieved notes describe PDS procedure and D/C cut fuse reinstallation."
}
```

Emit the same JSON to stdout so the orchestrator can inline it into the translator's system prompt **verbatim** (DESIGN-agent.md §Accuracy technique #2 — do not paraphrase).

## Do not

- Read vault files directly. All knowledge access is via `translate kb`.
- Fabricate a domain when `translate kb search` returns nothing relevant — fall back to `general` and say so.
- Summarize the retrieved notes beyond `excerpt` — callers want the prime lean.
- Re-run per chunk. This is document-level state.
