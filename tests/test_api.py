"""HTTP API smoke tests.

Exercises the FastAPI surface end-to-end against a stub translator. The
real ``router.translate`` is swapped out so we avoid LLM calls and just
verify plumbing: upload, run status, output download, error handling.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from rag.domain import RunConfig
from rag.frameworks.api import create_app


class _InlineExecutor:
    """Duck-types ThreadPoolExecutor — runs submitted jobs inline."""

    def submit(self, fn, *args, **kwargs):  # type: ignore[no-untyped-def]
        fn(*args, **kwargs)

        class _F:
            def result(self, timeout: float | None = None) -> None:
                return None

        return _F()

    def shutdown(self, wait: bool = True) -> None:
        return None


def _fake_translator(record: list[RunConfig]):
    def _translate(config: RunConfig) -> dict[str, Any]:
        record.append(config)
        run_dir = config.run_dir
        run_dir.mkdir(parents=True, exist_ok=True)
        outputs: dict[str, str] = {}
        per_lang: dict[str, dict[str, Any]] = {}
        for lang in config.target_langs:
            out = config.source_path.with_name(
                f"{config.source_path.stem}.{lang}{config.source_path.suffix}"
            )
            out.write_text(f"[{lang}] translated from {config.source_path.name}\n", encoding="utf-8")
            outputs[lang] = str(out)
            per_lang[lang] = {
                "chunks_total": 1,
                "chunks_passed": 1,
                "chunks_retried": 0,
                "chunks_escalated": 0,
                "output_path": str(out),
            }
        manifest = {
            "run_id": config.run_id,
            "source_path": str(config.source_path),
            "target_langs": config.target_langs,
            "status": "done",
            "per_lang": per_lang,
        }
        (run_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return manifest

    return _translate


@pytest.fixture
def client(tmp_path: Path):
    record: list[RunConfig] = []
    app = create_app(
        runs_root=tmp_path / "runs",
        translator=_fake_translator(record),
        executor=_InlineExecutor(),
    )
    client = TestClient(app)
    client.record = record  # type: ignore[attr-defined]
    return client


def test_healthz_ok(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_post_run_kicks_off_pipeline_and_returns_run_id(
    client: TestClient, tmp_path: Path
) -> None:
    response = client.post(
        "/runs",
        data={"target_langs": "vi,fr", "source_lang": "en"},
        files={"file": ("hello.txt", b"Hello, world!\n", "text/plain")},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    run_id = body["run_id"]
    assert run_id.endswith(tuple("0123456789abcdef"))  # hex suffix

    # Inline executor means the fake translator ran before the response returned.
    (config,) = client.record  # type: ignore[attr-defined]
    assert config.target_langs == ["vi", "fr"]
    assert config.source_lang == "en"
    assert config.run_id == run_id
    assert config.simple_mode is None
    assert config.roundtrip is False
    assert config.source_path.read_bytes() == b"Hello, world!\n"


def test_get_run_returns_manifest_once_done(client: TestClient) -> None:
    response = client.post(
        "/runs",
        data={"target_langs": "vi"},
        files={"file": ("note.md", b"# Hi\n", "text/markdown")},
    )
    run_id = response.json()["run_id"]

    status = client.get(f"/runs/{run_id}")
    assert status.status_code == 200
    manifest = status.json()
    assert manifest["status"] == "done"
    assert manifest["target_langs"] == ["vi"]
    assert "vi" in manifest["per_lang"]


def test_get_output_streams_translated_file(client: TestClient) -> None:
    response = client.post(
        "/runs",
        data={"target_langs": "vi"},
        files={"file": ("note.txt", b"Hello.\n", "text/plain")},
    )
    run_id = response.json()["run_id"]

    download = client.get(f"/runs/{run_id}/outputs/vi")
    assert download.status_code == 200
    assert download.content.decode("utf-8").startswith("[vi] translated from")


def test_unknown_run_id_returns_404(client: TestClient) -> None:
    response = client.get("/runs/does-not-exist")
    assert response.status_code == 404


def test_unsupported_extension_rejected(client: TestClient) -> None:
    response = client.post(
        "/runs",
        data={"target_langs": "vi"},
        files={"file": ("doc.pdf", b"%PDF-1.4\n", "application/pdf")},
    )
    assert response.status_code == 415


def test_missing_target_langs_rejected(client: TestClient) -> None:
    response = client.post(
        "/runs",
        data={"target_langs": "  "},
        files={"file": ("note.txt", b"hi\n", "text/plain")},
    )
    assert response.status_code == 422


def test_simple_and_roundtrip_flags_flow_into_config(
    client: TestClient,
) -> None:
    response = client.post(
        "/runs",
        data={
            "target_langs": "vi",
            "simple": "true",
            "roundtrip": "true",
        },
        files={"file": ("note.txt", b"hi\n", "text/plain")},
    )
    assert response.status_code == 202
    (config,) = client.record  # type: ignore[attr-defined]
    assert config.simple_mode is True
    assert config.roundtrip is True


def test_translator_failure_writes_error_status(tmp_path: Path) -> None:
    def _boom(_cfg: RunConfig) -> None:
        raise RuntimeError("kaboom")

    app = create_app(
        runs_root=tmp_path / "runs",
        translator=_boom,
        executor=_InlineExecutor(),
    )
    client = TestClient(app)

    response = client.post(
        "/runs",
        data={"target_langs": "vi"},
        files={"file": ("note.txt", b"hi\n", "text/plain")},
    )
    run_id = response.json()["run_id"]

    status = client.get(f"/runs/{run_id}")
    assert status.status_code == 200
    body = status.json()
    assert body["status"] == "error"
    assert "kaboom" in body["error"]


def test_output_404_when_lang_missing(client: TestClient) -> None:
    response = client.post(
        "/runs",
        data={"target_langs": "vi"},
        files={"file": ("note.txt", b"hi\n", "text/plain")},
    )
    run_id = response.json()["run_id"]
    missing = client.get(f"/runs/{run_id}/outputs/de")
    assert missing.status_code == 404


def test_path_traversal_rejected(client: TestClient) -> None:
    response = client.get("/runs/..%2Fetc")
    # FastAPI decodes %2F; the handler rejects slashes explicitly.
    assert response.status_code in (400, 404)
