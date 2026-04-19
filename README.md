# ai-translation

Multi-agent translation backed by a curated knowledge base. Two translation
paths (RAG via the Claude Agent SDK, Agent via Claude Code skills) share
the same vault + indexer + retrieval API.

- `DESIGN-knowledge.md` — knowledge base (vault + indexing + retrieval)
- `DESIGN-rag.md` — programmatic Python pipeline
- `DESIGN-agent.md` — Claude Code skills + subagents pipeline
- `PLAN-knowledge.md` — the current build plan for the knowledge base
- `src/knowledge/README.md` — package-level usage (CLI, env vars, Python API)

## Repository layout

```
ai-translation/
├── DESIGN-*.md, PLAN-*.md         design + plan docs
├── pyproject.toml
├── src/knowledge/                 the knowledge-base package (indexer, retrieval, CLI)
├── tests/                         unit tests + fixture vault
│
├── sources/                       your input docs (PDF/DOCX/HTML) — gitignored
│
├── vault/                         Obsidian vault — SOURCE OF TRUTH
│   ├── INDEX.md                   top-level MOC + Dataview review queue
│   ├── domains/<domain>/<topic>.md
│   ├── examples/<src>-<tgt>/<domain>/<id>.md
│   ├── glossary/terms/<term>.md
│   ├── languages/<lang>.md
│   ├── entities/<name>.md
│   └── idioms/<src>-<tgt>/<id>.md
│
└── .kb/                           derived stores — gitignored, rebuild via `kb index`
    ├── chroma/                    vector DB
    ├── glossary.json
    ├── entities.json
    └── languages.json
```

The vault is the source of truth; `.kb/` is derived — never edit it
directly. Per-user vault notes are gitignored; structural files (`INDEX.md`
templates, `.gitkeep`, `.obsidian/`) are tracked.

## Building knowledge from a PDF

The automated `kb extract <pdf>` command is on the roadmap but not built
yet. Until it lands, the workflow is Claude-assisted-manual.

### 1. Drop the source document

```
sources/handbook.pdf
```

`sources/` is gitignored — raw PDFs never enter the repo history.

### 2. Draft notes from the PDF

Open a Claude Code session in this repo and prompt:

> Read `sources/handbook.pdf` and draft domain notes under
> `vault/domains/<domain>/`. One note per topic. Frontmatter per
> `DESIGN-knowledge.md` (`id`, `source: handbook.pdf#p12-18`, `domain`,
> `status: needs-review`, `confidence`, `tags`, `related`). Open each
> note with a one-paragraph summary so I can skim-review.

Claude reads the PDF directly, splits it into topic-sized notes, fills the
frontmatter, and cross-links related notes with wikilinks.

### 3. Review in Obsidian

Open `vault/` in Obsidian (install the **Dataview** plugin). The root
`INDEX.md` surfaces every `needs-review` note sorted by `confidence`
ascending — weakest extractions float up.

Edit as you go. When a note is solid, flip its frontmatter:

```yaml
status: approved
```

### 4. Index approved notes

```bash
export KB_VAULT=./vault
export KB_STORE_PATH=./.kb
kb index
```

Prints a sync report (added / updated / removed per collection). Re-run
any time. Differential sync purges chunks for demoted or deleted notes.

### 5. Query the retrieval API

```bash
kb search "contract termination" --domain legal --k 5
kb examples query @sources/chunk.txt --src en --tgt ja --domain legal --k 3
kb glossary settlement --target ja
kb lang-card ja
kb entity Apple
kb idiom "kick the bucket" --src en --tgt vi
```

Every command returns JSON so the translation paths can parse it without
adapters.

### Seeding golden examples

Aside from extraction, you can hand-seed a source → target pair:

```bash
kb examples add src.txt tgt.txt --src en --tgt ja --domain legal
```

Writes a `needs-review` note under `vault/examples/en-ja/legal/`. Review
and approve, then re-run `kb index`.

## Setup

```bash
pip install -e '.[dev]'
PYTHONPATH=src pytest tests/     # 26 tests, no network or model weights
```

See `src/knowledge/README.md` for the full CLI surface, env vars, and
Python API.
