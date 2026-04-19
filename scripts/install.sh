#!/usr/bin/env bash
# Install the translation pipeline into this project.
#
# What it does (idempotent — safe to re-run):
#   1. Installs the `kb` CLI as an editable Python package (`pip install -e .`).
#   2. Symlinks `src/claude/skills`  -> `.claude/skills`
#      and       `src/claude/agents` -> `.claude/agents`
#      so Claude Code auto-discovers them.
#   3. Builds the vector index from the vault if `.kb/` is empty
#      (runs `kb index`).
#   4. Smoke-tests `kb search` to confirm retrieval works.
#
# Re-run any time you edit pyproject.toml, vault contents, or the skills.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'; RED=$'\033[0;31m'; BOLD=$'\033[1m'; DIM=$'\033[2m'; RESET=$'\033[0m'
step() { printf "\n${BOLD}==> %s${RESET}\n" "$1"; }
ok()   { printf "   ${GREEN}✓${RESET} %s\n" "$1"; }
warn() { printf "   ${YELLOW}!${RESET} %s\n" "$1"; }
die()  { printf "   ${RED}✗${RESET} %s\n" "$1"; exit 1; }

# ─── 1. Prerequisites ──────────────────────────────────────────────────────
step "Checking prerequisites"
command -v python3 >/dev/null || die "python3 not found on PATH"
command -v pip     >/dev/null || die "pip not found on PATH"
PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
MAJOR=${PY_VERSION%.*}; MINOR=${PY_VERSION#*.}
if (( MAJOR < 3 || (MAJOR == 3 && MINOR < 11) )); then
    die "python >=3.11 required (found $PY_VERSION)"
fi
ok "python $PY_VERSION"

# ─── 2. Install the kb CLI ─────────────────────────────────────────────────
step "Installing kb CLI (pip install -e .)"
if pip install -e . --quiet; then
    ok "kb CLI installed"
else
    die "pip install failed"
fi
command -v kb >/dev/null || die "kb not on PATH after install — check your pip user bin is in PATH"
ok "kb available at $(command -v kb)"

# ─── 3. Install skills and agents into .claude/ ───────────────────────────
step "Linking skills and agents into .claude/"
mkdir -p .claude

link_dir() {
    local src=$1 dst=$2
    [[ -d $src ]] || die "source dir missing: $src"
    if [[ -L $dst ]]; then
        rm "$dst"
    elif [[ -e $dst ]]; then
        warn "$dst exists and is not a symlink — moving to $dst.bak"
        mv "$dst" "$dst.bak.$(date +%s)"
    fi
    ln -s "$(realpath "$src")" "$dst"
    ok "$dst -> $(readlink "$dst")"
}

link_dir src/claude/skills .claude/skills
link_dir src/claude/agents .claude/agents

skill_count=$(find -L .claude/skills -mindepth 2 -maxdepth 2 -name 'SKILL.md' | wc -l)
agent_count=$(find -L .claude/agents -maxdepth 1 -name '*.md' | wc -l)
ok "$skill_count skill(s), $agent_count agent(s) installed"

# ─── 4. Build the vector index if missing ─────────────────────────────────
step "Checking vector index"
if [[ -d .kb/chroma && -f .kb/glossary.json ]]; then
    ok ".kb/ already populated — skipping reindex"
    warn "re-run manually with \`kb index\` to pick up vault changes"
else
    step "Building index from vault/ (this downloads bge-m3 ~2GB on first run)"
    kb index || die "kb index failed"
    ok "index built"
fi

# ─── 5. Smoke test ─────────────────────────────────────────────────────────
step "Smoke-testing kb search"
if kb search "brake pad" --domain automotive --k 1 >/dev/null 2>&1; then
    ok "kb search returned results"
else
    die "kb search failed — check vault contents and index"
fi

# ─── 6. Summary ────────────────────────────────────────────────────────────
printf "\n${BOLD}Install complete.${RESET}\n"
printf "\nTry it:\n"
printf "  ${DIM}# One file, one target language (Flow A)${RESET}\n"
printf "  /translate acadia-50-sentences.en.md --to vi\n\n"
printf "  ${DIM}# One file, multiple target languages (Flow B fan-out)${RESET}\n"
printf "  /translate template.xlsx --to ja,fr,de\n\n"
printf "Skills:  .claude/skills/  (${skill_count} files)\n"
printf "Agents:  .claude/agents/  (${agent_count} files)\n"
printf "CLI:     $(command -v kb)\n"
printf "Index:   .kb/chroma/\n"
