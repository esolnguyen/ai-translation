"""Unified ``translate`` CLI — ``kb``, ``metrics``, and ``run`` subcommands.

The dispatcher (``translate``) is the only console script exposed by
``pyproject.toml``. All operational flows — knowledge-base lookups,
reviewer-checklist gates, and the full RAG pipeline — live under it:

    translate kb search "brake fluid"
    translate metrics check --lang de --source @src.md --draft @dft.md
    translate run input.md --to de,vi

Each subcommand module lazy-imports its heavy dependencies inside the
handler, so ``translate metrics check`` does not pull in Chroma/rag,
and ``translate kb search`` does not pull in the pipeline router.
"""
