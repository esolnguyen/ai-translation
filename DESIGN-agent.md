# AI Translation — Claude Code Agent Pipeline

Translation driven by Claude Code skills and subagents reading an Obsidian vault directly. Interactive, local, no hosted infrastructure.

Related docs:
- [DESIGN-knowledge.md](./DESIGN-knowledge.md) — shared Phase 1 (extract to Obsidian vault)
- [DESIGN-rag.md](./DESIGN-rag.md) — programmatic Python + vector DB alternative path

## Goals

- Multi-agent translation via Claude Code subagents, not Python pipeline code
- Support `.txt`, `.md`, `.docx`, `.srt`, `.xlsx`
- Preserve source formatting (markdown structure, docx styles, srt timing)
- Consistent terminology via a shared glossary
- Interactive iteration — user can nudge an agent between steps
- Zero hosted infrastructure — no vector DB, no embedder, no server

## How this differs from the RAG pipeline

| Aspect | RAG pipeline | Agent pipeline (this doc) |
|---|---|---|
| Orchestration | Python + Claude Agent SDK | Claude Code skills + subagents |
| Retrieval | Vector DB (semantic) | File tools (Read / Grep / Glob on vault) |
| Format handling | Python adapters | Claude Code skills (+ Bash for parsing libs) |
| Best for | Batch, scheduled, CI | Interactive work, small batches, iteration |
| Infra required | Python runtime + vector DB | Just Claude Code |

Both share the Obsidian vault as the knowledge base.

## Phases

- **Phase 1 — Extract to Obsidian.** Shared with the RAG path. See [DESIGN-knowledge.md](./DESIGN-knowledge.md).
- **Phase 2 — Translate via subagents.** A Claude Code slash-command skill orchestrates role-specific subagents that read the vault directly via file tools. No indexing step.

## Phase 1 — Extract to Obsidian

Defined in [DESIGN-knowledge.md](./DESIGN-knowledge.md). Same vault, same note format as the RAG path. The Agent path reads this vault directly — no vector DB between the vault and the translator. Frontmatter fields (`domain`, `tags`, `status`, `source_lang`, `target_lang`) are the filter keys the subagents use in place of embeddings.

## Phase 2 — Translate via subagents

### Pipeline roles — skills + targeted subagents

The pipeline is sequential and stateful, so most roles run as **skills** in the main conversation — no lossy re-briefing across cold subagent spawns. **Subagents** are used only where isolation genuinely pays off: a fresh-eyes reviewer and per-language fan-out in Flow B.

**Skills (main-agent roles):**

1. **`translate-analyze`** — reads source; uses `Glob`/`Grep` on `vault/domains/**` frontmatter to find matching notes; reports domain, sub-domain, tone, register, audience, relevant note IDs. Output is injected verbatim into later skills' prompts.
2. **`translate-resolve-terms`** — document-level polysemy lock. Scans the full source for words with multiple common senses in the target language (e.g., EN `bank` → VI `ngân hàng` vs `bờ`), picks the right sense per the domain call, writes locked choices to a scratch glossary. Runs once per document before any prose translation.
3. **`translate-glossary`** — scans `vault/glossary/terms/*.md` + `vault/entities/*.md` + `vault/idioms/<src>-<tgt>/*.md`; merges with the resolved-terms scratch glossary; flags new terms for user approval.
4. **`translate-translate`** — translates units using the analyzer output, the locked glossary, top examples from `vault/examples/<src>-<tgt>/<domain>/`, and the target-language style card `vault/languages/<lang>.md`. Runs in two passes with self-flagging (see Accuracy techniques).
5. **`translate-cycle-check`** — targeted back-translation on flagged spans only. Back-translates each `<unsure>` / `<sense>` / reviewer-flagged span to source; Claude judges semantic drift on 1–5; if ≤3, emits a diff to feed into translator pass 2. Never back-translates the whole document.
6. **`translate-edit`** — applies reviewer fixes + cycle-check corrections, polishes for target-language readers.

**Subagents (`.claude/agents/*.md`) — only where isolation helps:**

