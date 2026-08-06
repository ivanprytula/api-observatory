# syntax=docker/dockerfile:1.4
FROM python:3.14-slim@sha256:a7fb1e634c4a578f9e0bd6327f11a3cde11b7a9395f48e24360c0988bcc5c2bc AS builder
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# uv — fast dependency installer
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /usr/local/bin/uv

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONPATH=/app

# Install dashboard-specific deps (streamlit + httpx + pydantic only)
COPY services/dashboard/pyproject.toml .
RUN uv sync --no-dev --no-install-project

# Stage 2: slim production image
FROM python:3.14-slim@sha256:a7fb1e634c4a578f9e0bd6327f11a3cde11b7a9395f48e24360c0988bcc5c2bc AS runtime
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
WORKDIR /app

# Create non-root user
RUN groupadd --gid 10001 appgroup && \
    useradd --uid 10001 --gid appgroup --shell /bin/false --no-create-home appuser

# Copy Python environment from builder
COPY --from=builder --chown=appuser:appgroup /app/.venv /app/.venv

# HOME set to /tmp (read-only rootfs compatible; Streamlit writes cache here)
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONUNBUFFERED=1 \
    HOME="/tmp"

# Copy dashboard source — least-changed layers first for cache efficiency
COPY --chown=appuser:appgroup services/__init__.py ./services/
COPY --chown=appuser:appgroup libs/contracts/ ./libs/contracts/
COPY --chown=appuser:appgroup services/dashboard/ ./services/dashboard/

USER appuser

# Streamlit default port
EXPOSE 8501

HEALTHCHECK --interval=5s --timeout=3s --retries=3 --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health')" || exit 1

# Entry point: new modular structure (was monolithic streamlit_app.py)
CMD ["streamlit", "run", "services/dashboard/ui/streamlit/app.py", \
     "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
