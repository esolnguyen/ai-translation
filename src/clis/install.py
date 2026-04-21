"""Install translation skills + agents into Claude Code or Kiro.

Usage:

    translate install claude [--scope project|user] [--force]
    translate install kiro   [--scope project|user] [--force]

Both targets read from ``src/agents/`` in this repo (the source of truth) and
materialise the target-specific layout by symlinking — so edits to the skills
flow through without re-running the installer.

Claude Code layout (``<dst> = .claude`` or ``~/.claude``):

    <dst>/skills/<skill>/SKILL.md     → src/agents/skills/<skill>/
    <dst>/agents/<name>.md            → src/agents/<name>.md

Kiro layout (``<dst> = .kiro`` or ``~/.kiro``):

    <dst>/skills/<skill>/SKILL.md     → src/agents/skills/<skill>/
    <dst>/commands/translate.md       → src/agents/skills/translate/SKILL.md
    <dst>/agents/<name>.md            → src/agents/<name>.md
    <dst>/agents/<name>.json          → generated manifest pinning skill resources
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from pathlib import Path
from typing import Iterable

import yaml

# Agents orchestrated at the top level (Kiro gets a JSON manifest for each).
ORCHESTRATOR_AGENTS = ("translation-lang-worker", "translation-reviewer")

# Skill whose SKILL.md doubles as the /translate slash command in Kiro.
SLASH_COMMAND_SKILL = "translate"


# ─── Paths ─────────────────────────────────────────────────────────────────


def _repo_root() -> Path:
    # src/clis/install.py → repo root is parents[2]
    return Path(__file__).resolve().parents[2]


def _agents_dir() -> Path:
    return _repo_root() / "src" / "agents"


def _skills_dir() -> Path:
    return _agents_dir() / "skills"


def _target_base(target: str, scope: str) -> Path:
    folder = f".{target}"
    if scope == "user":
        return Path.home() / folder
    return Path.cwd() / folder


# ─── Link helpers ──────────────────────────────────────────────────────────


def _replace(dst: Path, *, force: bool) -> None:
    """Make ``dst`` available for a fresh symlink.

    - If it's already a symlink, remove it.
    - If it's a real file/dir, back it up (or delete with --force).
    """
    if dst.is_symlink():
        dst.unlink()
        return
    if not dst.exists():
        return
    if force:
        if dst.is_dir():
            shutil.rmtree(dst)
        else:
            dst.unlink()
        return
    backup = dst.with_suffix(dst.suffix + f".bak.{int(time.time())}")
    dst.rename(backup)
    print(f"   ! {dst} exists and is not a symlink — moved to {backup.name}")


def _symlink(src: Path, dst: Path, *, force: bool) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    _replace(dst, force=force)
    dst.symlink_to(src.resolve())


# ─── Kiro JSON manifest generation ─────────────────────────────────────────


def _parse_frontmatter(md: Path) -> dict:
    text = md.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    return yaml.safe_load(text[4:end]) or {}


def _kiro_manifest(agent_md: Path) -> dict:
    meta = _parse_frontmatter(agent_md)
    name = meta.get("name") or agent_md.stem
    description = meta.get("description", "")
    skill_deps = meta.get("skills") or []

    resources = [
        f"file://../skills/{skill}/SKILL.md"
        for skill in skill_deps
        if (_skills_dir() / skill).is_dir()
    ]
    return {
        "name": name,
        "description": description,
        "prompt": f"file://./{agent_md.stem}.md",
        "resources": resources,
        "tools": ["*"],
    }


# ─── Installers ────────────────────────────────────────────────────────────


def _iter_skill_dirs() -> Iterable[Path]:
    return sorted(p for p in _skills_dir().iterdir() if p.is_dir())


def _install_skills(dst_skills: Path, *, force: bool) -> int:
    count = 0
    for skill in _iter_skill_dirs():
        _symlink(skill, dst_skills / skill.name, force=force)
        count += 1
    return count


def _install_claude(scope: str, force: bool) -> int:
    base = _target_base("claude", scope)
    print(f"==> Installing Claude Code skills + agents → {base}")

    skill_count = _install_skills(base / "skills", force=force)
    print(f"   ✓ {skill_count} skill(s) linked into {base / 'skills'}")

    agents_dst = base / "agents"
    agents_dst.mkdir(parents=True, exist_ok=True)
    agent_count = 0
    for name in ORCHESTRATOR_AGENTS:
        src = _agents_dir() / f"{name}.md"
        if not src.exists():
            print(f"   ! skipping missing agent: {src}")
            continue
        _symlink(src, agents_dst / f"{name}.md", force=force)
        agent_count += 1
    print(f"   ✓ {agent_count} agent(s) linked into {agents_dst}")
    return 0


def _install_kiro(scope: str, force: bool) -> int:
    base = _target_base("kiro", scope)
    print(f"==> Installing Kiro skills + agents + commands → {base}")

    skill_count = _install_skills(base / "skills", force=force)
    print(f"   ✓ {skill_count} skill(s) linked into {base / 'skills'}")

    # Slash command: Kiro reads /translate from <base>/commands/translate.md
    cmd_src = _skills_dir() / SLASH_COMMAND_SKILL / "SKILL.md"
    if cmd_src.exists():
        _symlink(cmd_src, base / "commands" / f"{SLASH_COMMAND_SKILL}.md", force=force)
        print(f"   ✓ /{SLASH_COMMAND_SKILL} command linked into {base / 'commands'}")
    else:
        print(f"   ! skipping missing slash-command source: {cmd_src}")

    # Agents: symlink the .md prompt + generate a .json manifest.
    agents_dst = base / "agents"
    agents_dst.mkdir(parents=True, exist_ok=True)
    agent_count = 0
    for name in ORCHESTRATOR_AGENTS:
        src = _agents_dir() / f"{name}.md"
        if not src.exists():
            print(f"   ! skipping missing agent: {src}")
            continue
        _symlink(src, agents_dst / f"{name}.md", force=force)
        manifest = _kiro_manifest(src)
        (agents_dst / f"{name}.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        agent_count += 1
    print(f"   ✓ {agent_count} agent(s) + manifest(s) written into {agents_dst}")
    return 0


# ─── CLI plumbing ──────────────────────────────────────────────────────────


def _cmd(args: argparse.Namespace) -> int:
    if args.target == "claude":
        return _install_claude(args.scope, args.force)
    if args.target == "kiro":
        return _install_kiro(args.scope, args.force)
    raise SystemExit(f"unknown install target: {args.target}")


def build_parser(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "target",
        choices=("claude", "kiro"),
        help="Which host to install into: claude (Claude Code) or kiro (Kiro IDE).",
    )
    p.add_argument(
        "--scope",
        choices=("project", "user"),
        default="project",
        help="project → <cwd>/.<target>/ (default), user → ~/.<target>/",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing non-symlink files at target paths (default: back up).",
    )
    p.set_defaults(func=_cmd)
