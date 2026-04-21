"""``translate run`` — execute the RAG pipeline on a file."""

from __future__ import annotations

import argparse
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def cmd_run(args: argparse.Namespace) -> int:
    from rag.domain import RunConfig
    from rag.router import translate as run_translate

    if not args.path.exists():
        raise SystemExit(f"source file not found: {args.path}")

    target_langs = [t.strip() for t in args.to.split(",") if t.strip()]
    if not target_langs:
        raise SystemExit("--to must list at least one target language")

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
    logger.info(
        "run start source=%s targets=%s simple=%s dry_run=%s",
        config.source_path,
        ",".join(target_langs),
        config.simple_mode,
        config.dry_run,
    )
    t0 = time.monotonic()
    report = run_translate(config)
    elapsed = time.monotonic() - t0
    logger.info(
        "run end   run_id=%s elapsed=%.2fs outputs=%d",
        report.run_id,
        elapsed,
        len(report.outputs),
    )
    for lang, path in report.outputs.items():
        logger.info("output lang=%s path=%s", lang, path)
        print(f"{lang}\t{path}")
    return 0


def build_parser(parser: argparse.ArgumentParser) -> None:
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
    parser.set_defaults(simple_mode=None, func=cmd_run)
