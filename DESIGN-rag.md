# AI Translation — RAG Pipeline

Multi-agent translation built in Python using the Claude Agent SDK, backed by a vector-DB knowledge base. Programmatic, scriptable, CI-friendly.

Related docs:
- [DESIGN-knowledge.md](./DESIGN-knowledge.md) — shared Phase 1 (extract to Obsidian vault)
- [DESIGN-agent.md](./DESIGN-agent.md) — Claude Code agent-driven alternative path

## Goals

- Multi-agent translation pipeline for quality over single-shot translation
- Support `.txt`, `.md`, `.docx`, `.srt`, `.xlsx`
- Preserve source formatting (markdown structure, docx styles, srt timing)
- Consistent terminology via a shared glossary
- Domain awareness via vector retrieval over a curated knowledge base
- Reproducible batch runs — safe to resume, re-run, or schedule

## Phases

- **Phase 1 — Extract to Obsidian.** Shared with the Agent path. See [DESIGN-knowledge.md](./DESIGN-knowledge.md).
- **Phase 2 — Index to vector DB.** Sync approved notes from Obsidian into a vector database + structured glossary + examples store. Output: a retrieval API for the translator.
- **Phase 3 — Translation pipeline.** Python multi-agent pipeline consuming the Phase 2 retrieval API at runtime.

Full flow:

```
source docs          -> [Phase 1: knowledge]  -> Obsidian vault (review)
Obsidian vault       -> [Phase 2: index]      -> vector DB + glossary + examples
translation request  -> [Phase 3: translate]  -> translated output
```

Obsidian is the source of truth. The vector DB is derived — never edit it directly.

## Phase 1 — Extract to Obsidian

Defined in [DESIGN-knowledge.md](./DESIGN-knowledge.md). Input: PDF/DOCX/HTML (knowledge sources — not translation targets). Output: approved markdown notes + MOCs in `vault/` with frontmatter (`status`, `domain`, `tags`, `confidence`). Consumed by Phase 2's indexer.

## Phase 2 — Index to vector DB

Goal: sync approved Obsidian notes into a vector database + structured glossary store, exposing a retrieval API for Phase 3.

### Flow

```
Obsidian vault (status: approved)
    -> [Indexer]   chunk by headings + embed + upsert
        + glossary terms -> structured store (key-value)
        + note bodies    -> vector DB
        + examples       -> vector DB (separate collection)
    -> Retrieval API (search / glossary / examples)
```

### Indexer rules

- Only notes with `status: approved` are indexed — `needs-review` notes are skipped
- Chunk by H2/H3 headings, not fixed token windows
- Stable `id` in frontmatter is the primary key — updates upsert, don't duplicate
- Deleted or demoted notes are purged from the index on the next sync
- Notes are routed to collections by folder: `domains/**` → `notes`, `examples/**` → `examples`, `glossary/**` → structured term store (not vectorized)
- Golden examples are embedded on the **source** field; `source_lang`, `target_lang`, and `domain` are stored as vector metadata for filtering

### Retrieval API

Three surfaces for Phase 3 agents:

- `search(query, domain=None, k=5)` — semantic search over domain note chunks
- `glossary(term, target_lang)` — exact-match term lookup with canonical translation
- `examples(source_text, source_lang, target_lang, domain=None, k=3)` — most similar golden source → target pairs for few-shot prompting

### Phase 2 deliverables

1. `kb index` — full sync of approved notes, examples, and glossary terms
2. `kb index --watch` — incremental sync on vault changes
3. Retrieval API (`search`, `glossary`, `examples`) with a CLI smoke-test command
4. Sync report: added / updated / removed counts per collection per run

## Phase 3 — Translation pipeline

### Shared multi-agent pipeline

Both flows below use the same pipeline. Only the input adapter and output writer differ.

1. **Analyzer** — detects domain, tone, audience from input; queries `search()` for top-k matching domain notes as context
2. **Glossary Builder** — extracts recurring terms + proper nouns; for known terms uses `glossary()`, for new terms decides canonical translations and (optionally) emits them back to the vault as `needs-review`
3. **Translator** — translates units using glossary + analyzer notes + top-k `examples()` as few-shot anchors
4. **Reviewer** — checks fidelity, consistency with glossary, tone
5. **Editor** — applies reviewer fixes and polishes for target-language readers

### Flow A — Text files (file-to-file)

