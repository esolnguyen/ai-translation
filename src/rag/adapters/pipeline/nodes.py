"""Default graph node functions (Rev 3 topology).

analyze → resolve_terms → glossary(per-lang) → translate(per-lang)
       → repair(per-lang) → review(per-lang)

Cycle-check, triangulate, and a standalone editor are gone — their jobs
are absorbed by Translator self-flagging + the unified Repair node and the
pure-code Reviewer loop.

Node functions close over a ``PipelineDependencies`` bundle so the graph
itself carries no framework knowledge.
"""

from __future__ import annotations

from dataclasses import asdict, replace

from ...domain import ReviewDecision
from ...use_cases.analyze import AnalyzeDocument
from ...use_cases.back_translate import BackTranslate
from ...use_cases.build_glossary import BuildGlossary
from ...use_cases.ports import PipelineDependencies, RunState
from ...use_cases.repair_chunk import RepairChunk
from ...use_cases.resolve_terms import ResolveTerms
from ...use_cases.review_chunk import ReviewChunk, ReviewInputs
from ...use_cases.translate_chunk import TranslateChunk
from ..metrics import (
    DefaultMetricProfileRegistry,
    InMemoryCustomCheckRegistry,
    default_custom_check_registry,
)
from ..metrics.checks import (
    GlossaryAdherenceCheck,
    LengthSanityCheck,
    MarkdownIntegrityCheck,
    PlaceholderRoundTripCheck,
    TagBalanceCheck,
)
from .graph import Graph, NodeSpec

_UNIVERSAL_CHECK_NAMES: tuple[str, ...] = (
    "glossary_adherence",
    "placeholder_round_trip",
    "markdown_integrity",
    "tag_balance",
    "length_sanity",
)


