# Multi-Language RAG Pipeline — Implementation Plan

> Living plan for the RAG path (`src/rag/`). Pairs with `DESIGN-rag.md`.
> The Claude Agent path (`src/claude/`) is already scaffolded and installed
> via `scripts/install.sh`; this plan only covers the programmatic pipeline.
>
> **Revision 3 (de-redundant):** Triangulator removed; Editor folded into
> Repair; Analyzer stripped to `{domain, summary, candidate_terms}`;
> Reviewer becomes **pure code** (checklist + embedding similarity + rule
> gates — zero LLM calls). Net LLM-call count for a 100-chunk × 3-lang
> run: ~500 (vs Rev 2's ~665, Rev 1's ~3000).
>
> Earlier revisions kept in git history.

---

## 1. Assumptions

- **Orchestrator:** hand-rolled `Graph` + `SimplePipelineRunner` (shipped in
  M1). LangGraph is a drop-in alternative behind the same `PipelineRunner`
  port if/when we outgrow the simple runner.
- **Quality signals — each one either cheap or conditional:**
  - *Translator self-flag (scalpel)* — the translator emits `<unsure>` /
    `<sense>` tags inline. Single extra cost: the Repair node that rewrites
    only flagged spans. Clean chunks pay zero repair cost.
  - *Pure-code Reviewer* — no LLM call. Combines:
    - **Checklist** (rule-based): glossary adherence, placeholder
      round-trip, markdown integrity, tag balance, length sanity.
    - **Example similarity** (embedding cosine): compare the draft against
      the retrieved example pairs — no model call, just vector math.
    - **Custom checks** (language-specific pure functions): diacritics,
      case-after-negation, classifier presence, etc.
  - *Repair with failures* — one node handles both self-flag repair and
    reviewer-failure repair. Editor is folded in.
- **Fan-out:** N target languages run as independent branches; each branch
  owns its own Glossary → Translator → Repair → Reviewer chain.
- **No Triangulator.** The checklist + example-similarity + self-flag stack
  catches the same errors at a fraction of the cost. Re-add an LLM-backed
  triangulator only when QA shows a class of miss it would specifically
  catch (item 1 in §6).
- **Scratchpad:** `.translate-runs/<run-id>/` via `RunPaths`. All nodes
  read/write through it so runs are resumable and auditable.
- **KB lookup cache:** `<KB_STORE_PATH>/lookup-cache.json`, keyed by
  `(term, domain, target_lang)` → `{entity, notes, glossary, examples}`.
  Populated during ResolveTerms + Glossary, persisted across runs,
  invalidated when `kb index` changes a term's hash.

## 2. Graph topology

```
                    ┌──────────────┐
  source units ────▶│   Analyzer   │   domain + summary + candidate_terms
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐
                    │ ResolveTerms │   per-term KB lookup; reads/writes cache
                    └──────┬───────┘
                           ▼
               ┌───────────┴───────────┐
               │                       │
   ┌───────────▼───────────┐ ... ┌─────▼─────────────────┐   (one branch per
   │ Glossary (lang=vi)    │     │ Glossary (lang=pl)    │    target lang)
   └───────────┬───────────┘     └─────┬─────────────────┘
               ▼                       ▼
     Translator (1-pass, self-flag)  Translator (...)
               ▼                       ▼
     ┌──────────────────────┐    ┌──────────────────────┐
     │ Repair               │◀─┐ │ Repair               │◀─┐
     │   in:                │  │ │   in:                │  │
     │   - `<unsure>` spans │  │ │   - `<unsure>` spans │  │
     │   - reviewer fails   │  │ │   - reviewer fails   │  │
     └──────────┬───────────┘  │ └──────────┬───────────┘  │
                ▼              │            ▼              │
     ┌──────────────────────┐  │ ┌──────────────────────┐  │
     │ Reviewer (pure code) │──┘ │ Reviewer (pure code) │──┘
     │   checklist + cosine │    │   checklist + cosine │
     │   + custom checks    │    │   + custom checks    │
     └──────────┬───────────┘    └──────────┬───────────┘
                ▼                           ▼
            output.vi.*                 output.pl.*
```

Key cost properties:

- **Repair is conditional.** If a chunk has no `<unsure>`/`<sense>` span
  *and* the Reviewer passes, Repair is a no-op — zero LLM calls.
- **Reviewer makes zero LLM calls.** All three signals are either rule-based
  or vector math.
- **Retry loops back to Repair with `failures`.** If the retry still fails
  after `max_repair_passes`, the chunk escalates: Repair writes the draft
  verbatim and flags it in the manifest. No separate Editor node.
- **Triangulator deleted.** For any target language count.

## 3. Milestones

