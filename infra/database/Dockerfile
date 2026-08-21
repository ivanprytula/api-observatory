# syntax=docker/dockerfile:1.4
# dhi.io/pgvector:0.8-pg17-debian13-dev — postgres:17 with pgvector pre-installed on hardened Debian 13 dev image (includes shell + package manager).
# no manual compilation required.
# Base-image digests are updated with `just update-base-image-digest`.

FROM dhi.io/pgvector:0.8-pg17-debian13-dev@sha256:bebc78fa7124cf0cc1e38233d87197606aea45e288ec68841a84ae9f3300b529

ENV DEBIAN_FRONTEND=noninteractive

ARG CONTRACTS_VERSION=unknown
LABEL org.opencontainers_image.source="https://github.com/ivan-pi/rpi-api-observatory" \
      org.opencontainers_image.licenses="MIT" \
      org.opencontainers_image.revision="${CONTRACTS_VERSION}"

RUN apt-get update \
	&& rm -rf /var/lib/apt/lists/*

HEALTHCHECK --interval=10s --timeout=3s --retries=6 \
  CMD ["pg_isready", "-U", "postgres"]
