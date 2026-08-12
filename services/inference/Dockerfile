# syntax=docker/dockerfile:1.4
FROM python:3.14-slim@sha256:a7fb1e634c4a578f9e0bd6327f11a3cde11b7a9395f48e24360c0988bcc5c2bc AS builder
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# uv — fast dependency installer
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /usr/local/bin/uv

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONPATH=/app

# Install system deps needed to build asyncpg/psycopg
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get upgrade -y --no-install-recommends && apt-get install -y --no-install-recommends \
    build-essential=12.12 \
    libpq-dev=17.10-0+deb13u1 \
    && rm -rf /var/lib/apt/lists/*

# Install inference-specific deps, including the shared tracing helper's OTel dependencies.
COPY services/inference/pyproject.toml .
RUN uv sync --no-dev --no-install-project

# Pre-download the embedding model into the image so first request isn't a
# cold-start network fetch — matches this service's env default model.
# HF_HUB_DISABLE_XET: force plain HTTPS downloads from huggingface.co/resolve
# instead of HF's Xet CAS backend, which redirects through several rotating
# CDN subdomains that are awkward to allowlist in restricted network setups.
RUN HF_HUB_DISABLE_XET=1 /app/.venv/bin/python -c \
    "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5')"

# Stage 2: slim production image
FROM python:3.14-slim@sha256:a7fb1e634c4a578f9e0bd6327f11a3cde11b7a9395f48e24360c0988bcc5c2bc AS runtime
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
WORKDIR /app

ARG CONTRACTS_VERSION=unknown
LABEL api-observatory.contracts.version="${CONTRACTS_VERSION}"

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get upgrade -y --no-install-recommends && apt-get install -y --no-install-recommends \
    libpq5=17.10-0+deb13u1 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 10001 appgroup && \
    useradd --uid 10001 --gid appgroup --shell /bin/false --no-create-home appuser

COPY --from=builder --chown=appuser:appgroup /app/.venv /app/.venv
# Pre-downloaded model cache — HOME=/tmp below must match where it was cached.
COPY --from=builder --chown=appuser:appgroup /root/.cache /tmp/.cache

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONUNBUFFERED=1 \
    HOME="/tmp" \
    HF_HUB_DISABLE_XET=1

COPY --chown=appuser:appgroup services/__init__.py ./services/
COPY --chown=appuser:appgroup libs/ ./libs/
COPY --chown=appuser:appgroup services/inference/alembic.ini ./alembic.ini
COPY --chown=appuser:appgroup services/inference/alembic/ ./alembic/
COPY --chown=appuser:appgroup services/inference/ ./services/inference/

USER appuser

EXPOSE 8001

HEALTHCHECK --interval=5s --timeout=3s --retries=5 --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health')" || exit 1

CMD ["uvicorn", "services.inference.main:app", "--host", "0.0.0.0", "--port", "8001"]
