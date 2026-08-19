# syntax=docker/dockerfile:1.4
FROM dhi.io/python:3.14-debian13@sha256:aa0ca597178dc1f272f15ed23a213becab317bd8c47af82694a497a51dc8cee6 AS base
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
COPY --from=ghcr.io/astral-sh/uv:0.12.3 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONPATH=/app

FROM base AS builder

# Install system deps needed to build asyncpg/psycopg
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get upgrade -y --no-install-recommends && apt-get install -y --no-install-recommends \
    build-essential=12.12 \
    libpq-dev=17.10-0+deb13u1 \
    && rm -rf /var/lib/apt/lists/*

# Install inference-specific deps, including the shared tracing helper's OTel dependencies.
COPY services/inference/pyproject.toml .
RUN uv sync --no-dev --no-install-project && \
    HF_HUB_DISABLE_XET=1 /app/.venv/bin/python -c \
    "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5')"

# Stage 2: slim production image
FROM dhi.io/python:3.14-debian13@sha256:aa0ca597178dc1f272f15ed23a213becab317bd8c47af82694a497a51dc8cee6 AS runtime
WORKDIR /app

ARG CONTRACTS_VERSION=unknown
LABEL org.opencontainers_image.source="https://github.com/ivan-pi/rpi-api-observatory" \
      org.opencontainers_image.licenses="MIT" \
      org.opencontainers_image.revision="${CONTRACTS_VERSION}" \
      api-observatory.contracts.version="${CONTRACTS_VERSION}"

RUN groupadd --gid 10001 appgroup && \
    useradd --uid 10001 --gid appgroup --shell /bin/false --no-create-home appuser

# Copy Python environment and runtime libs from builder
COPY --from=builder --chown=appuser:appgroup /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appgroup /usr/lib/x86_64-linux-gnu/libpq* /usr/lib/x86_64-linux-gnu/
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

USER 10001

EXPOSE 8001

HEALTHCHECK --interval=5s --timeout=3s --retries=5 --start-period=10s \
  CMD ["/bin/sh", "-c", "python -c 'import urllib.request; urllib.request.urlopen(\"http://127.0.0.1:8001/health\")'"]

CMD ["uvicorn", "services.inference.main:app", "--host", "0.0.0.0", "--port", "8001"]
