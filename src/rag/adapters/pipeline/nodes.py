"""Default graph node functions.

Real use-case calls start landing here per milestone:

- M1: every node is a stub that records an event.
- M2: ``analyze`` + ``resolve_terms`` call into use-cases; the rest stay stubs.

Node functions close over a ``PipelineDependencies`` bundle so the graph
itself carries no framework knowledge.
"""

from __future__ import annotations

from ...use_cases.analyze import AnalyzeDocument
from ...use_cases.build_glossary import BuildGlossary
from ...use_cases.ports import PipelineDependencies, RunState
from ...use_cases.resolve_terms import ResolveTerms
from .graph import Graph, NodeSpec


def build_default_graph(deps: PipelineDependencies) -> Graph:
    analyzer = AnalyzeDocument(llm=deps.llm, retriever=deps.retriever)
    resolver = ResolveTerms(retriever=deps.retriever, lookup_cache=deps.term_cache)
    glossary_builder = BuildGlossary(
        retriever=deps.retriever, lookup_cache=deps.term_cache
    )

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

    def translate_p1(state: RunState, lang: str) -> RunState:
        branch = state.branch(lang)
        branch.chunks_total = len(state.units)
        state.record("translate_p1", {"lang": lang, "chunks": branch.chunks_total})
        return state

    def cycle_check(state: RunState, lang: str) -> RunState:
        state.record("cycle_check", {"lang": lang})
        return state

    def translate_p2(state: RunState, lang: str) -> RunState:
        state.record("translate_p2", {"lang": lang})
        return state

    def triangulate(state: RunState) -> RunState:
        state.record("triangulate", {"langs": list(state.branches)})
        return state

    def review(state: RunState, lang: str) -> RunState:
        branch = state.branch(lang)
        branch.chunks_passed = branch.chunks_total
        state.record("review", {"lang": lang, "passed": branch.chunks_passed})
        return state

    def edit(state: RunState, lang: str) -> RunState:
        state.record("edit", {"lang": lang})
        return state

    graph = Graph(entry="analyze")
    graph.add(NodeSpec("analyze", analyze))
    graph.add(NodeSpec("resolve_terms", resolve_terms))
    graph.add(NodeSpec("glossary", glossary, per_lang=True))
    graph.add(NodeSpec("translate_p1", translate_p1, per_lang=True))
    graph.add(NodeSpec("cycle_check", cycle_check, per_lang=True))
    graph.add(NodeSpec("translate_p2", translate_p2, per_lang=True))
    graph.add(NodeSpec("triangulate", triangulate))
    graph.add(NodeSpec("review", review, per_lang=True))
    graph.add(NodeSpec("edit", edit, per_lang=True))

    graph.connect("analyze", "resolve_terms")
    graph.connect("resolve_terms", "glossary")
    graph.connect("glossary", "translate_p1")
    graph.connect("translate_p1", "cycle_check")
    graph.connect("cycle_check", "translate_p2")
    graph.connect("translate_p2", "triangulate")
    graph.connect("triangulate", "review")
    graph.connect("review", "edit")
    return graph
