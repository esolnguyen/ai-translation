# ai-translation

Multi-agent translation backed by a curated knowledge base. Two translation
paths (RAG via the Claude Agent SDK, Agent via Claude Code skills) share
the same vault + indexer + retrieval API.

- `DESIGN-knowledge.md`: knowledge base (vault + indexing + retrieval)
- `DESIGN-rag.md`: programmatic Python pipeline
- `DESIGN-agent.md`: Claude Code skills + subagents pipeline
- `PLAN-knowledge.md`: the current build plan for the knowledge base
- `src/knowledge/README.md`: package-level usage (CLI, env vars, Python API)

## Repository layout

```
ai-translation/
├── DESIGN-*.md, PLAN-*.md         design + plan docs
├── pyproject.toml
├── src/knowledge/                 the knowledge-base package (indexer, retrieval, CLI)
├── tests/                         unit tests + fixture vault
│
├── sources/                       your input docs (PDF/DOCX/HTML), gitignored
│
├── vault/                         Obsidian vault (SOURCE OF TRUTH)
│   ├── INDEX.md                   top-level MOC + Dataview review queue
│   ├── domains/<domain>/<topic>.md
│   ├── examples/<src>-<tgt>/<domain>/<id>.md
│   ├── glossary/terms/<term>.md
│   ├── languages/<lang>.md
│   └── entities/<name>.md
│
└── .kb/                           derived stores, gitignored; rebuild via `translate kb index`
    ├── chroma/                    vector DB
    ├── glossary.json
    ├── entities.json
    └── languages.json
```

The vault is the source of truth; `.kb/` is derived, so never edit it
directly. Per-user vault notes are gitignored; structural files (`INDEX.md`
templates, `.gitkeep`, `.obsidian/`) are tracked.

## Building knowledge from a PDF

The automated `translate kb extract <pdf>` command is on the roadmap but not
built yet. Until it lands, the workflow is Claude-assisted-manual.

### 1. Drop the source document

```
sources/handbook.pdf
```

`sources/` is gitignored, so raw PDFs never enter the repo history.

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
ascending, so weakest extractions float up.

Edit as you go. When a note is solid, flip its frontmatter:

```yaml
status: approved
```

### 4. Index approved notes

```bash
export KB_VAULT=./vault
export KB_STORE_PATH=./.kb
translate kb index
```

Prints a sync report (added / updated / removed per collection). Re-run
any time. Differential sync purges chunks for demoted or deleted notes.

### 5. Query the retrieval API

```bash
translate kb search "contract termination" --domain legal --k 5
translate kb examples query @sources/chunk.txt --src en --tgt ja --domain legal --k 3
translate kb glossary settlement --target ja
translate kb lang-card ja
translate kb entity Apple
```

Every command returns JSON so the translation paths can parse it without
adapters.

### Seeding golden examples

Aside from extraction, you can hand-seed a source → target pair:

```bash
translate kb examples add src.txt tgt.txt --src en --tgt ja --domain legal
```

Writes a `needs-review` note under `vault/examples/en-ja/legal/`. Review
and approve, then re-run `translate kb index`.

## Setup

```bash
pip install -e '.[dev]'
PYTHONPATH=src pytest tests/     # 26 tests, no network or model weights
```

See `src/knowledge/README.md` for the full CLI surface, env vars, and
Python API.

## Installing skills + agents into a host

The pipeline ships as skills (`src/agents/skills/`) and orchestrator
agents (`src/agents/*.md`). Install them into **Claude Code** or
**Kiro** with one command. The installer symlinks back to `src/agents/`,
so edits flow through without re-running it.

```bash
# Claude Code, project scope (<cwd>/.claude/)
translate install claude

# Kiro, project scope (<cwd>/.kiro/)
translate install kiro

# User scope instead of project scope
translate install kiro --scope user

# Overwrite existing non-symlink files (default: back them up)
translate install kiro --force
```

What lands where:

| Host   | Layout                                                                 |
|--------|------------------------------------------------------------------------|
| Claude | `.claude/skills/<skill>/`, `.claude/agents/<name>.md`                  |
| Kiro   | `.kiro/skills/<skill>/`, `.kiro/agents/<name>.{md,json}`               |

Kiro has no slash-command surface, so the `translate` orchestrator is
registered as a Kiro **agent** (`.kiro/agents/translate.json`) with every
sibling skill attached as a resource. Launch it via `kiro-cli --agent
translate` or pick it from the agent TUI. The two subagents
(`translation-lang-worker`, `translation-reviewer`) are installed the
same way so the orchestrator can delegate to them.

### One-shot bootstrap

`scripts/install.sh [claude|kiro|both]` wraps the above: installs the
`translate` CLI in editable mode, runs `translate install <target>`,
builds the vector index if `.kb/` is empty, and smoke-tests retrieval.

## Running in Docker

Docker packages the RAG pipeline (CLI + `translate-api` HTTP server) only.
The `src/agents/` tree is intentionally excluded (via `.dockerignore`)
because those are Claude Code / Kiro skills that run on a host, not
inside a container.

### Build + run

```bash
cp .env.example .env                # fill in AZURE / GEMINI creds as needed
docker compose build
docker compose up -d                 # API on http://localhost:8000
```

Mounted layout inside the container:

| Host path            | Container path    | Purpose                                 |
|----------------------|-------------------|-----------------------------------------|
| `./vault/`           | `/data/vault`     | Markdown source of truth (bind mount)   |
| `./sources/`         | `/data/sources`   | Input PDFs/DOCX (read-only)             |
| named vol `kb`       | `/data/kb`        | Chroma vector store + JSON indexes      |
| named vol `runs`     | `/data/runs`      | `translate-api` run scratchpads         |
| named vol `hf-cache` | `/hf-cache`       | `bge-m3` embedder weights (~2GB)        |

### Build the index

The vector store is empty on first boot. Populate it from the mounted
vault with the one-shot `indexer` service:

```bash
docker compose run --rm indexer
```

This downloads `bge-m3` into the `hf-cache` volume (first run only) and
writes chunks into the `kb` volume.

### CLI inside the container

```bash
docker compose exec api translate kb search "contract termination" --domain legal --k 5
docker compose exec api translate run /data/sources/handbook.md --to vi
```

### What's excluded from the image

- `src/agents/` (Claude Code / Kiro skills + agents)
- `.claude/`, `.kiro/` (host-specific symlink trees)
- `.env`, `.kb/`, `.translate-runs/`, `vault/`, `sources/` (runtime/user data, mounted instead)
- `tests/`, `examples/`, `test.json`, `scripts/install.sh`
