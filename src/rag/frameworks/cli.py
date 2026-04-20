"""CLI for the RAG pipeline.

Usage:

    translate <path> --to <lang>[,<lang>...] [--source-lang en] [--run-id <id>]

Registered via ``pyproject.toml`` as the ``translate`` entry point.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ..domain import RunConfig
from ..router import translate as run_translate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="translate",
        description="Translate a file into one or more target languages using the RAG pipeline.",
    )
    parser.add_argument(
        "path", type=Path, help="Source file (.txt, .md, .docx, .srt, .xlsx)"
    )
    parser.add_argument(
        "--to",
        required=True,
        help="Comma-separated target language codes, e.g. `ja` or `ja,fr,de`",
    )
    parser.add_argument("--source-lang", default="en")
    parser.add_argument("--run-id", default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Walk the graph without calling any LLM; exercises I/O only",
    )
    parser.add_argument(
        "--roundtrip",
        action="store_true",
        help="Add a back-translation QA leg; records per-chunk similarity",
    )
    simple_group = parser.add_mutually_exclusive_group()
    simple_group.add_argument(
        "--simple",
        dest="simple_mode",
        action="store_const",
        const=True,
        help="Force the simple (translate-only) pipeline, skipping RAG nodes",
    )
    simple_group.add_argument(
        "--no-simple",
        dest="simple_mode",
        action="store_const",
        const=False,
        help="Force the full RAG pipeline even for tiny inputs",
    )
    parser.set_defaults(simple_mode=None)
    args = parser.parse_args(argv)

    if not args.path.exists():
        parser.error(f"source file not found: {args.path}")

    target_langs = [t.strip() for t in args.to.split(",") if t.strip()]
    if not target_langs:
        parser.error("--to must list at least one target language")

    config = RunConfig(
        source_path=args.path.resolve(),
        target_langs=target_langs,
        source_lang=args.source_lang,
        run_id=args.run_id,
        kb_vault=Path(os.environ.get("KB_VAULT", "./vault")),
        kb_store=Path(os.environ.get("KB_STORE_PATH", "./.kb")),
        dry_run=args.dry_run,
        simple_mode=args.simple_mode,
        roundtrip=args.roundtrip,
    )
    report = run_translate(config)
    for lang, path in report.outputs.items():
        print(f"{lang}\t{path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