```
input.{txt,md,docx,srt}
    -> [Format Parser] extract translatable units + preserve structure
    -> [Multi-agent pipeline] translate units
    -> [Format Writer] rebuild file with translated units
    -> output.{txt,md,docx,srt}
```

Format-specific handling:

- **`.txt`** — translate full content; chunk if long
- **`.md`** — parse to AST, translate text nodes only; leave code blocks, URLs, and front-matter untouched
- **`.docx`** — use `python-docx`; extract runs per paragraph, translate while preserving bold/italic/styles, rewrite
- **`.srt`** — parse into cues; translate dialogue only, keep indices and timestamps, respect ~42 char/line subtitle limit

Output filename convention: `input.{lang}.ext` (e.g., `readme.ja.md`). Original file is never modified.

### Flow B — Excel template (in-place column fill)

Template has the source language column filled; target language columns are empty and must be populated.

```
template.xlsx  (source col filled, target cols empty)
    -> [Excel Parser] read source col + detect empty target cols
    -> [Multi-agent pipeline] translate per target language (parallel)
    -> [Excel Writer] write results into the right column cells
    -> template.xlsx  (same file, target columns populated)
```

Why multi-agent matters more here: Excel cells are short strings with zero surrounding context (e.g., "Home", "Save", "Apple"). The Analyzer + retrieval calls provide the context a Translator needs to disambiguate.

Properties:

- Preserves all other sheet content (styles, formulas, other sheets)
- Idempotent — cells already filled are skipped, safe to re-run
- Target languages run in parallel, sharing a glossary built once upfront
- Batching: ~30 rows per translator call (balance of cost vs. consistency)

## Architecture

```
kb/
  core/                    framework-free library (no CLI, HTTP, or agent-SDK imports)
    extractor.py           docs -> markdown notes + MOCs
    indexer.py             approved notes -> chunks -> vector DB
    store.py               vector DB client behind a `Store` protocol
    glossary.py            structured term store (JSON / SQLite)
    examples.py            golden example ingestion + embedding
    retrieval.py           search / glossary / examples API
  cli/                     `kb ...` commands — thin wrapper over core
  vault/                   Obsidian vault (contents gitignored, .obsidian tracked)

adapters/
  txt.py     parse / write
  md.py      parse / write (AST-aware)
  docx.py    parse / write (preserve runs)
  srt.py     parse / write (preserve timing)
  xlsx.py    parse / write (column-based, in-place)

pipeline/
  analyzer.py
  glossary.py
  translator.py
  reviewer.py
  editor.py

router.py    dispatches file -> adapter -> pipeline -> adapter
```

The pipeline is format-agnostic. Adapters convert files into translatable units and back. Pipeline agents import `kb.core.retrieval` directly — no CLI shell-out in the hot path.

### Reuse rules (keep the core thin)

- No CLI parsing, HTTP handlers, or agent-SDK imports inside `kb/core/`
- Vector store behind a `Store` protocol — swap Chroma ↔ LanceDB ↔ Qdrant without touching callers
- Embedder behind an `Embedder` protocol — swap providers without touching callers
- All public functions return plain data (dataclasses / dicts), not framework-specific objects

## Key design decisions

- **Excel batch size:** start at 30 rows per translator call
- **Languages in parallel:** yes, with a shared glossary built once upfront
- **Excel library:** `openpyxl` (preserves styles/formulas) over `pandas` (loses formatting)
- **Markdown:** parse with an AST library (e.g., `markdown-it-py`) to avoid translating code/URLs
- **Glossary persistence:** JSON per project, reusable across runs, user-editable
- **Vector DB:** TBD — Chroma (simplest), LanceDB (embedded, fast), or Qdrant (most features)
- **Embedder:** TBD — OpenAI `text-embedding-3-small`, Voyage, or local `bge-m3`

## Stack

- **Python** — best ecosystem for `.docx` (`python-docx`), `.xlsx` (`openpyxl`), `.srt` (`pysrt`), `.md` (`markdown-it-py`)
- **Claude Agent SDK** — orchestrates the multi-agent pipeline
- **CLI first** — `translate file.xlsx --to ja,fr,de`; web UI later if needed

## Open questions

1. Should users be able to pre-seed the glossary (common in localization workflows)?
2. Do we need a "dry-run" mode that shows the glossary + a sample translation before running the full file?
3. Progress/cost reporting — per file, per language, or both?
