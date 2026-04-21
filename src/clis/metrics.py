"""``translate metrics`` — reviewer checklist and metric-profile lookup.

Mirrors what the Rev 3 reviewer runs internally so agents can shell out
instead of re-deriving the checklist inside the LLM.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._shared import emit_json, read_text_argument, vault_path

_UNIVERSAL_CHECK_NAMES: tuple[str, ...] = (
    "glossary_adherence",
    "placeholder_round_trip",
    "markdown_integrity",
    "tag_balance",
    "length_sanity",
)

_PASS_THRESHOLD = 0.75


@dataclass(slots=True, frozen=True)
class _GlossaryView:
    """Minimal ``GlossaryEntryLike`` used when loading from a JSON file."""

    source: str
    target: str


def _load_glossary(path: str | None) -> list[_GlossaryView]:
    if not path:
        return []
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    raw_entries: list[dict[str, Any]] = []
    if isinstance(data, list):
        raw_entries = [e for e in data if isinstance(e, dict)]
    elif isinstance(data, dict):
        entries = data.get("entries") or []
        if isinstance(entries, list):
            raw_entries = [e for e in entries if isinstance(e, dict)]
    views: list[_GlossaryView] = []
    for entry in raw_entries:
        source = str(entry.get("source") or "").strip()
        target = str(entry.get("target") or "").strip()
        if source and target:
            views.append(_GlossaryView(source=source, target=target))
    return views


def _profile_payload(profile: Any) -> dict[str, Any]:
    return {
        "lang": profile.lang,
        "weights": {
            "checklist": profile.weights.checklist,
            "similarity": profile.weights.similarity,
            "custom": profile.weights.custom,
        },
        "repair_max_passes": profile.repair_max_passes,
        "custom_check_names": list(profile.custom_check_names),
    }


def cmd_profile(args: argparse.Namespace) -> int:
    from metrics import VaultMetricProfileRegistry

    registry = VaultMetricProfileRegistry(vault_path(args.vault))
    profile = registry.get(args.lang)
    emit_json(_profile_payload(profile))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    from metrics import (
        ChunkContext,
        GlossaryAdherenceCheck,
        LengthSanityCheck,
        MarkdownIntegrityCheck,
        PlaceholderRoundTripCheck,
        TagBalanceCheck,
        VaultMetricProfileRegistry,
        default_custom_check_registry,
    )

    source = read_text_argument(args.source)
    draft = read_text_argument(args.draft)
    glossary = _load_glossary(args.glossary)

    registry = VaultMetricProfileRegistry(vault_path(args.vault))
    profile = registry.get(args.lang)
    checks = default_custom_check_registry()

    ctx = ChunkContext(
        target_lang=args.lang,
        source_lang=args.source_lang or "",
        glossary=list(glossary),
    )

    universal = [
        GlossaryAdherenceCheck(),
        PlaceholderRoundTripCheck(),
        MarkdownIntegrityCheck(),
        TagBalanceCheck(),
        LengthSanityCheck(),
    ]
    custom = checks.resolve(
        [n for n in profile.custom_check_names if n not in _UNIVERSAL_CHECK_NAMES]
    )

    checklist_results = [c.run(draft, source, ctx) for c in universal]
    custom_results = [c.run(draft, source, ctx) for c in custom]

    checklist_passed = sum(1 for r in checklist_results if r.passed)
    custom_passed = sum(1 for r in custom_results if r.passed)

    checklist_rate = (
        checklist_passed / len(checklist_results) if checklist_results else 1.0
    )
    custom_rate = custom_passed / len(custom_results) if custom_results else 1.0

    failures = [
        {"name": r.name, "detail": r.detail}
        for r in (*checklist_results, *custom_results)
        if not r.passed
    ]

    composite: float | None = None
    decision = "pass"
    if args.similarity is not None:
        similarity = max(0.0, min(1.0, args.similarity))
        composite = (
            profile.weights.checklist * checklist_rate
            + profile.weights.similarity * similarity
            + profile.weights.custom * custom_rate
        )
        decision = "pass" if not failures and composite >= _PASS_THRESHOLD else "retry"
    else:
        decision = "pass" if not failures else "retry"

    payload = {
        "lang": args.lang,
        "profile": _profile_payload(profile),
        "checklist": {
            "results": [
                {"name": r.name, "passed": r.passed, "detail": r.detail}
                for r in checklist_results
            ],
            "passed": checklist_passed,
            "total": len(checklist_results),
            "pass_rate": round(checklist_rate, 4),
        },
        "custom": {
            "results": [
                {"name": r.name, "passed": r.passed, "detail": r.detail}
                for r in custom_results
            ],
            "passed": custom_passed,
            "total": len(custom_results),
            "pass_rate": round(custom_rate, 4),
        },
        "failures": failures,
        "similarity": args.similarity,
        "composite": None if composite is None else round(composite, 4),
        "decision": decision,
    }
    emit_json(payload)
    return 0 if decision == "pass" else 1


def build_parser(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="metrics_command", required=True)

    p_profile = sub.add_parser("profile", help="Show the metric profile for a language")
    p_profile.add_argument("lang", help="BCP-47 language code (e.g. de, vi)")
    p_profile.add_argument("--vault", help="Vault root (default: $KB_VAULT or ./vault)")
    p_profile.set_defaults(func=cmd_profile)

    p_check = sub.add_parser(
        "check",
        help="Run the reviewer checklist + profile-driven custom checks",
    )
    p_check.add_argument("--lang", required=True, help="target language code")
    p_check.add_argument(
        "--source", required=True, help="source text, or @file to read from disk"
    )
    p_check.add_argument(
        "--draft", required=True, help="draft text, or @file to read from disk"
    )
    p_check.add_argument("--source-lang", default="", help="source language code (optional)")
    p_check.add_argument(
        "--glossary",
        help="path to a glossary JSON (accepts translate-glossary output shape)",
    )
    p_check.add_argument("--vault", help="vault root (default: $KB_VAULT or ./vault)")
    p_check.add_argument(
        "--similarity",
        type=float,
        help="optional 0..1 cosine to compute the composite score",
    )
    p_check.set_defaults(func=cmd_check)
