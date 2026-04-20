"""Default graph node functions (Rev 3 topology).

analyze → resolve_terms → glossary(per-lang) → translate(per-lang)
       → repair(per-lang) → review(per-lang)

Cycle-check, triangulate, and a standalone editor are gone — their jobs
are absorbed by Translator self-flagging + the unified Repair node.

Node functions close over a ``PipelineDependencies`` bundle so the graph
itself carries no framework knowledge.
"""

from __future__ import annotations

from dataclasses import asdict

from ...use_cases.analyze import AnalyzeDocument
from ...use_cases.build_glossary import BuildGlossary
from ...use_cases.ports import PipelineDependencies, RunState
from ...use_cases.repair_chunk import RepairChunk
from ...use_cases.resolve_terms import ResolveTerms
from ...use_cases.translate_chunk import TranslateChunk
from .graph import Graph, NodeSpec


def build_default_graph(deps: PipelineDependencies) -> Graph:
    analyzer = AnalyzeDocument(llm=deps.llm, retriever=deps.retriever)
    resolver = ResolveTerms(retriever=deps.retriever, lookup_cache=deps.term_cache)
    glossary_builder = BuildGlossary(
        retriever=deps.retriever, lookup_cache=deps.term_cache
    )
    translator = TranslateChunk(llm=deps.llm, retriever=deps.retriever)
    repairer = RepairChunk(llm=deps.llm)

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
            output = repairer.execute(
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
        branch.chunks_passed = branch.chunks_total - branch.chunks_escalated
        state.record(
            "review",
            {
                "lang": lang,
                "passed": branch.chunks_passed,
                "escalated": branch.chunks_escalated,
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
    return graph
