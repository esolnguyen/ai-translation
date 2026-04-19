---
name: translate-cycle-check
description: Targeted back-translation on flagged spans only (`<unsure>` / `<sense>` / reviewer-flagged). Scores semantic drift 1–5 with in-context back-translation (no false positives from isolated 3-word snippets). Emits diffs for `translate-translate` pass 2. Never back-translates the whole document.
tools: Bash, Read, Write
---

# translate-cycle-check

The targeted half of DESIGN-agent.md §Accuracy techniques #6. Runs between translator pass 1 and pass 2, per chunk.

## Inputs

- `run_dir`, `target_lang`
- `pass1_draft_path` — `<run_dir>/<target_lang>/chunks/<id>.pass1.md`
- `chunk` — `{id, current_source_text}` so the back-translation can be compared against the original
- `source_lang`, `target_lang`

## Procedure

1. Parse the pass-1 draft for flagged spans:
    - `<unsure>...</unsure>`
    - `<sense word="..." chose="..." because="...">...</sense>`
    - Any spans the previous reviewer flagged (passed in via optional `--extra-spans` JSON)
2. For each flagged span:
    1. Locate the **full target-language sentence** containing the span in the pass-1 draft.
    2. Mark the span inside that sentence with `<span>...</span>` — the back-translator sees the whole sentence, but only back-translates the marked portion (DESIGN-agent.md §Accuracy #6 — context guard against false drift).
    3. Ask Claude to back-translate only the `<span>` portion **in context**, into `source_lang`.
    4. Compare the back-translation to the original source span (same-index range in `current_source_text`) and score semantic drift on 1–5:
        - 5 = identical meaning
        - 4 = tiny rewording, same meaning
        - 3 = noticeable drift in nuance or emphasis
        - 2 = meaning partially off
        - 1 = meaning changed
    5. Emit a diff entry. Spans with score ≥ 4 are fine; ≤ 3 feed pass 2.

## Output

Write `<run_dir>/<target_lang>/chunks/<id>.cycle.json`:

```json
{
  "chunk_id": "0042",
  "results": [
    {
      "span": "cú đá",
      "source_span": "strike",
      "back_translation": "kick",
      "drift_score": 5,
      "action": "keep",
      "span_context": "Anh ấy đã tung một <span>cú đá</span> vào phút 87."
    },
    {
      "span": "dịch vụ trước giao xe",
      "source_span": "pre-delivery service",
      "back_translation": "pre-sale service",
      "drift_score": 3,
      "action": "rewrite",
      "suggested_fix": "dịch vụ tiền giao xe",
      "reason": "PDS is a fixed industry term; the back-translation shows the chosen form drifts to a sales context"
    }
  ]
}
```

Emit the same JSON to stdout so the orchestrator can hand it straight to pass 2.

## Do not

- Back-translate the full chunk — only flagged spans.
- Back-translate spans in isolation — always include the full target-language sentence with the span marked. Isolated 3-word snippets generate false drift.
- Modify the pass-1 draft. Output is diffs only; rewriting is pass 2's job.
- Lower a drift score because "the translation reads nicer" — this is a meaning check, not a fluency check.
