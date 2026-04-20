"""Composition root — assemble the use-case from adapters.

The CLI (and any future web entry point) call ``translate(config)``. Nothing
above this layer knows about concrete adapter classes.
"""

from __future__ import annotations

from .adapters.documents import make_document_adapter
from .adapters.llm import make_llm_client
from .adapters.persistence import make_run_repository, make_term_cache
from .adapters.pipeline import make_pipeline_runner
from .adapters.retrieval import make_retriever
from .domain import RunConfig
from .use_cases.ports import PipelineDependencies
from .use_cases.translate_document import TranslateDocument, TranslateReport


def translate(config: RunConfig) -> TranslateReport:
    """Build the default use-case and run it."""
    repository = make_run_repository()
    deps = PipelineDependencies(
        llm=make_llm_client(),
        retriever=make_retriever(config.kb_store),
        repository=repository,
        term_cache=make_term_cache(config.kb_store),
    )
    use_case = TranslateDocument(
        document_adapter_factory=make_document_adapter,
        runner=make_pipeline_runner(deps),
        repository=repository,
    )
    return use_case.execute(config)


__all__ = ["translate", "RunConfig"]
