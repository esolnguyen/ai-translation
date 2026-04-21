"""``translate kb`` — knowledge base operations.

All handlers lazy-import ``knowledge.core`` so that unrelated
subcommands (``translate metrics …``) do not pay for Chroma + the
embedding model on startup.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ._shared import emit_json, read_text_argument, vault_path


def cmd_index(args: argparse.Namespace) -> int:
    from knowledge.core.indexer import Indexer
    from knowledge.core.retrieval import Retriever

    retriever = Retriever.from_env()
    indexer = Indexer(
        embedder=retriever._embedder,  # noqa: SLF001 — intentional reuse
        store=retriever._store,  # noqa: SLF001
        glossary_store=retriever._glossary,  # noqa: SLF001
        entity_store=retriever._entities,  # noqa: SLF001
        language_store=retriever._languages,  # noqa: SLF001
    )
    report = indexer.sync(vault_path())
    if args.json:
        emit_json(report.to_dict())
    else:
        print(report.format())
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    from knowledge.core.retrieval import Retriever

    retriever = Retriever.from_env()
    hits = retriever.search(args.query, domain=args.domain, k=args.k)
    emit_json(hits)
    return 0


def cmd_glossary(args: argparse.Namespace) -> int:
    from knowledge.core.retrieval import Retriever

    retriever = Retriever.from_env()
    entry = retriever.glossary(args.term, target_lang=args.target)
    emit_json(entry)
    return 0 if entry is not None else 1


def cmd_examples_query(args: argparse.Namespace) -> int:
    from knowledge.core.retrieval import Retriever

    retriever = Retriever.from_env()
    source_text = read_text_argument(args.source)
    hits = retriever.examples(
        source_text=source_text,
        source_lang=args.src,
        target_lang=args.tgt,
        domain=args.domain,
        k=args.k,
    )
    emit_json(hits)
    return 0


def cmd_examples_add(args: argparse.Namespace) -> int:
    source_text = Path(args.source_file).read_text(encoding="utf-8").strip()
    target_text = Path(args.target_file).read_text(encoding="utf-8").strip()
    vault = vault_path()
    example_id = args.id or f"ex-{args.domain}-{Path(args.source_file).stem}"
    dest_dir = vault / "examples" / f"{args.src}-{args.tgt}" / args.domain
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{example_id}.md"
    body = (
        f"---\n"
        f"id: {example_id}\n"
        f"source_lang: {args.src}\n"
        f"target_lang: {args.tgt}\n"
        f"domain: {args.domain}\n"
        f"status: needs-review\n"
        f"---\n\n"
        f"## Source\n{source_text}\n\n"
        f"## Target\n{target_text}\n\n"
        f"## Notes\n"
    )
    dest.write_text(body, encoding="utf-8")
    emit_json({"wrote": str(dest), "id": example_id})
    return 0


def cmd_lang_card(args: argparse.Namespace) -> int:
    from knowledge.core.retrieval import Retriever

    retriever = Retriever.from_env()
    card = retriever.language_card(args.lang)
    emit_json(card)
    return 0 if card is not None else 1


def cmd_entity(args: argparse.Namespace) -> int:
    from knowledge.core.retrieval import Retriever

    retriever = Retriever.from_env()
    entry = retriever.entity(args.name)
    emit_json(entry)
    return 0 if entry is not None else 1


def build_parser(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="kb_command", required=True)

    p_index = sub.add_parser("index", help="Sync approved vault notes to stores")
    p_index.add_argument("--json", action="store_true", help="emit JSON report")
    p_index.set_defaults(func=cmd_index)

    p_search = sub.add_parser("search", help="Semantic search over domain notes")
    p_search.add_argument("query")
    p_search.add_argument("--domain")
    p_search.add_argument("--k", type=int, default=5)
    p_search.set_defaults(func=cmd_search)

    p_gloss = sub.add_parser("glossary", help="Canonical term lookup")
    p_gloss.add_argument("term")
    p_gloss.add_argument("--target", required=True, help="target language code")
    p_gloss.set_defaults(func=cmd_glossary)

    p_examples = sub.add_parser("examples", help="Golden example lookup / seeding")
    ex_sub = p_examples.add_subparsers(dest="examples_cmd", required=True)

    p_ex_query = ex_sub.add_parser("query", help="Top-k similar golden pairs")
    p_ex_query.add_argument("source", help="source text, or @file to read from disk")
    p_ex_query.add_argument("--src", required=True)
    p_ex_query.add_argument("--tgt", required=True)
    p_ex_query.add_argument("--domain")
    p_ex_query.add_argument("--k", type=int, default=3)
    p_ex_query.set_defaults(func=cmd_examples_query)

    p_ex_add = ex_sub.add_parser("add", help="Seed a new golden example into the vault")
    p_ex_add.add_argument("source_file")
    p_ex_add.add_argument("target_file")
    p_ex_add.add_argument("--src", required=True)
    p_ex_add.add_argument("--tgt", required=True)
    p_ex_add.add_argument("--domain", required=True)
    p_ex_add.add_argument("--id", help="stable note id (auto-generated if omitted)")
    p_ex_add.set_defaults(func=cmd_examples_add)

    p_lang = sub.add_parser("lang-card", help="Per-target-language style card")
    p_lang.add_argument("lang")
    p_lang.set_defaults(func=cmd_lang_card)

    p_entity = sub.add_parser("entity", help="Proper-noun decision lookup")
    p_entity.add_argument("name")
    p_entity.set_defaults(func=cmd_entity)
