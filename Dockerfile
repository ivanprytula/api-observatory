# syntax=docker/dockerfile:1.4
FROM python:3.14-slim@sha256:ce40764625a4ff50df3548277632e7f96c4e77fe75fa848aae9885476e7df5a4 AS base
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
COPY --from=ghcr.io/astral-sh/uv:0.12.3 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONPATH=/app

FROM base AS builder

# Install system dependencies for asyncpg/postgresql
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get upgrade -y --no-install-recommends && apt-get install -y --no-install-recommends \
    build-essential=12.12 \
    libpq-dev=17.10-0+deb13u1 \
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
FROM python:3.14-slim@sha256:ce40764625a4ff50df3548277632e7f96c4e77fe75fa848aae9885476e7df5a4 AS runtime
WORKDIR /app

ARG CONTRACTS_VERSION=unknown
LABEL org.opencontainers_image.source="https://github.com/ivan-pi/rpi-api-observatory" \
      org.opencontainers_image.licenses="MIT" \
      org.opencontainers_image.revision="${CONTRACTS_VERSION}" \
      api-observatory.contracts.version="${CONTRACTS_VERSION}"

# Create non-root user for security
RUN groupadd --gid 10001 appgroup && \
    useradd --uid 10001 --gid appgroup --shell /bin/false --no-create-home appuser

# Copy Python environment and runtime libs from builder
COPY --from=builder --chown=appuser:appgroup /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appgroup /usr/lib/x86_64-linux-gnu/libpq* /usr/lib/x86_64-linux-gnu/
# HOME set to /tmp for Streamlit config/cache (read_only rootfs compatible)
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONUNBUFFERED=1 \
    HOME="/tmp"

# Copy source code — most frequently changed files last for cache efficiency
COPY --chown=appuser:appgroup libs/ ./libs/
COPY --chown=appuser:appgroup alembic.ini ./
COPY --chown=appuser:appgroup alembic/ ./alembic/
COPY --chown=appuser:appgroup services/ingestor/ ./services/ingestor/

USER 10001

# Port for FastAPI
EXPOSE 8000

# Migrations run as an explicit pre-rollout Compose command; this image only serves traffic.
CMD ["uvicorn", "services.ingestor.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
