"""Run-scope value objects: ``RunConfig`` and ``RunPaths``.

Pure dataclasses — no I/O at construction time. Env lookups happen in the
framework layer (``frameworks/cli.py``), not here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class RunConfig:
    """All settings for one translate invocation."""

    source_path: Path
    target_langs: list[str]
    source_lang: str = "en"
    run_id: str | None = None
    run_root: Path = field(default_factory=lambda: Path(".translate-runs"))
    batch_size: int = 30             # xlsx rows per translator call
    max_review_retries: int = 2
    compose_threshold: float = 4.0   # composite score required for pass
    chunk_target_tokens: int = 700   # rough target for neighbor-context chunks
    kb_vault: Path = field(default_factory=lambda: Path("./vault"))
    kb_store: Path = field(default_factory=lambda: Path("./.kb"))
    dry_run: bool = False

    @property
    def run_dir(self) -> Path:
        if self.run_id is None:
            raise ValueError("run_id must be set before accessing run_dir")
        return self.run_root / self.run_id


@dataclass(slots=True)
class RunPaths:
    """Filesystem layout for a single translation run."""

    run_dir: Path
    source_path: Path
    manifest: Path
    units: Path
    analysis: Path

    @classmethod
    def for_run(cls, run_dir: Path, source_path: Path) -> RunPaths:
        return cls(
            run_dir=run_dir,
            source_path=source_path,
            manifest=run_dir / "manifest.json",
            units=run_dir / "units.jsonl",
            analysis=run_dir / "analysis.json",
        )

    def glossary(self, target_lang: str) -> Path:
        return self.run_dir / f"glossary.{target_lang}.json"

    def chunks_dir(self, target_lang: str) -> Path:
        return self.run_dir / target_lang / "chunks"

    def review_dir(self, target_lang: str) -> Path:
        return self.run_dir / target_lang / "review"

    def triangulate_dir(self) -> Path:
        return self.run_dir / "triangulate"
