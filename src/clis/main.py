"""Top-level ``translate`` dispatcher.

Structure:

    translate kb ...       → src/clis/kb.py
    translate metrics ...  → src/clis/metrics.py
    translate run ...      → src/clis/run.py
    translate install ...  → src/clis/install.py
"""

from __future__ import annotations

import argparse

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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
