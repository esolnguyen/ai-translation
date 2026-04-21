---
id: examples-index
status: approved
---

# Golden translation examples

Curated source → target pairs used as few-shot anchors during translation.
Embedded on the `## Source` section; `source_lang` / `target_lang` /
`domain` are indexed as vector metadata for filtering.

```dataview
TABLE source_lang, target_lang, domain, status
FROM "examples"
SORT domain ASC, file.name ASC
```

Seed new pairs with:

```
translate kb examples add <source-file> <target-file> --src en --tgt ja --domain legal
```
