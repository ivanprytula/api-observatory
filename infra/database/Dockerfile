# syntax=docker/dockerfile:1.4
# pgvector/pgvector:pg17-trixie — postgres:17 with pgvector pre-installed on newer Debian.
# no manual compilation required.
# Base-image digests are updated with `just update-base-image-digest`.

FROM pgvector/pgvector:pg17-trixie@sha256:724a4041afdb1750446e3f6b5cfa8f3b0ac5a2cf538ddfa6bfee4f94c2fa85c6

ARG CONTRACTS_VERSION=unknown
LABEL org.opencontainers_image.source="https://github.com/ivan-pi/rpi-api-observatory" \
      org.opencontainers_image.licenses="MIT" \
      org.opencontainers_image.revision="${CONTRACTS_VERSION}"

RUN apt-get update \
	&& apt-get upgrade -y --no-install-recommends \
	&& rm -rf /var/lib/apt/lists/*

HEALTHCHECK --interval=10s --timeout=3s --retries=6 \
  CMD pg_isready -U postgres
