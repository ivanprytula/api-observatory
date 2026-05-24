# syntax=docker/dockerfile:1.4
# postgis/postgis:17-3.4 — postgres:17-bookworm with PostGIS 3.4 pre-installed.
# pgvector is compiled and installed on top for vector similarity search.
# Digest pinning: update monthly via docs/setup/digest-update-runbook.md
# TODO: pin to a digest once a specific 17-3.4 digest is validated

FROM postgis/postgis:17-3.4
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install build dependencies required for pgvector compilation
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    clang-13 \
    llvm-13 \
    postgresql-server-dev-17 \
    git \
    && git clone --branch v0.7.4 https://github.com/pgvector/pgvector.git /tmp/pgvector && \
    cd /tmp/pgvector && \
    make && \
    make install && \
    rm -rf /tmp/pgvector && \
    apt-get remove -y build-essential clang-13 llvm-13 git postgresql-server-dev-17 && \
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