def build_default_graph(
    deps: PipelineDependencies,
    *,
    roundtrip: bool = False,
) -> Graph:
    analyzer = AnalyzeDocument(llm=deps.llm, retriever=deps.retriever)
    resolver = ResolveTerms(retriever=deps.retriever, lookup_cache=deps.term_cache)
    glossary_builder = BuildGlossary(
        retriever=deps.retriever, lookup_cache=deps.term_cache
    )
    translator = TranslateChunk(llm=deps.llm, retriever=deps.retriever)
    repair_node_repairer = RepairChunk(llm=deps.llm, max_passes=1)
    review_node_repairer = RepairChunk(llm=deps.llm, max_passes=16)
    profile_registry = deps.profile_registry or DefaultMetricProfileRegistry()
    custom_registry = deps.custom_check_registry or default_custom_check_registry()
    universal_checks = _resolve_universal_checks(custom_registry)

    def analyze(state: RunState) -> RunState:
        output = analyzer.execute(
            state.units,
            source_lang=state.config.source_lang,
        )
        state.analysis = output.analysis
        state.candidate_terms = output.candidate_terms
        state.record(
            "analyze",
            {
                "units": len(state.units),
                "domain": output.analysis.domain,
                "sub_domain": output.analysis.sub_domain,
                "candidates": len(output.candidate_terms),
                "retrieved_notes": len(output.analysis.retrieved_note_ids),
            },
        )
        return state

    def resolve_terms(state: RunState) -> RunState:
        domain = state.analysis.domain if state.analysis else None
        output = resolver.execute(
            state.units,
            state.candidate_terms,
            domain=domain,
        )
        state.term_cache = output.cache
        if state.analysis is not None:
            deps.repository.write_analysis(
                state.paths,
                state.analysis,
                candidate_terms=state.candidate_terms,
                term_cache=state.term_cache,
            )
        state.record(
            "resolve_terms",
            {
                "terms_total": output.total,
                "terms_resolved": output.resolved,
                "hit_rate": round(output.hit_rate, 3),
                "cache_hits": output.cache_hits,
                "cache_misses": output.cache_misses,
            },
        )
        return state

    def glossary(state: RunState, lang: str) -> RunState:
        domain = state.analysis.domain if state.analysis else None
        output = glossary_builder.execute(
            state.term_cache,
            target_lang=lang,
            domain=domain,
        )
        branch = state.branch(lang)
        branch.glossary = output.entries
        deps.repository.write_glossary(state.paths, lang, output.entries)
        state.record(
            "glossary",
            {
                "lang": lang,
                "cached_terms": len(state.term_cache),
                "entries": len(output.entries),
                "cache_hits": output.cache_hits,
                "cache_misses": output.cache_misses,
            },
        )
        return state

    def translate(state: RunState, lang: str) -> RunState:
        branch = state.branch(lang)
        branch.chunks_total = len(state.units)
        branch.flags_by_unit = {}
        flagged_units = 0
        for unit in state.units:
            output = translator.execute(
                unit,
                target_lang=lang,
                source_lang=state.config.source_lang,
                analysis=state.analysis,
                glossary=branch.glossary,
            )
            branch.translations[unit.id] = output.translated
            if output.flags:
                branch.flags_by_unit[unit.id] = list(output.flags)
                flagged_units += 1
        deps.repository.write_translated(
            state.paths, lang, branch.translations.values()
        )
        state.record(
            "translate",
            {
                "lang": lang,
                "chunks": branch.chunks_total,
                "flagged": flagged_units,
            },
        )
        return state

    def repair(state: RunState, lang: str) -> RunState:
        branch = state.branch(lang)
        reports: list[dict] = []
        repaired = 0
        escalated = 0
        for unit in state.units:
            flags = branch.flags_by_unit.get(unit.id, [])
            failures = branch.failures_by_unit.get(unit.id, [])
            if not flags and not failures:
                continue
            current = branch.translations[unit.id]
            output = repair_node_repairer.execute(
                current,
                flags=flags,
                failures=failures,
                source_text=unit.text,
                source_lang=state.config.source_lang,
                target_lang=lang,
                analysis=state.analysis,
                glossary=branch.glossary,
                pass_count=branch.repair_passes.get(unit.id, 0),
            )
            branch.translations[unit.id] = output.translated
            branch.repair_passes[unit.id] = output.report.pass_count
            reports.append(asdict(output.report))
            if output.report.escalated:
                escalated += 1
            elif output.report.actions:
                repaired += 1
            branch.flags_by_unit.pop(unit.id, None)
        branch.chunks_retried = repaired
        branch.chunks_escalated = escalated
        if reports:
            deps.repository.write_translated(
                state.paths, lang, branch.translations.values()
            )
        deps.repository.write_repair(state.paths, lang, reports)
        state.record(
            "repair",
            {
                "lang": lang,
                "repaired": repaired,
                "escalated": escalated,
                "chunks": len(reports),
            },
        )
        return state

    def review(state: RunState, lang: str) -> RunState:
        branch = state.branch(lang)
        profile = profile_registry.get(lang)
        reviewer = ReviewChunk(
            profile=profile,
            universal_checks=universal_checks,
            custom_registry=custom_registry,
            embedder=deps.embedder,
        )
        domain = state.analysis.domain if state.analysis else None
        reports: list[dict] = []
        passed = 0
        escalated = 0
        retried_units = 0
        for unit in state.units:
            if unit.id not in branch.translations:
                continue
            translation = branch.translations[unit.id]
            examples = deps.retriever.examples(
                unit.text,
                source_lang=state.config.source_lang,
                target_lang=lang,
                domain=domain,
            )
            inputs = ReviewInputs(
                unit_id=unit.id,
                draft_text=translation.target_text,
                source_text=unit.text,
                target_lang=lang,
                source_lang=state.config.source_lang,
                glossary=branch.glossary,
                examples=examples,
            )
            result = reviewer.execute(inputs)
            retries = 0
            budget = profile.repair_max_passes
            escalated_here = False
            while result.decision == ReviewDecision.RETRY and retries < budget:
                repair_out = review_node_repairer.execute(
                    translation,
                    flags=[],
                    failures=result.failures,
                    source_text=unit.text,
                    source_lang=state.config.source_lang,
                    target_lang=lang,
                    analysis=state.analysis,
                    glossary=branch.glossary,
                    pass_count=retries,
                )
                if repair_out.report.escalated:
                    escalated_here = True
                    break
                translation = repair_out.translated
                branch.translations[unit.id] = translation
                branch.failures_by_unit[unit.id] = list(result.failures)
                retries += 1
                inputs = replace(inputs, draft_text=translation.target_text)
                result = reviewer.execute(inputs)

            if retries > 0 and not escalated_here:
                retried_units += 1
            if result.decision == ReviewDecision.PASS:
                passed += 1
            else:
                escalated_here = True
            if escalated_here:
                escalated += 1

            reports.append(
                {
                    "unit_id": unit.id,
                    "decision": (
                        "pass" if result.decision == ReviewDecision.PASS else "escalate"
                    ),
                    "checklist_score": result.checklist_score,
                    "similarity_score": result.similarity_score,
                    "custom_score": result.custom_score,
                    "composite": result.composite,
                    "failures": list(result.failures),
                    "retries": retries,
                }
            )

        branch.chunks_passed = passed
        branch.chunks_retried += retried_units
        branch.chunks_escalated += escalated
        deps.repository.write_review(state.paths, lang, reports)
        if retried_units or escalated:
            deps.repository.write_translated(
                state.paths, lang, branch.translations.values()
            )
        state.record(
            "review",
            {
                "lang": lang,
                "passed": passed,
                "escalated": escalated,
                "retries": retried_units,
            },
        )
        return state

    back_translator = BackTranslate(llm=deps.llm, embedder=deps.embedder)

    def roundtrip_node(state: RunState, lang: str) -> RunState:
        branch = state.branch(lang)
        reports: list[dict] = []
        sims: list[float] = []
        for unit in state.units:
            translation = branch.translations.get(unit.id)
            if translation is None:
                continue
            output = back_translator.execute(
                translation,
                source_lang=state.config.source_lang,
            )
            entry: dict[str, object] = {
                "unit_id": output.unit_id,
                "source_text": output.source_text,
                "back_text": output.back_text,
                "similarity": output.similarity,
            }
            reports.append(entry)
            if output.similarity is not None:
                sims.append(output.similarity)
        branch.roundtrip_reports = reports
        branch.roundtrip_mean_similarity = sum(sims) / len(sims) if sims else None
        deps.repository.write_roundtrip(state.paths, lang, reports)
        state.record(
            "roundtrip",
            {
                "lang": lang,
                "chunks": len(reports),
                "mean_similarity": branch.roundtrip_mean_similarity,
            },
        )
        return state

    graph = Graph(entry="analyze")
    graph.add(NodeSpec("analyze", analyze))
    graph.add(NodeSpec("resolve_terms", resolve_terms))
    graph.add(NodeSpec("glossary", glossary, per_lang=True))
    graph.add(NodeSpec("translate", translate, per_lang=True))
    graph.add(NodeSpec("repair", repair, per_lang=True))
    graph.add(NodeSpec("review", review, per_lang=True))

    graph.connect("analyze", "resolve_terms")
    graph.connect("resolve_terms", "glossary")
    graph.connect("glossary", "translate")
    graph.connect("translate", "repair")
    graph.connect("repair", "review")

    if roundtrip:
        graph.add(NodeSpec("roundtrip", roundtrip_node, per_lang=True))
        graph.connect("review", "roundtrip")
    return graph


