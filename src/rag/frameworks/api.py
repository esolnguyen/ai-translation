"""HTTP API for the RAG pipeline.

A small FastAPI surface around ``router.translate``. Runs are asynchronous
from the client's perspective: ``POST /runs`` writes the uploaded source
into a fresh scratchpad, kicks the pipeline off on a worker thread, and
returns immediately with the ``run_id``. Clients poll ``GET /runs/{id}``
for status (backed by ``manifest.json``) and download translated files
via ``GET /runs/{id}/outputs/{lang}``.

Run this entry point with ``translate-api`` (installs as a console script
when the ``api`` extra is present); the composition root is the same
:func:`rag.router.translate` the CLI uses, so behaviour is identical.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import shutil
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from ..domain import RunConfig
from ..router import translate as run_translate

logger = logging.getLogger(__name__)

_RUNS_DIR_ENV = "RAG_API_RUNS_DIR"
_DEFAULT_RUNS_DIR = Path(".translate-runs")
_SUPPORTED_SUFFIXES = {".txt", ".md", ".srt", ".xlsx", ".docx"}

_LOGGING_CONFIGURED = False


def _configure_logging(level: str | None = None) -> None:
    """Idempotent bootstrap. Runs in both ``main()`` and ``create_app()``
    so the uvicorn ``--reload`` worker process (which never enters main)
    still gets the same env, root logging, and noise suppression as the
    parent. Loads ``.env`` via python-dotenv so ``RAG_LLM`` and provider
    creds reach the worker even when launched from a fresh shell.
    """
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return
    import warnings

    try:
        from dotenv import load_dotenv

        load_dotenv(override=True)
    except ImportError:
        pass

    chosen = (level or os.environ.get("RAG_LOG_LEVEL", "INFO")).upper()
    logging.basicConfig(
        level=chosen,
        format="%(asctime)s %(levelname)-5s %(name)s :: %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )
    for name in (
        "chromadb.telemetry",
        "chromadb.telemetry.product",
        "chromadb.telemetry.product.posthog",
    ):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    warnings.filterwarnings(
        "ignore",
        message=r".*doesn't match a supported version.*",
    )
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
    _LOGGING_CONFIGURED = True


def create_app(
    *,
    runs_root: Path | None = None,
    translator: Any = run_translate,
    executor: ThreadPoolExecutor | None = None,
) -> FastAPI:
    """Build a FastAPI app with all dependencies resolved.

    Accepts overrides for tests: swap ``translator`` for a stub and
    ``runs_root`` to redirect persistence. An ``executor`` override lets
    tests run jobs synchronously via a dummy executor if needed.
    """

    _configure_logging()
    root = runs_root or Path(os.environ.get(_RUNS_DIR_ENV, str(_DEFAULT_RUNS_DIR)))
    pool = executor or ThreadPoolExecutor(max_workers=2, thread_name_prefix="rag-api")

    app = FastAPI(title="ai-translation RAG API", version="0.1")
    app.state.runs_root = root
    app.state.translator = translator
    app.state.executor = pool

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/runs", status_code=202)
    async def create_run(
        background_tasks: BackgroundTasks,
        file: UploadFile,
        target_langs: str = Form(...),
        source_lang: str = Form("en"),
        simple: str | None = Form(None),
        roundtrip: bool = Form(False),
    ) -> JSONResponse:
        langs = [t.strip() for t in target_langs.split(",") if t.strip()]
        if not langs:
            raise HTTPException(422, detail="target_langs must list at least one code")
        if file.filename is None:
            raise HTTPException(422, detail="uploaded file must have a filename")
        suffix = Path(file.filename).suffix.lower()
        if suffix not in _SUPPORTED_SUFFIXES:
            raise HTTPException(
                415,
                detail=(
                    f"unsupported source format: {suffix or '(none)'}. "
                    f"Supported: {', '.join(sorted(_SUPPORTED_SUFFIXES))}"
                ),
            )

        run_id = _new_run_id(file.filename)
        run_dir = root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        source_path = run_dir / f"source{suffix}"
        with source_path.open("wb") as fh:
            shutil.copyfileobj(file.file, fh)

        simple_mode = _parse_tristate(simple)
        config = RunConfig(
            source_path=source_path,
            target_langs=langs,
            source_lang=source_lang,
            run_id=run_id,
            run_root=root,
            simple_mode=simple_mode,
            roundtrip=roundtrip,
        )
        _write_status(run_dir, {"run_id": run_id, "status": "queued"})
        logger.info(
            "run queued run_id=%s file=%s langs=%s simple=%s roundtrip=%s",
            run_id,
            file.filename,
            langs,
            simple_mode,
            roundtrip,
        )

        background_tasks.add_task(_execute_run, app, config, run_dir)
        return JSONResponse(
            {"run_id": run_id, "status": "queued"},
            status_code=202,
        )

    @app.get("/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        run_dir = _resolve_run_dir(root, run_id)
        manifest_path = run_dir / "manifest.json"
        if manifest_path.exists():
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        status_path = run_dir / "status.json"
        if status_path.exists():
            return json.loads(status_path.read_text(encoding="utf-8"))
        raise HTTPException(404, detail=f"run not found: {run_id}")

    @app.get("/runs/{run_id}/outputs/{lang}")
    def get_output(run_id: str, lang: str) -> FileResponse:
        run_dir = _resolve_run_dir(root, run_id)
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.exists():
            raise HTTPException(404, detail=f"run not finished: {run_id}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        per_lang = manifest.get("per_lang") or {}
        entry = per_lang.get(lang)
        if not entry or not entry.get("output_path"):
            raise HTTPException(404, detail=f"no output for lang {lang}")
        path = Path(entry["output_path"])
        if not path.exists():
            raise HTTPException(
                410,
                detail=f"output file missing on disk: {path}",
            )
        return FileResponse(path, filename=path.name)

    return app


def _execute_run(app: FastAPI, config: RunConfig, run_dir: Path) -> None:
    executor: ThreadPoolExecutor = app.state.executor
    translator = app.state.translator
    executor.submit(_run_in_thread, translator, config, run_dir)


def _run_in_thread(translator: Any, config: RunConfig, run_dir: Path) -> None:
    started = time.perf_counter()
    logger.info("run start  run_id=%s source=%s", config.run_id, config.source_path)
    try:
        translator(config)
    except Exception as exc:
        payload = {
            "run_id": config.run_id,
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        }
        _write_status(run_dir, payload)
        logger.exception(
            "run failed run_id=%s elapsed=%.2fs",
            config.run_id,
            time.perf_counter() - started,
        )
        return
    logger.info(
        "run done   run_id=%s elapsed=%.2fs",
        config.run_id,
        time.perf_counter() - started,
    )


def _write_status(run_dir: Path, payload: dict[str, Any]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "status.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _resolve_run_dir(root: Path, run_id: str) -> Path:
    if "/" in run_id or ".." in run_id:
        raise HTTPException(400, detail="invalid run_id")
    run_dir = root / run_id
    if not run_dir.exists():
        raise HTTPException(404, detail=f"run not found: {run_id}")
    return run_dir


def _parse_tristate(value: str | None) -> bool | None:
    if value is None or value == "":
        return None
    lowered = value.strip().lower()
    if lowered in {"true", "1", "yes", "on"}:
        return True
    if lowered in {"false", "0", "no", "off"}:
        return False
    raise HTTPException(422, detail=f"invalid simple flag: {value!r}")


def _new_run_id(source_filename: str) -> str:
    stem = Path(source_filename).stem or "upload"
    return f"{int(time.time())}-{stem}-{secrets.token_hex(3)}"


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``translate-api`` console script."""
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(prog="translate-api")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument(
        "--log-level",
        default=os.environ.get("RAG_LOG_LEVEL", "INFO"),
        help="root log level (DEBUG, INFO, WARNING, ERROR). Default INFO.",
    )
    args = parser.parse_args(argv)

    # Pin RAG_LOG_LEVEL so the reload-spawned worker process inherits the
    # same level when it imports the app and re-runs _configure_logging().
    os.environ["RAG_LOG_LEVEL"] = args.log_level.upper()
    _configure_logging(args.log_level)

    reload_kwargs: dict[str, Any] = {}
    if args.reload:
        # Watch only the source tree. Keeps reload working for code edits
        # while ignoring write churn from .claude/, .kb/, .translate-runs/,
        # vault/, sources/, and the like.
        reload_kwargs = {
            "reload_dirs": ["src"],
            "reload_includes": ["*.py"],
        }
        # Silence watchfiles' "N changes detected" batch counter; the
        # reload itself still logs via uvicorn's own reloader output.
        logging.getLogger("watchfiles").setLevel(logging.WARNING)
        logging.getLogger("watchfiles.main").setLevel(logging.WARNING)

    uvicorn.run(
        "rag.frameworks.api:create_app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        factory=True,
        log_level=args.log_level.lower(),
        **reload_kwargs,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
