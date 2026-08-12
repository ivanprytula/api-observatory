# syntax=docker/dockerfile:1.4
# pgvector/pgvector:pg17-trixie — postgres:17 with pgvector pre-installed on newer Debian.
# no manual compilation required.
# Base-image digests are updated with `just update-base-image-digest`.

FROM pgvector/pgvector:pg17-trixie@sha256:a74b9af952f5609c090120bf938b0c8bca56c33ed9fb05643fd9fceec52c4a08

RUN apt-get update \
	&& apt-get upgrade -y --no-install-recommends \
	&& rm -rf /var/lib/apt/lists/*