| # | Name | Scope | Exit criterion | Status |
|---|------|-------|----------------|--------|
| M1 | Graph foundation | `RunState` channel, `Graph` + `SimplePipelineRunner`, dry-run harness | `translate foo.txt --to vi --dry-run` walks every node | ✅ done |
| M2 | Analyzer + ResolveTerms | Domain + `candidate_terms` + `summary`; heuristic + LLM candidates; KB entity+search lookup | `analysis.json` written; term-cache hit-rate logged | ✅ done |
| M2.1 | Trim Analyzer output | Strip `tone`/`register`/`audience` from `AnalysisResult`; simplify prompt | Analyzer prompt + domain class match the Rev 3 schema | — |
| M2.5 | KB lookup cache | Cross-run persistent cache keyed by `(term, domain, target_lang)`; ResolveTerms + Glossary read/write it | Second run on same doc shows >0 cache hits in manifest | — |
| M3 | Per-lang Glossary builder | Read term cache → `retriever.glossary(term, target_lang)` → dedupe → `glossary.<lang>.json` | Each branch has a non-empty glossary when KB has entries | — |
| M4 | Translator (single-pass, self-flag) + Repair (unified) | Prompt emits `<unsure>`/`<sense>` spans; Repair takes `flags + failures` and rewrites only relevant spans; escalation writes verbatim | Clean chunks show empty `repair.json`; escalations noted in manifest | — |
| M5 | Reviewer (pure code) | Rule-based checklist + embedding cosine vs examples + custom checks; retries loop to Repair with failures | `acadia-50-sentences.en.md → .vi.md` green end-to-end | — |
| M5.5 | Metric profiles | Per-language weights + custom-check registry; loaded from `vault/languages/<lang>.md` | `adapters/metrics/registry.py` dispatches per-lang; de/pl profiles exercised by tests | — |
| M6 | Adapters | `md`, `docx`, `srt`, `xlsx` filled in following `txt.py` reference | Each adapter round-trips its fixture without data loss | — |
| M7 | Simple-mode short-circuit | `--simple` flag bypasses Analyzer/ResolveTerms/Glossary/Reviewer for tiny docs (`< 500 words`); auto-selects on small inputs | A 100-word × 5-lang run uses ≤6 LLM calls | — |
| M8 | Optional full round-trip | `--roundtrip` adds a back-translation leg; off by default; metrics recorded in manifest for QA | Flag toggles an extra graph edge | — |

**M2.1 notes.** Strip these fields (all currently in `domain/analysis.py`
and `use_cases/analyze.py`):

- `AnalysisResult.tone` → remove.
- `AnalysisResult.register` → remove.
- `AnalysisResult.audience` → remove.

Prompt schema becomes `{domain, sub_domain, summary, candidate_terms}`.
Translator infers register from the source text directly — a competent
model doesn't need the label when the source already shows the register.

## 4. Per-language metric profiles

Scoring that works for Vietnamese won't work for Polish. Each
`vault/languages/<lang>.md` carries a `## Metric profile` section that the
Reviewer loads at run time.

**Profile schema:**

```yaml
metric_profile:
  weights:
    checklist:   0.40   # rule-based: markdown, tags, glossary adherence
    similarity:  0.30   # embedding cosine vs retrieved examples
    custom:      0.30   # sum of custom pass/fail gates, weighted per check
  repair:
    mode: on_flags_or_fail    # on_flags_or_fail | always | off
    max_passes: 1
  custom_checks:
    - glossary_adherence        # every glossary-locked term lands as spec'd
    - placeholder_round_trip    # {name}, %s, <span>, etc. preserved
    - markdown_integrity        # fences, headings, list markers preserved
    - classifier_presence       # CJK/SEA-specific
    - formality_consistency     # Sie/du; Pan/Pani don't oscillate
    - aspect_consistency        # Polish
    - case_after_negation       # Polish
    - diacritic_presence        # Polish: ą ę ć ł ń ó ś ź ż
    - compound_noun_integrity   # German
```

**Starter profiles:**

- **vi** — `weights (0.40, 0.30, 0.30)`; `custom_checks: [glossary_adherence,
  placeholder_round_trip, markdown_integrity, classifier_presence,
  formality_consistency]`.
- **de** — `weights (0.45, 0.20, 0.35)` (checklist heavier — case errors are
  deterministic); `custom_checks: [glossary_adherence, placeholder_round_trip,
  markdown_integrity, formality_consistency, compound_noun_integrity]`.
- **pl** — `weights (0.50, 0.15, 0.35)` (morphology-heavy); `custom_checks:
  [glossary_adherence, placeholder_round_trip, markdown_integrity,
  formality_consistency, aspect_consistency, case_after_negation,
  diacritic_presence]`; `repair.max_passes: 2`.

