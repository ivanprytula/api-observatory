# syntax=docker/dockerfile:1.4
FROM python:3.14-slim@sha256:5b3879b6f3cb77e712644d50262d05a7c146b7312d784a18eff7ff5462e77033 AS builder
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# uv — fast dependency installer
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /usr/local/bin/uv

# Install system dependencies for asyncpg/postgresql
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get upgrade -y --no-install-recommends && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Install deps first (better layer caching)
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen --no-install-project

# Stage 2: Final image — slim, no build tools, non-root user
FROM python:3.14-slim@sha256:5b3879b6f3cb77e712644d50262d05a7c146b7312d784a18eff7ff5462e77033
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
WORKDIR /app

# Install system deps for asyncpg
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get upgrade -y --no-install-recommends && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --shell /bin/false --no-create-home appuser

# Copy Python environment from builder (avoid extra layer from recursive chown)
COPY --from=builder --chown=appuser:appgroup /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONUNBUFFERED=1

# Copy source code and migration files
COPY --chown=appuser:appgroup libs/ ./libs/
COPY --chown=appuser:appgroup services/ingestor/ ./services/ingestor/

USER appuser

# Port for FastAPI
EXPOSE 8000

CMD ["uvicorn", "services.ingestor.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
