"""Top-level ``translate`` dispatcher.

Structure:

    translate kb ...       → src/clis/kb.py
    translate metrics ...  → src/clis/metrics.py
    translate run ...      → src/clis/run.py
    translate install ...  → src/clis/install.py
"""

from __future__ import annotations

import argparse
import logging
import os

from . import install, kb, metrics, run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="translate",
        description="Unified CLI: knowledge base, reviewer metrics, and the RAG pipeline.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_kb = sub.add_parser("kb", help="Knowledge base: index, search, glossary, examples, …")
    kb.build_parser(p_kb)

    p_metrics = sub.add_parser(
        "metrics", help="Reviewer checklist + per-language metric profiles"
    )
    metrics.build_parser(p_metrics)

    p_run = sub.add_parser("run", help="Run the RAG translation pipeline on a file")
    run.build_parser(p_run)

    p_install = sub.add_parser(
        "install",
        help="Install skills + agents into Claude Code or Kiro (claude|kiro).",
    )
    install.build_parser(p_install)

    return parser


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(override=False)


def _configure_logging() -> None:
    level = os.environ.get("RAG_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-5s %(name)s :: %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    for noisy in (
        "chromadb.telemetry",
        "chromadb.telemetry.product",
        "chromadb.telemetry.product.posthog",
    ):
        logging.getLogger(noisy).setLevel(logging.CRITICAL)


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    _configure_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