- **`translation-reviewer`** — runs a **structured checklist** review (not open-ended) and produces a **composite score** from three sub-scores: ground (domain-knowledge alignment), example (exemplar similarity), and checklist (structural correctness). Checklist is driven by the target-language style card and includes language-specific items: pronouns/kinship, classifiers, register, polysemy sense-picks, named-entity handling, idioms. Runs as a subagent so it hasn't witnessed the translator's reasoning; it sees only source + translation + glossary, producing a more honest critique. See **Review scoring** below.
- **`translation-lang-worker`** (Flow B only) — per-language fan-out. `/translate template.xlsx --to ja,fr,de` spawns one per target language. Each worker runs the translate → cycle-check → reviewer → edit chain against a shared, pre-built glossary.

### Vault access (no embeddings)

Relevance without a vector DB:

- `Glob vault/domains/<domain>/*.md` — list notes in a domain
- `Grep -l "tags:.*contract" vault/domains/**/*.md` — filter by tag
- `Read` for specific notes
- `Glob vault/examples/<src>-<tgt>/<domain>/*.md` — list candidate few-shot pairs
- Wikilinks in note bodies guide chain-of-reading

This works well for small-to-medium vaults. If the vault outgrows this, switch to the RAG path.

### Slash-command skills

- **`/translate <file> --to ja,fr`** — orchestrates the 5-subagent chain
- **`/seed-example <source-file> <target-file> --src en --tgt ja --domain legal`** — writes a golden example note
- **`/extract <doc>`** — invokes the Phase 1 extractor

### Format handling (skills, not Python modules)

Each format has a skill that parses input into translatable units and writes output. Skills call out to Bash when a library is needed (`python-docx`, `openpyxl`, etc.) but the orchestration stays in Claude Code.

- `translate-md` — Markdown AST; translate text nodes only
- `translate-docx` — runs per paragraph; preserve bold/italic/styles
- `translate-srt` — cues with timing + ~42 char/line limit
- `translate-xlsx` — in-place column fill; idempotent (skip filled cells)
- `translate-txt` — plain text; chunk if long

`/translate` invokes the right format skill to extract units → hands them to the subagent chain → re-invokes the skill to write output.

## Flow A — Text files

```
/translate input.md --to ja
    -> translate-md skill:           parse to units
    -> translate-analyze skill:      domain + sub-domain + tone + register
    -> translate-resolve-terms skill: document-level polysemy lock
    -> translate-glossary skill:     glossary + entities + idioms + resolved terms
    -> translate-translate skill, PASS 1:
         + reads vault/languages/<lang>.md style card
         + receives prev/current/next chunk as neighbor context
         + self-flags uncertain spans <unsure> and sense picks <sense>
    -> translate-cycle-check skill:  back-translate flagged spans only → diffs
    -> translate-translate skill, PASS 2: rewrite flagged spans using diffs
    -> translation-reviewer SUBAGENT: checklist + ground + example → composite score
         └─ composite < threshold: loop back to translator with retry_focus (max 2)
    -> translate-edit skill:         apply fixes + polish
    -> translate-md skill:           rebuild file
    -> input.ja.md
```

Output filename convention: `input.{lang}.ext`. Original file is never modified.

## Flow B — Excel template (in-place column fill)

```
/translate template.xlsx --to ja,fr,de
    -> translate-xlsx skill:        read source col, detect empty target cols
    -> translate-analyze skill:     run once on the source corpus
    -> translate-resolve-terms skill: polysemy lock across the whole column
    -> translate-glossary skill:    built once, shared across languages
    -> translation-lang-worker SUBAGENT per target language (parallel):
         translate-translate PASS 1 (skill, ~30 rows/batch, with style card)
         -> translate-cycle-check (skill, flagged cells only)
         -> translate-translate PASS 2 (skill)
         -> translation-reviewer (nested subagent, checklist)
         -> translate-edit (skill)
    -> translate-xlsx skill:        write cells in-place
```

Properties:

- Preserves all other sheet content (styles, formulas, other sheets)
- Idempotent — filled cells are skipped
- Target languages run in parallel, sharing a glossary + resolved-terms lock built once upfront
- Excel cell strings are short and context-free, so polysemy lock + analyzer domain prime + glossary are critical for disambiguation

