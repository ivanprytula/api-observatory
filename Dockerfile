# syntax=docker/dockerfile:1.4
FROM python:3.14-slim@sha256:44dd04494ee8f3b538294360e7c4b3acb87c8268e4d0a4828a6500b1eff50061 AS builder
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# uv — fast dependency installer
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /usr/local/bin/uv

# Install system dependencies for asyncpg/postgresql
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get upgrade -y --no-install-recommends && apt-get install -y --no-install-recommends \
    build-essential=12.12 \
    libpq-dev=17.10-0+deb13u1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Install deps first (better layer caching)
# --extra ai: the LangGraph incident-triage agent (Phase 3) and /analyze's RAG
# path are core ingestor features, not optional demos — install their deps.
# --extra tracing: OTel SDK + OTLP exporter; without it setup_tracing() degrades
# to a no-op and spans/trace_id correlation are silently lost (post-MVP Phase 0).
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen --no-install-project --extra ai --extra tracing

# Stage 2: Final image — slim, no build tools, non-root user
FROM python:3.14-slim@sha256:44dd04494ee8f3b538294360e7c4b3acb87c8268e4d0a4828a6500b1eff50061 AS runtime
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
WORKDIR /app

# Install system deps for asyncpg
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get upgrade -y --no-install-recommends && apt-get install -y --no-install-recommends \
    libpq5=17.10-0+deb13u1 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd --gid 10001 appgroup && \
    useradd --uid 10001 --gid appgroup --shell /bin/false --no-create-home appuser

# Copy Python environment from builder (avoid extra layer from recursive chown)
COPY --from=builder --chown=appuser:appgroup /app/.venv /app/.venv
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

USER appuser

# Port for FastAPI
EXPOSE 8000

# Run database migrations and start the FastAPI server
CMD ["uvicorn", "services.ingestor.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
