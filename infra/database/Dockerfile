# syntax=docker/dockerfile:1.4
# pgvector/pgvector:pg17-trixie — postgres:17 with pgvector pre-installed on newer Debian.
# No PostGIS; no manual compilation required.
# Digest pinning: update monthly via docs/setup/digest-update-runbook.md

FROM pgvector/pgvector:pg17-trixie

RUN apt-get update \
	&& apt-get upgrade -y --no-install-recommends \
	&& rm -rf /var/lib/apt/lists/*
