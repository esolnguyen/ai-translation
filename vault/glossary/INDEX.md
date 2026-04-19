---
id: glossary-index
status: approved
---

# Glossary

Canonical term translations. Indexed into the structured glossary store,
not the vector DB. Each term under `terms/` carries frontmatter `term`,
`domain`, and a body with per-target-language translations.

```dataview
TABLE domain, status, file.mtime as "modified"
FROM "glossary/terms"
SORT file.name ASC
```
