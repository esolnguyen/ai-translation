"""CLI smoke tests — exercise ``kb index`` + retrieval subcommands end-to-end.

Uses the in-memory fakes so tests stay fast and don't hit Chroma or load
any real embedding model.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from knowledge.cli import main as cli
from knowledge.core.entities import EntityStore
from knowledge.core.glossary import GlossaryStore
from knowledge.core.languages import LanguageStore
from knowledge.core.retrieval import Retriever

from .fakes import FakeEmbedder, InMemoryStore

FIXTURE_VAULT = Path(__file__).parent / "fixtures" / "vault"


@pytest.fixture
def fake_retriever(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Retriever:
    """Patch the CLI's ``Retriever.from_env`` to return one backed by fakes."""
    retriever = Retriever(
        embedder=FakeEmbedder(),
        store=InMemoryStore(),
        glossary_store=GlossaryStore(tmp_path / "glossary.json"),
        entity_store=EntityStore(tmp_path / "entities.json"),
        language_store=LanguageStore(tmp_path / "languages.json"),
    )
    monkeypatch.setattr(cli, "Retriever", type("R", (), {"from_env": staticmethod(lambda: retriever)}))
    monkeypatch.setenv("KB_VAULT", str(FIXTURE_VAULT))
    return retriever


def test_kb_index_then_search(
    fake_retriever: Retriever,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["index", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["notes"]["added"] >= 1
    assert report["examples"]["added"] == 1

    assert cli.main(["search", "contract termination", "--domain", "legal", "--k", "3"]) == 0
    hits = json.loads(capsys.readouterr().out)
    assert hits
    assert hits[0]["metadata"]["note_id"] == "legal-contract-terms"


def test_kb_glossary_and_lang_card(
    fake_retriever: Retriever,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli.main(["index", "--json"])
    capsys.readouterr()

    assert cli.main(["glossary", "settlement", "--target", "ja"]) == 0
    entry = json.loads(capsys.readouterr().out)
    assert entry["id"] == "glossary-settlement"

    assert cli.main(["lang-card", "ja"]) == 0
    card = json.loads(capsys.readouterr().out)
    assert card["lang"] == "ja"


def test_kb_examples_add_writes_needs_review(
    fake_retriever: Retriever,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = tmp_path / "new-vault"
    vault.mkdir()
    monkeypatch.setenv("KB_VAULT", str(vault))

    src_file = tmp_path / "src.txt"
    src_file.write_text("Hello", encoding="utf-8")
    tgt_file = tmp_path / "tgt.txt"
    tgt_file.write_text("こんにちは", encoding="utf-8")

    rc = cli.main(
        [
            "examples",
            "add",
            str(src_file),
            str(tgt_file),
            "--src",
            "en",
            "--tgt",
            "ja",
            "--domain",
            "greetings",
            "--id",
            "ex-hello",
        ]
    )
    assert rc == 0
    result = json.loads(capsys.readouterr().out)
    written = Path(result["wrote"])
    assert written.exists()
    content = written.read_text(encoding="utf-8")
    assert "status: needs-review" in content
    assert "Hello" in content
    assert "こんにちは" in content