`src/rag/adapters/metrics/registry.py` registers named `custom_checks` as
small pure functions `(draft, chunk_ctx, glossary) -> CheckResult`. The
Reviewer computes:

```
score = weights.checklist  * (checks_passed / checks_total)
      + weights.similarity * mean_cosine(draft_embed, example_embeds)
      + weights.custom     * (custom_passed / custom_total)
```

Any `custom_check` gate fail forces a Repair retry regardless of score.

## 5. Cost accounting

Back-of-envelope for a 100-chunk × 3-lang run. "Call" = one LLM completion.

| Stage | Rev 1 | Rev 2 | Rev 3 | Notes |
|-------|------:|------:|------:|-------|
| Analyze | 1 | 1 | 1 | Same |
| ResolveTerms | 0 | 0 | 0 | Heuristic + retriever, no LLM |
| Glossary (per lang) | 3 | 3 | 3 | One small prompt per lang |
| Translator | 300 | 300 | 300 | Single pass |
| Repair | 300 | ~30 | ~30 | Only flagged / reviewer-failed chunks |
| Cycle-check | 300 | (merged) | (merged) | — |
| Triangulator | ~900 | ~0 | 0 | **Removed** |
| Reviewer | 900 (3 calls × 300) | 300 | **0** | Pure code in Rev 3 |
| Editor | up to 300 | ~30 | (merged) | Folded into Repair |
| **Total** | **~3,000** | **~665** | **~335** | ~9× cheaper than Rev 1 |

For the small-doc case (100 words × 5 langs, 1 chunk each):

| Stage | Rev 3 calls | Notes |
|-------|------------:|-------|
| Analyze | 1 | |
| Glossary (×5) | 5 | |
| Translator (×5) | 5 | |
| Repair | ~0 | Unlikely to fire on 100 clean words |
| Reviewer (×5) | 0 | Pure code |
| **Total** | **~11** | Sonnet: ~$0.04; Gemini 2.0 Flash: ~$0.0009 |

With `--simple` (M7), the small-doc case drops to **~5 calls** (one per
lang, skip everything else). Sonnet: ~$0.015; Gemini: ~$0.0005.

## 6. Open decisions

1. **Re-add an LLM triangulator?** Revisit after M6 if QA shows a specific
   error class the pure-code Reviewer misses. Default: stay removed.
2. **Simple-mode threshold.** Auto-route under 500 words *and* under 3
   chunks to `--simple`; keep the flag manually overridable. Numbers tunable
   once we have real latency data.
3. **Runner choice.** Ship with `SimplePipelineRunner`. Swap to LangGraph
   only if fan-out logic or resumability outgrows the hand-rolled version.
4. **Metric profile location.** Embedded in `vault/languages/<lang>.md`
   keeps all per-language knowledge in one place.

## 7. Reuse surfaces (already built)

- `src/rag/domain/` — value objects (Rev 3 trims `AnalysisResult` at M2.1).
- `src/rag/use_cases/ports/` — every abstraction the use-case layer needs.
- `src/rag/use_cases/translate_document.py` — composition entry point.
- `src/rag/use_cases/analyze.py` / `resolve_terms.py` — M2 use-cases.
- `src/rag/adapters/pipeline/graph.py` — hand-rolled DAG primitives.
- `src/rag/adapters/llm/` — null + claude + azure-openai + gemini clients.
- `knowledge.core.retrieval.Retriever.from_env()` — shared KB surface.

## 8. Verification checkpoints

- After M2.1: `analysis.json` no longer has `tone`/`register`/`audience`;
  translator prompt regression test (unchanged translator output for a
  fixture chunk) passes.
- After M2.5: second invocation on the same doc shows `cache_hits > 0` in
  `manifest.events[resolve_terms]`.
- After M3: `glossary.<lang>.json` non-empty when the KB has relevant
  entries; glossary content differs across target langs.
- After M4: a deliberately ambiguous fixture ("bank" without domain) shows
  at least one `<unsure>` flag; Repair rewrites only that span; clean
  chunks have empty `repair.json`; escalated chunks are flagged in the
  manifest.
- After M5: 50-sentence Acadia fixture `.en.md → .vi.md` completes with
  total LLM calls within the Rev 3 budget; all chunks pass the checklist
  or escalate with reasons.
- After M5.5: same doc with `--to de` vs `--to pl` yields Reviewer scores
  computed under different weight vectors; `custom_checks` fire on
  constructed regressions (e.g. strip a diacritic → pl gate fails).
- After M7: `translate hello.txt --to vi,de,pl,fr,ja` on a 100-word input
  uses ≤6 LLM calls (1 Analyze + 5 Translator, everything else skipped).
