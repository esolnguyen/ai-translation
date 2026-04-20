"""M8 — BackTranslate use-case unit tests.

Covers the core round-trip QA primitive: the LLM is called once with a
``{target_lang} → {source_lang}`` system prompt, the result is trimmed, and
similarity is computed via the injected embedder when one is present.
"""

from __future__ import annotations

from collections.abc import Sequence

from rag.domain import TranslatedUnit
from rag.use_cases.back_translate import BackTranslate
from rag.use_cases.ports import Embedder, LLMClient, LLMMessage


class _RecordingLLM(LLMClient):
    def __init__(self, response: str) -> None:
        self._response = response
        self.messages: list[Sequence[LLMMessage]] = []

    def complete(
        self,
        messages: Sequence[LLMMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        self.messages.append(list(messages))
        return self._response


class _FakeEmbedder(Embedder):
    def __init__(self, table: dict[str, list[float]]) -> None:
        self._table = table

    @property
    def name(self) -> str:
        return "fake"

    @property
    def dimension(self) -> int:
        return 3

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._table.get(t, [0.0, 0.0, 0.0]) for t in texts]


def _translation(src: str, tgt: str, lang: str = "vi") -> TranslatedUnit:
    return TranslatedUnit(
        id="u1",
        source_text=src,
        target_text=tgt,
        target_lang=lang,
        meta={},
    )


def test_back_translate_uses_target_to_source_prompt() -> None:
    llm = _RecordingLLM("Hello there.")
    bt = BackTranslate(llm=llm)
    out = bt.execute(_translation("Hi.", "Xin chào."), source_lang="en")

    assert out.back_text == "Hello there."
    system = next(m.content for m in llm.messages[0] if m.role == "system")
    assert "vi back to en" in system.replace(" to ", " back to en", 1) or (
        "vi" in system and "en" in system
    )
    user = next(m.content for m in llm.messages[0] if m.role == "user")
    assert user == "Xin chào."


def test_back_translate_similarity_when_embedder_present() -> None:
    llm = _RecordingLLM("hello world")
    embedder = _FakeEmbedder(
        {
            "hello world": [1.0, 0.0, 0.0],
            "hello world!": [0.9999, 0.01, 0.0],
        }
    )
    bt = BackTranslate(llm=llm, embedder=embedder)
    out = bt.execute(
        _translation("hello world!", "xin chào thế giới"),
        source_lang="en",
    )
    assert out.similarity is not None
    assert out.similarity > 0.99


def test_back_translate_similarity_none_without_embedder() -> None:
    llm = _RecordingLLM("hello")
    bt = BackTranslate(llm=llm)
    out = bt.execute(_translation("hi", "xin chào"), source_lang="en")
    assert out.similarity is None


def test_back_translate_similarity_none_on_empty_back() -> None:
    llm = _RecordingLLM("")
    embedder = _FakeEmbedder({})
    bt = BackTranslate(llm=llm, embedder=embedder)
    out = bt.execute(_translation("hi", "xin chào"), source_lang="en")
    assert out.back_text == ""
    assert out.similarity is None