## Accuracy techniques

Concrete levers the pipeline stacks to maximise translation quality. Each is cheap in isolation; the gains compound.

### 1. Per-language style cards

`vault/languages/<lang>.md` — one note per target language capturing register rules, pronoun / kinship systems, honorifics, classifier usage, sentence-final particles, common source-language pitfalls, and preferred idioms. The translator reads the card for the target language every run. Single biggest lift for per-language naturalness (e.g., Vietnamese pronoun selection, Japanese keigo, French gender agreement).

### 2. Domain prime — verbatim, not summarised

The analyzer's output (domain, sub-domain, register) is injected **verbatim** into the translator's system prompt. Explicit priming disambiguates polysemy far better than inferred context. Example: priming "sports journalism / football match / casual" biases EN `strike` → `cú đá`, not `đình công`.

### 3. Document-level term resolution (polysemy lock)

Before any prose is translated, `translate-resolve-terms` scans the full source for words with ≥2 common senses in the target language, picks the right sense once based on the domain + overall context, and writes the locked choices to the scratch glossary. Prevents the common failure where the same polysemous word gets translated inconsistently across paragraphs.

### 4. Neighbor-context chunking

For long documents, split at paragraph / H2 boundaries (~500–800 tokens). Each translator call receives **prev chunk + current chunk + next chunk** but translates only the current. Kills pronoun / reference drift at chunk boundaries — the #1 long-doc failure mode.

### 5. Two-pass translate with self-flagging

- **Pass 1** — translator produces draft and wraps uncertain spans in `<unsure>...</unsure>` and disambiguation choices in `<sense word="strike" chose="cú đá" because="football context">cú đá</sense>`.
- **Pass 2** — same skill, given the draft + flags + cycle-check diffs, rewrites *only* marked spans with deeper thinking. Cheaper and more accurate than one monolithic pass.

### 6. Targeted back-translation (not full-document)

Back-translation excels at catching meaning drops / additions but is blind to register, pronoun, and classifier errors, and tends to self-confirm when run on whole documents. So `translate-cycle-check` back-translates **only flagged spans** (`<unsure>`, `<sense>`, or reviewer-flagged) and asks Claude to score semantic drift 1–5. Spans scoring ≤3 are retranslated with the diff as feedback. ~10% of the token cost of full back-translation with most of the signal.

### 7. Checklist reviewer (not open-ended)

The reviewer runs a structured checklist driven by the target-language style card. Generic items plus language-specific ones:

- [ ] Every glossary term used correctly
- [ ] No untranslated source-language leakage
- [ ] Tone / register matches the analyzer's call
- [ ] No sentences added or dropped
- [ ] Polysemous source words translated to the correct sense for the domain
- [ ] Named entities and idioms handled per vault convention
- [ ] Language-specific (example, VI): pronouns / kinship match inferred relationship; classifiers correct for each noun; sentence-final particles appropriate for register

Checklist reviewers catch ~2× the errors of "is this good?" reviewers.

### 8. Named entities and idioms as vault notes

- `vault/entities/<name>.md` — proper nouns with decision (translate / transliterate / keep as-is) + rationale. Picked up by `translate-glossary`.
- `vault/idioms/<src>-<tgt>/<id>.md` — idiom pairs so the translator doesn't render them literally (`kick the bucket` ≠ `đá cái xô`).

Both files are created by `/seed-example`-style skills or during extraction review.

### 9. Composite review score

The reviewer produces three sub-scores (1–5) plus a weighted composite. Sub-scores make weaknesses visible and addressable; the composite is the ship-or-retry gate.

| Sub-score | What it measures | How the reviewer computes it (no infra) |
|---|---|---|
| **Ground** | Alignment with domain knowledge | Reads the top tag-matched notes from `vault/domains/<domain>/`. Judges whether the translation uses the same terminology, style, and conventions those notes describe. |
| **Example** | Stylistic similarity to golden pairs | Reads 2–3 tag-matched pairs from `vault/examples/<src>-<tgt>/<domain>/`. Judges whether the translation reads like the approved exemplars in tone, register, phrasing. |
| **Checklist** | Structural correctness | Runs the language-specific checklist. Score = `passed_items / total_items × 5`. |

