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

# Install dashboard-specific deps (streamlit + httpx + pydantic only)
COPY services/dashboard/pyproject.toml .
RUN uv sync --no-dev --no-install-project

# Stage 2: slim production image
FROM dhi.io/python:3.14-debian13-dev@sha256:1977c4a9624171ef582e641eb6f67adfc3f4b3ec0cb59345876f1928cda6f698 AS runtime
ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

ARG CONTRACTS_VERSION=unknown
LABEL org.opencontainers_image.source="https://github.com/ivan-pi/rpi-api-observatory" \
      org.opencontainers_image.licenses="MIT" \
      org.opencontainers_image.revision="${CONTRACTS_VERSION}" \
      api-observatory.contracts.version="${CONTRACTS_VERSION}"

# Copy Python environment from builder
COPY --from=builder --chown=65532:65532 /app/.venv /app/.venv

# HOME set to /tmp (read-only rootfs compatible; Streamlit writes cache here)
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONUNBUFFERED=1 \
    HOME="/tmp"

# Copy dashboard source — least-changed layers first for cache efficiency
COPY --chown=65532:65532 services/__init__.py ./services/
COPY --chown=65532:65532 libs/contracts/ ./libs/contracts/
COPY --chown=65532:65532 services/dashboard/ ./services/dashboard/
COPY --chown=65532:65532 .streamlit/ .streamlit/

USER 65532

# Streamlit default port
EXPOSE 8501

HEALTHCHECK --interval=5s --timeout=3s --retries=3 --start-period=10s \
  CMD ["/bin/sh", "-c", "python -c 'import urllib.request; urllib.request.urlopen(\"http://127.0.0.1:8501/_stcore/health\")'"]

# Entry point: new modular structure (was monolithic streamlit_app.py)
CMD ["streamlit", "run", "services/dashboard/ui/streamlit/app.py", \
     "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