def build_simple_graph(deps: PipelineDependencies) -> Graph:
    """Simple-mode graph: a single per-lang translate node.

    No Analyzer, no ResolveTerms, no Glossary, no Repair, no Reviewer. Used
    for tiny inputs where the full pipeline's fixed overhead would dominate.
    Any ``<unsure>``/``<sense>`` tags the translator emits are stripped by
    :func:`parse_flags` inside :class:`TranslateChunk` — we simply discard
    the resulting flag list.
    """

    translator = TranslateChunk(llm=deps.llm, retriever=deps.retriever)

    def translate_simple(state: RunState, lang: str) -> RunState:
        branch = state.branch(lang)
        branch.chunks_total = len(state.units)
        for unit in state.units:
            output = translator.execute(
                unit,
                target_lang=lang,
                source_lang=state.config.source_lang,
                analysis=None,
                glossary=[],
            )
            branch.translations[unit.id] = output.translated
        branch.chunks_passed = branch.chunks_total
        deps.repository.write_translated(
            state.paths, lang, branch.translations.values()
        )
        state.record(
            "translate_simple",
            {"lang": lang, "chunks": branch.chunks_total},
        )
        return state

    graph = Graph(entry="translate_simple")
    graph.add(NodeSpec("translate_simple", translate_simple, per_lang=True))
    return graph


def _resolve_universal_checks(registry):
    try:
        return registry.resolve(list(_UNIVERSAL_CHECK_NAMES))
    except KeyError:
        fallback = InMemoryCustomCheckRegistry(
            [
                GlossaryAdherenceCheck(),
                PlaceholderRoundTripCheck(),
                MarkdownIntegrityCheck(),
                TagBalanceCheck(),
                LengthSanityCheck(),
            ]
        )
        return fallback.resolve(list(_UNIVERSAL_CHECK_NAMES))
