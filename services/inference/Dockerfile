# syntax=docker/dockerfile:1.4
FROM dhi.io/python:3.14-debian13-dev@sha256:1977c4a9624171ef582e641eb6f67adfc3f4b3ec0cb59345876f1928cda6f698 AS base
ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
COPY --from=dhi.io/uv:debian-13-0@sha256:1ee4bf660dfd7e31bbb6eba8adb17d85dec1ff2fb3280e077067d8dc1537d472 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONPATH=/app

FROM base AS builder

# Install system deps needed to build asyncpg/psycopg
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install inference-specific deps, including the shared tracing helper's OTel dependencies.
COPY services/inference/pyproject.toml .
RUN uv sync --no-dev --no-install-project && \
    HF_HUB_DISABLE_XET=1 /app/.venv/bin/python -c \
    "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5')"

# Stage 2: slim production image
FROM dhi.io/python:3.14-debian13-dev@sha256:1977c4a9624171ef582e641eb6f67adfc3f4b3ec0cb59345876f1928cda6f698 AS runtime
ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

ARG CONTRACTS_VERSION=unknown
LABEL org.opencontainers_image.source="https://github.com/ivan-pi/rpi-api-observatory" \
      org.opencontainers_image.licenses="MIT" \
      org.opencontainers_image.revision="${CONTRACTS_VERSION}" \
      api-observatory.contracts.version="${CONTRACTS_VERSION}"

# Copy Python environment and runtime libs from builder
COPY --from=builder --chown=65532:65532 /app/.venv /app/.venv
COPY --from=builder --chown=65532:65532 /usr/lib/x86_64-linux-gnu/libpq* /usr/lib/x86_64-linux-gnu/
# Pre-downloaded model cache — HOME=/tmp below must match where it was cached.
COPY --from=builder --chown=65532:65532 /root/.cache /tmp/.cache

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONUNBUFFERED=1 \
    HOME="/tmp" \
    HF_HUB_DISABLE_XET=1

COPY --chown=65532:65532 services/__init__.py ./services/
COPY --chown=65532:65532 libs/ ./libs/
COPY --chown=65532:65532 services/inference/alembic.ini ./alembic.ini
COPY --chown=65532:65532 services/inference/alembic/ ./alembic/
COPY --chown=65532:65532 services/inference/ ./services/inference/

USER 65532

EXPOSE 8001

HEALTHCHECK --interval=5s --timeout=3s --retries=5 --start-period=10s \
  CMD ["/bin/sh", "-c", "python -c 'import urllib.request; urllib.request.urlopen(\"http://127.0.0.1:8001/health\")'"]

CMD ["uvicorn", "services.inference.main:app", "--host", "0.0.0.0", "--port", "8001"]
