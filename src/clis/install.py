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
    <dst>/agents/translate.md         → src/agents/skills/translate/SKILL.md
    <dst>/agents/translate.json       → generated manifest attaching every
                                        sibling skill as a resource
    <dst>/agents/<subagent>.md        → src/agents/<subagent>.md
    <dst>/agents/<subagent>.json      → generated manifest pinning the
                                        subagent's declared skill deps

Kiro has no slash-command surface, so ``translate`` is exposed as an
agent: ``kiro-cli --agent translate`` (or pick it from the TUI).
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

# Subagents: prompt file lives at ``src/agents/<name>.md``.
SUBAGENTS = ("translation-lang-worker", "translation-reviewer")

# Top-level user-facing orchestrator. In Claude Code this is a slash-command
# skill at ``.claude/skills/translate/``; in Kiro there is no slash-command
# surface, so we additionally register it as an agent named ``translate``
# whose prompt is the skill's ``SKILL.md`` and whose resources are every
# sibling skill (so the orchestrator can delegate to them).
ORCHESTRATOR_AGENT = "translate"


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


def _kiro_manifest(
    agent_md: Path,
    *,
    agent_name: str | None = None,
    resource_skills: list[str] | None = None,
) -> dict:
    """Build a Kiro agent manifest.

    ``resource_skills`` lets callers override which skills are attached as
    context (needed for the orchestrator agent whose frontmatter doesn't
    enumerate its skill deps). When omitted, reads ``skills:`` from the
    prompt file's frontmatter.
    """
    meta = _parse_frontmatter(agent_md)
    name = agent_name or meta.get("name") or agent_md.stem
    description = meta.get("description", "")
    skill_deps = resource_skills if resource_skills is not None else (meta.get("skills") or [])

    resources = [
        f"file://../skills/{skill}/SKILL.md"
        for skill in skill_deps
        if (_skills_dir() / skill).is_dir()
    ]
    return {
        "name": name,
        "description": description,
        "prompt": f"file://./{name}.md",
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
    for name in SUBAGENTS:
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
    print(f"==> Installing Kiro skills + agents → {base}")

    skill_count = _install_skills(base / "skills", force=force)
    print(f"   ✓ {skill_count} skill(s) linked into {base / 'skills'}")

    agents_dst = base / "agents"
    agents_dst.mkdir(parents=True, exist_ok=True)

    # Clean up the legacy commands/ directory from earlier installer versions.
    # Kiro never read this path; keeping it around just invites confusion.
    legacy_commands = base / "commands"
    if legacy_commands.exists():
        shutil.rmtree(legacy_commands)
        print(f"   ! removed legacy {legacy_commands} (Kiro ignores commands/)")

    agent_count = 0

    # 1. Orchestrator agent: prompt is the skill's SKILL.md; resources are
    #    every sibling skill so the orchestrator can delegate to them.
    orchestrator_prompt = _skills_dir() / ORCHESTRATOR_AGENT / "SKILL.md"
    if orchestrator_prompt.exists():
        _symlink(orchestrator_prompt, agents_dst / f"{ORCHESTRATOR_AGENT}.md", force=force)
        sibling_skills = [
            p.name for p in _iter_skill_dirs() if p.name != ORCHESTRATOR_AGENT
        ]
        manifest = _kiro_manifest(
            orchestrator_prompt,
            agent_name=ORCHESTRATOR_AGENT,
            resource_skills=sibling_skills,
        )
        (agents_dst / f"{ORCHESTRATOR_AGENT}.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        agent_count += 1
    else:
        print(f"   ! skipping missing orchestrator prompt: {orchestrator_prompt}")

    # 2. Subagents (translation-lang-worker, translation-reviewer): prompt
    #    is src/agents/<name>.md; resources come from frontmatter `skills:`.
    for name in SUBAGENTS:
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
