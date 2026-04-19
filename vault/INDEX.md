---
id: vault-index
status: approved
---

# Knowledge Vault

Source of truth for the AI translation knowledge base. The vector DB and
structured stores under `.kb/` are derived from approved notes in this
vault via `kb index`.

## Review queue

Requires the **Dataview** plugin in Obsidian. Weakest extractions float to
the top so reviewers spend their time where it matters most.

```dataview
TABLE confidence, domain, status, file.mtime as "modified"
FROM "domains" OR "examples" OR "glossary" OR "languages" OR "entities" OR "idioms"
WHERE status = "needs-review"
SORT confidence ASC, file.mtime DESC
```

## Structure

- `domains/` — domain knowledge notes (→ `notes` vector collection)
- `examples/<src>-<tgt>/<domain>/` — golden translation pairs (→ `examples` vector collection, embedded on source)
- `glossary/terms/` — canonical term translations (→ structured store)
- `languages/<lang>.md` — per-target-language style cards (→ structured store)
- `entities/` — proper-noun handling decisions (→ structured store)
- `idioms/<src>-<tgt>/` — idiom pairs (→ `idioms` vector collection)

## Lifecycle

Every note carries `status: needs-review` or `status: approved`. Only
approved notes are indexed. See `DESIGN-knowledge.md` for the note-format
spec and review accelerators.
