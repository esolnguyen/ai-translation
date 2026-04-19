# Project rules — ai-translation

These rules are load-bearing. Apply them to every change in this repo.

## Language & typing

- **Python 3.12.** Use modern syntax; do not target older versions.
- **No deprecated `typing` aliases.** Prefer built-ins and `collections.abc`:
  - `list[int]`, `dict[str, X]`, `tuple[X, ...]`, `set[X]` — not `List`, `Dict`, `Tuple`, `Set`.
  - `X | Y`, `X | None` — not `Union[X, Y]`, `Optional[X]`.
  - `from collections.abc import Iterable, Iterator, Mapping, Sequence, Callable` — not from `typing`.
  - `type Alias = ...` (PEP 695) for type aliases; do not use `TypeAlias`.
  - Generics via PEP 695 syntax: `class Foo[T]:` / `def bar[T](x: T) -> T:` — not `TypeVar`.
  - `typing` is still fine for `Protocol`, `TYPE_CHECKING`, `Final`, `ClassVar`, `cast`, `overload`, `Self`.

## File size

- **Hard cap: 500 lines per file.**
- If a file would cross 500 lines, split it before committing. Extract cohesive
  pieces into their own modules under a sibling folder (e.g. `foo.py` → `foo/`
  package with `foo/__init__.py` re-exporting the public surface). Do not split
  arbitrarily — split along seams that already exist (classes, domains, layers).

## Architecture — clean architecture

Layered, dependencies point inward only:

```
domain      ← pure entities + value objects (no I/O, no frameworks)
   ↑
use-cases   ← application logic; orchestrates domain via ports (abstractions)
   ↑
adapters    ← concrete implementations of ports (DB, HTTP, CLI, vector store, LLM)
   ↑
frameworks  ← entry points: CLI, web, scheduled jobs, LangGraph wiring
```

- Domain and use-case layers import **only** from `collections.abc`, stdlib, and
  each other. No `chromadb`, `anthropic`, `pymongo`, `langgraph` imports here.
- Adapters depend on use-case ports, never the other way around.
- Cross-layer calls go through **abstract base classes or Protocols** declared
  in the inner layer.

## OOP, abstractions, SOLID

- Use classes with clear responsibilities; prefer composition over inheritance.
- Define ports as ABCs or `typing.Protocol` in the layer that *consumes* them —
  never next to the concrete implementation.
- **SOLID:**
  - **S** — one reason to change per class. If a class both parses and persists,
    split it.
  - **O** — extend behavior via new subclasses/strategies, not by editing
    switch-chains. New target language or adapter = new class, not a new
    `if lang == ...` branch.
  - **L** — subclasses must be substitutable. No "this subclass raises on
    method X" exceptions.
  - **I** — many small interfaces beat one fat one. A `Reader` and a `Writer`
    are two ports, not one `Adapter` with both.
  - **D** — depend on abstractions. Inject dependencies through constructors;
    do not `import chromadb` inside a use-case.

## Factory pattern

- Every family of interchangeable implementations gets a factory:
  - `make_embedder(name: str) -> Embedder`
  - `make_store(kind: str, **cfg) -> Store`
  - `make_adapter(path: Path) -> Adapter`
  - `make_metric_profile(lang: str) -> MetricProfile`
- Factories live at the edge of their layer (adapters package). Selection keys
  come from config/env, never hardcoded in call sites.
- Call sites receive the abstraction; they never know which concrete class they
  got. No `isinstance` checks on factory output.

## Persistence

- **MongoDB is the database of record** when persistence is needed.
- Access Mongo through a repository port (abstract) in the use-case layer; the
  concrete `MongoRepository` lives in adapters. Use-cases never touch a Mongo
  client directly.
- Chroma (vector DB) and JSON structured stores (`.kb/*.json`) are **not**
  general-purpose storage — they are retrieval backends for the knowledge base.
  Don't repurpose them as the app DB.
- Connection strings and database names come from env/config, never
  hardcoded.

## Code hygiene

- No dead code, no commented-out blocks. Delete it; git remembers.
- No defensive validation inside trusted internal boundaries — validate at
  system edges (CLI args, HTTP input, file formats).
- Docstrings on public surfaces only (class, public method, module). Private
  helpers speak through names.
- Tests mirror the package layout. Unit tests exercise use-cases against fake
  adapters; integration tests exercise concrete adapters.
