"""Local sentence-transformers embedder (default: bge-m3).

Model load is deferred to the first ``embed`` call so importing the module
stays cheap — otherwise every ``kb`` invocation would pay a multi-second
cold start just to print ``--help``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

_MODEL_DIMENSIONS = {
    "BAAI/bge-m3": 1024,
    "BAAI/bge-small-en-v1.5": 384,
    "BAAI/bge-base-en-v1.5": 768,
    "BAAI/bge-large-en-v1.5": 1024,
}


class LocalEmbedder:
    """``Embedder`` protocol implementation backed by sentence-transformers."""

    def __init__(self, model_name: str = "BAAI/bge-m3") -> None:
        self._model_name = model_name
        self._model: SentenceTransformer | None = None
        self._dimension = _MODEL_DIMENSIONS.get(model_name)

    @property
    def name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            # Unknown model — force a load so we can read it off the model.
            self._dimension = self._load().get_sentence_embedding_dimension()
        return self._dimension

    def _load(self) -> SentenceTransformer:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load()
        vectors = model.encode(texts, normalize_embeddings=True)
        return [list(map(float, v)) for v in vectors]
