#!/usr/bin/env bash
# Install the translation pipeline into this project.
#
# What it does (idempotent — safe to re-run):
#   1. Installs the `translate` CLI as an editable Python package (`pip install -e .`).
#   2. Delegates to `translate install <target>` to materialise skills + agents into
#      the requested host layout. Supported targets: `claude` (default), `kiro`, `both`.
#   3. Builds the vector index from the vault if `.kb/` is empty (runs `translate kb index`).
#   4. Smoke-tests `translate kb search` to confirm retrieval works.
#
# Usage:
#   scripts/install.sh [claude|kiro|both] [--scope project|user] [--force]
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

# ─── 0. Parse args ─────────────────────────────────────────────────────────
TARGET="claude"
if [[ $# -gt 0 && "$1" != -* ]]; then
    TARGET="$1"; shift
fi
case "$TARGET" in
    claude|kiro|both) ;;
    *) die "unknown target '$TARGET' (expected: claude, kiro, both)" ;;
esac
EXTRA_ARGS=("$@")

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

# ─── 2. Install the translate CLI ─────────────────────────────────────────
step "Installing translate CLI (pip install -e .)"
if pip install -e . --quiet; then
    ok "translate CLI installed"
else
    die "pip install failed"
fi
command -v translate >/dev/null || die "translate not on PATH after install — check your pip user bin is in PATH"
ok "translate available at $(command -v translate)"

# ─── 3. Install skills + agents into the host(s) ──────────────────────────
install_target() {
    local host=$1
    step "Installing skills + agents into $host"
    translate install "$host" "${EXTRA_ARGS[@]}" || die "translate install $host failed"
}

if [[ "$TARGET" == "both" ]]; then
    install_target claude
    install_target kiro
else
    install_target "$TARGET"
fi

# ─── 4. Build the vector index if missing ─────────────────────────────────
step "Checking vector index"
if [[ -d .kb/chroma && -f .kb/glossary.json ]]; then
    ok ".kb/ already populated — skipping reindex"
    warn "re-run manually with \`translate kb index\` to pick up vault changes"
else
    step "Building index from vault/ (this downloads bge-m3 ~2GB on first run)"
    translate kb index || die "translate kb index failed"
    ok "index built"
fi

# ─── 5. Smoke test ─────────────────────────────────────────────────────────
step "Smoke-testing translate kb search"
if translate kb search "brake pad" --domain automotive --k 1 >/dev/null 2>&1; then
    ok "translate kb search returned results"
else
    warn "translate kb search found nothing — vault may be empty or domain absent"
fi

# ─── 6. Summary ────────────────────────────────────────────────────────────
printf "\n${BOLD}Install complete ($TARGET).${RESET}\n"
printf "\nTry it:\n"
printf "  ${DIM}# One file, one target language (Flow A)${RESET}\n"
printf "  /translate acadia-50-sentences.en.md --to vi\n\n"
printf "  ${DIM}# One file, multiple target languages (Flow B fan-out)${RESET}\n"
printf "  /translate template.xlsx --to ja,fr,de\n\n"
printf "CLI:     $(command -v translate)\n"
printf "Index:   .kb/chroma/\n"
