# syntax=docker/dockerfile:1.7

# ─── Stage 1: build wheel ──────────────────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/clis ./src/clis
COPY src/knowledge ./src/knowledge
COPY src/metrics ./src/metrics
COPY src/rag ./src/rag

RUN pip install --upgrade pip build \
    && python -m build --wheel --outdir /wheels .


# ─── Stage 2: runtime ──────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/hf-cache \
    KB_VAULT=/data/vault \
    KB_STORE_PATH=/data/kb \
    RAG_API_RUNS_DIR=/data/runs \
    ANONYMIZED_TELEMETRY=False

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /wheels /wheels

# Install the wheel with the extras the containerized service actually uses.
# `agents` (Claude Code skills) is intentionally excluded; host-specific.
RUN pip install --upgrade pip \
    && pip install /wheels/*.whl \
        "ai-translation-knowledge[rag,api,extract,azure-openai,gemini]" \
        python-dotenv \
    && rm -rf /wheels

RUN useradd --create-home --uid 1000 app \
    && mkdir -p /data/vault /data/kb /data/runs /data/sources /hf-cache \
    && chown -R app:app /data /hf-cache

USER app

EXPOSE 8000

# Default: boot the FastAPI service. Override for CLI use:
#   docker run --rm image translate kb index
#   docker run --rm image translate run path/to/file --to vi
CMD ["translate-api", "--host", "0.0.0.0", "--port", "8000"]
