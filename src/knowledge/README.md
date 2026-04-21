# knowledge

Shared knowledge base for the AI translation system. Syncs approved notes
from an Obsidian vault into a vector DB + structured stores, and exposes a
retrieval API that both translation paths (RAG and Agent) consume.

See `DESIGN-knowledge.md` at the repo root for the full design. This README
covers what's currently implemented in this package.

## Scope

In this build:

- Vault walker, H2/H3 chunker
- Chroma-backed vector store and local (`bge-m3`) embedder
- JSON-backed structured stores for glossary, entities, language cards
- Indexer with differential sync (added / updated / removed counts per collection)
- Retrieval API (`search`, `glossary`, `examples`, `language_card`, `entity`, `idiom`)
- `translate kb` CLI over every retrieval surface, plus `translate kb index` and `translate kb examples add` (subcommands of the unified `translate` dispatcher in `src/clis/`).

Deferred: LLM extractor (`translate kb extract`), `translate kb index --watch`,
Claude Code skills (`/extract`, `/seed-example`).

## Install

```bash
pip install -e .
```

Optional extras: `.[openai]`, `.[extract]`, `.[dev]`.

## Environment

| Var              | Default        | Purpose                                    |
|------------------|----------------|--------------------------------------------|
| `KB_VAULT`       | `./vault`      | Obsidian vault root                        |
| `KB_STORE_PATH`  | `./.kb`        | Where Chroma + JSON stores live            |
| `KB_EMBEDDER`    | `local`        | Embedder backend (`local` only for now)    |
| `KB_EMBEDDER_MODEL` | `BAAI/bge-m3` | Sentence-transformers model id             |

## CLI

Every retrieval command prints JSON on stdout.

```bash
translate kb index                          # sync approved vault notes, human report
translate kb index --json                   # same, JSON report

translate kb search "contract termination" --domain legal --k 5
translate kb examples query @chunk.txt --src en --tgt ja --domain legal --k 3
translate kb examples add src.txt tgt.txt --src en --tgt ja --domain legal
translate kb glossary settlement --target ja
translate kb lang-card ja
translate kb entity Apple
translate kb idiom "kick the bucket" --src en --tgt vi
```

`@file` in the `examples query` source argument reads the source text from
disk instead of treating the argument as a literal string.

## Python

```python
from knowledge.core.retrieval import Retriever

retriever = Retriever.from_env()
hits = retriever.search("contract termination", domain="legal", k=3)
card = retriever.language_card("ja")
```

Returns plain dicts and lists — no backend types leak through the API.

## Layout

```
src/knowledge/
  core/
    models.py          Note, Chunk, Status, NoteKind, load_note
    vault.py           folder-routed walker
    chunker.py         H2/H3 splitting; EXAMPLE/IDIOM source extraction
    store.py           Store protocol + VectorRecord + QueryHit
    embedder.py        Embedder protocol
    stores/chroma.py   Chroma backend
    embedders/local.py sentence-transformers backend (lazy-loaded)
    glossary.py        JSON-backed glossary store
    entities.py        JSON-backed entity store
    languages.py       JSON-backed language-card store
    sync.py            SyncDelta / SyncReport
    indexer.py         Indexer.sync(vault_path) -> SyncReport
    retrieval.py       Retriever
```

The `kb` subcommand is exposed by the unified `translate` dispatcher in
`src/clis/kb.py`, which lazy-imports `knowledge.core`. This package no
longer ships its own CLI module.

Swap Chroma for another vector DB by implementing the `Store` protocol in
`core/store.py` and updating `Retriever.from_env`. Same pattern for the
embedder via `Embedder` in `core/embedder.py`.

## Tests

```bash
PYTHONPATH=src pytest tests/
```

Tests use an in-memory `Store` and a hash-based `FakeEmbedder`, so no real
model weights or Chroma instances are required.
