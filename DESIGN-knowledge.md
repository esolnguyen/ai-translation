# AI Translation — Knowledge Base (Phase 1)

The shared knowledge layer used by both translation paths. An LLM extracts source documents (PDF/DOCX/HTML) into a reviewable Obsidian vault. The vault is the single source of truth.

Consumed by:
- [DESIGN-rag.md](./DESIGN-rag.md) — indexes the vault into a vector DB
- [DESIGN-agent.md](./DESIGN-agent.md) — reads the vault directly via Claude Code subagents

## Goals

- Turn unstructured source documents into structured, reviewable markdown notes
- Make review fast — the LLM generates both content notes AND index/MOC files so users review top-down, not file-by-file
- Capture golden translation examples so downstream translators can few-shot from them
- Keep the vault format neutral — no assumptions about how it will be consumed later

## Flow

```
source docs (pdf / docx / html)
    -> [Extractor]   LLM produces structured markdown notes + MOCs
    -> Obsidian vault (status: needs-review)
    -> user reviews, edits, flips status: approved
```

Downstream consumers read only notes where `status: approved`.

## Vault structure

```
vault/
  INDEX.md                    top-level MOC, grouped by domain
  domains/
    <domain>/
      INDEX.md                domain MOC, links all notes in the domain
      <topic>.md
  glossary/
    INDEX.md                  alphabetical term index
    terms/
      <term>.md
  examples/
    INDEX.md                  MOC for golden translation examples
    <src>-<tgt>/<domain>/
      <example-id>.md         curated source -> target pair
```

## Note format

Every generated note carries frontmatter:

```yaml
---
id: legal-contract-terms        # stable ID; survives renames
source: contracts.pdf#p12-18    # provenance for spot-checking
domain: legal
status: needs-review            # needs-review | approved
confidence: 0.85                # LLM self-score, 0-1
tags: [contract, terms]
related: [[jurisdiction]], [[settlement]]
---
```

Each note body opens with a one-paragraph summary so reviewers can skim and approve in seconds.

## Review accelerators

- `status: needs-review` + Obsidian Dataview → instant review queue
- Sort by `confidence` ascending → review weakest extractions first
- Wikilinks between related notes → broken links expose extraction gaps
- Source references in frontmatter → jump straight to the original page

## Golden translation examples

Curated source → target pairs that exemplify preferred style, tone, and terminology. Seeded manually or imported from prior approved translations. Same lifecycle as other notes (`needs-review` → `approved`).

```yaml
---
id: ex-legal-contract-001
source_lang: en
target_lang: ja
domain: legal
status: approved                # needs-review | approved
tags: [contract, formal]
---

## Source
...source text...

## Target
...target translation...

## Notes
Why this pair is exemplary — term choices, tone decisions, edge cases.
```

Downstream translators retrieve the top-k most similar pairs as few-shot anchors (semantic search in the RAG path, folder/tag filtering in the Agent path).

## Extraction

The extractor reads a source document and writes one or more markdown notes into the vault with `status: needs-review`. It can be invoked two ways — both produce the same vault output:

- **Python CLI** — `kb extract <file-or-dir>` (used by the RAG path; can also be called from Claude Code via Bash)
- **Claude Code skill** — `/extract <doc>` (used by the Agent path; calls the same underlying code or re-implements with Claude's tool use)

Extractor responsibilities:

- Split source into topic-sized notes, not one giant dump
- Generate domain / topic MOCs (`INDEX.md` at each level)
- Fill frontmatter including `source` provenance and a `confidence` self-score
- Cross-link related notes with wikilinks

Prompts are tuned per source type (PDF vs DOCX vs HTML) since the extraction signal differs.

## Seeding golden examples

- **Python CLI** — `kb examples add <source-file> <target-file> --src en --tgt ja --domain legal`
- **Claude Code skill** — `/seed-example <source-file> <target-file> --src en --tgt ja --domain legal`

Both write a new note into `vault/examples/<src>-<tgt>/<domain>/` with `status: needs-review` until the user approves.

## Phase 1 deliverables

1. Vault scaffolded with `INDEX.md` template and Dataview review queries
2. Extraction tool (Python CLI, Claude Code skill, or both) that writes `needs-review` notes
3. Example-seeding tool (CLI or skill) for golden pairs
4. Extractor prompts tuned per source type (PDF / DOCX / HTML)

## Open questions

1. Is the vault checked into the repo (contents gitignored, `.obsidian/` tracked) or stored outside?
2. Start with PDF only, or PDF + DOCX + HTML from day one?
3. Should extraction always go via the Python CLI (shared with RAG path) or should the Agent path own its own `/extract` skill implementation?
