# syntax=docker/dockerfile:1.4
# dhi.io/pgvector:0.8-pg17-debian13 — postgres:17 with pgvector pre-installed on hardened Debian 13.
# no manual compilation required.
# Base-image digests are updated with `just update-base-image-digest`.

FROM dhi.io/pgvector:0.8-pg17-debian13@sha256:d91ee73792106b6d657af8803a12670b871c8ef9bc70516d853867a53f941734

ARG CONTRACTS_VERSION=unknown
LABEL org.opencontainers_image.source="https://github.com/ivan-pi/rpi-api-observatory" \
      org.opencontainers_image.licenses="MIT" \
      org.opencontainers_image.revision="${CONTRACTS_VERSION}"

RUN apt-get update \
	&& apt-get upgrade -y --no-install-recommends \
	&& rm -rf /var/lib/apt/lists/*

HEALTHCHECK --interval=10s --timeout=3s --retries=6 \
  CMD ["pg_isready", "-U", "postgres"]
