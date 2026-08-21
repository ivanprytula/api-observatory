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

# Install system dependencies for asyncpg/postgresql
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install deps first (better layer caching)
# --extra ai: the LangGraph incident-triage agent (Phase 3) and /analyze's RAG
# path are core ingestor features, not optional demos — install their deps.
# --extra tracing: OTel SDK + OTLP exporter; without it setup_tracing() degrades
# to a no-op and spans/trace_id correlation are silently lost (post-MVP Phase 0).
# --extra messaging: the opt-in Redpanda notification-consumer command shares
# this image and imports aiokafka without starting the FastAPI lifespan.
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen --no-install-project --extra ai --extra tracing --extra messaging

# Stage 2: Final image — slim, no build tools, non-root user
FROM dhi.io/python:3.14-debian13-dev@sha256:1977c4a9624171ef582e641eb6f67adfc3f4b3ec0cb59345876f1928cda6f698 AS runtime
ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

ARG CONTRACTS_VERSION=unknown
LABEL org.opencontainers_image.source="https://github.com/ivanprytula/api-observatory" \
      org.opencontainers_image.licenses="Apache-2.0" \
      org.opencontainers_image.revision="${CONTRACTS_VERSION}" \
      api-observatory.contracts.version="${CONTRACTS_VERSION}"

# Copy Python environment and runtime libs from builder
COPY --from=builder --chown=65532:65532 /app/.venv /app/.venv
COPY --from=builder --chown=65532:65532 /usr/lib/x86_64-linux-gnu/libpq* /usr/lib/x86_64-linux-gnu/
# HOME set to /tmp for Streamlit config/cache (read_only rootfs compatible)
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONUNBUFFERED=1 \
    HOME="/tmp"

# Copy source code — most frequently changed files last for cache efficiency
COPY --chown=65532:65532 libs/ ./libs/
COPY --chown=65532:65532 alembic.ini ./
COPY --chown=65532:65532 alembic/ ./alembic/
COPY --chown=65532:65532 services/ingestor/ ./services/ingestor/
COPY --chown=65532:65532 scripts/seed_admin.py ./scripts/seed_admin.py

USER 65532

# Port for FastAPI
EXPOSE 8000

# Migrations run as an explicit pre-rollout Compose command; this image only serves traffic.
CMD ["uvicorn", "services.ingestor.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