**Composite** = `0.35 × ground + 0.35 × example + 0.30 × checklist`. Weights tunable per project in the reviewer's system prompt — e.g., raise the example weight for marketing copy, raise the checklist weight for legal.

**Gating rules:**

- Composite ≥ 4.0 **and** every sub-score ≥ 3 → pass to editor
- Any sub-score ≤ 3 → feed the specific weakness back to the translator for a targeted retry (max 2 cycles)
- Composite < 3.5 after retries → surface to the user for manual review

**Review report format** — the reviewer subagent returns structured output so the orchestrator can route automatically:

```yaml
ground:
  score: 4.2
  notes: "Uses legal register; one term deviates from vault/domains/legal/contract-terms.md"
example:
  score: 3.8
  notes: "Matches exemplar tone; formality slightly stiffer than the reference pairs"
checklist:
  score: 4.5
  passed: 14
  total: 15
  failures:
    - "glossary term 'settlement' rendered inconsistently between para 3 and para 7"
composite: 4.17
decision: pass          # pass | retry | escalate
retry_focus:            # only present when decision == retry
  target: translate-translate
  reason: "example score low — translation reads more formal than exemplars; soften register in marked spans"
  spans: [<list of source spans to rework>]
```

This makes the review a *structured signal*, not just prose — the orchestrator can loop automatically without a human in the middle until composite drops below the escalation threshold.

## Architecture

```
.claude/
  agents/
    translation-reviewer.md        checklist review subagent
    translation-lang-worker.md     per-language subagent for Flow B fan-out
  skills/
    translate.md                   slash-command orchestrator
    translate-analyze.md           pipeline step
    translate-resolve-terms.md     polysemy lock
    translate-glossary.md          pipeline step
    translate-translate.md         two-pass translator with self-flagging
    translate-cycle-check.md       targeted back-translation
    translate-edit.md              pipeline step
    translate-md.md                format handlers
    translate-docx.md
    translate-srt.md
    translate-xlsx.md
    translate-txt.md
    seed-example.md
    extract.md                     Phase 1 extractor (optional)

vault/                              shared with the RAG path
  domains/<domain>/<topic>.md       domain knowledge (from Phase 1)
  glossary/terms/<term>.md          canonical term translations
  examples/<src>-<tgt>/<domain>/    golden source -> target pairs
  languages/<lang>.md               per-target-language style cards
  entities/<name>.md                proper-noun handling decisions
  idioms/<src>-<tgt>/<id>.md        idiom pairs
```

## Key design decisions

- **No vector DB, no embedder** — relevance via folder structure, tags, and wikilinks
- **Skills for sequential roles, subagents only where isolation pays off** — analyzer / resolver / glossary / translator / cycle-check / editor share state as skills; reviewer runs as a subagent for unbiased critique; Flow B uses per-language subagents for parallelism
- **Accuracy stack over single heroic step** — style cards + domain prime + polysemy lock + neighbor-context + two-pass self-flagging + targeted back-translation + checklist reviewer. Each is cheap; the gains compound.
- **Back-translation is a scalpel, not a hammer** — run only on flagged spans; checklist reviewer is the primary quality gate.
- **Format logic in skills, not Python modules** — rely on Claude's tool use + Bash for parsing libs
- **Excel batch:** ~30 rows per translator call
- **Vault is shared with the RAG path** — start with the agent pipeline and switch to RAG later without re-curating notes

## When to use this over the RAG pipeline

- Small-to-medium vault (tag/domain filtering is enough)
- Translating a handful of documents at a time
- You want to review each agent's output before the next runs
- No appetite to run or host a vector DB
- Exploring / prototyping — the vault you build here is directly reusable by the RAG path later

## Open questions

1. Without embeddings, how does the translator subagent pick which examples to include — tag overlap only, or also a lightweight keyword match?
2. Should extraction (Phase 1) be a Claude Code skill or stay as the Python `kb extract` CLI shared with the RAG path?
3. Caching — subagent calls can be expensive at scale. Cache per-domain glossary extraction across invocations?
