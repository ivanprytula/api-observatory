# ADR 004: Docker BuildKit, Image Optimization, and Security Scanning

Track: C — Architecture and Platform Strategy

**Status**: Adopted (April 22, 2026)
**Decision Date**: April 22, 2026
**Scope**: Current application and database Dockerfiles

---

## Context

The original decision assumed six application services. The current deployable HTTP contract is
ingestor, inference, and dashboard; local Compose also runs their dependencies. The security and
reproducibility decision remains applicable even though the old service inventory does not.

1. **Ingestor** — FastAPI REST API and background work
2. **Inference** — embeddings and vector search
3. **Dashboard** — Streamlit UI
4. **Databases and local dependencies** — PostgreSQL/pgvector, cache, and Redpanda

As of April 22, 2026, Dockerfiles lacked:

- BuildKit support for layer caching optimization
- Base image digest pinning (reproducibility risk)
- Automated security scanning for dependencies and container images
- Consistent multi-stage build patterns across all services

**Problem**: Rebuilds were slow (~2-3 min), builds were non-reproducible, and no vulnerability scanning for supply chain security.

---

## Decision

### 1. Adopt BuildKit with Cache Mounts (APPROVED)

**Choice**: Enable BuildKit syntax (1.4) with persistent apt cache mounts.

**Rationale**: `--mount=type=cache,target=/var/cache/apt,sharing=locked` persists package cache across builds; second build runs 3-5x faster. BuildKit is stable since Docker v20.10.

**Trade-off**: Slight image size increase (~50MB cache per layer), but faster rebuilds offset cost.

### 2. Pin Base Images to SHA256 Digests (APPROVED)

**Choice**: Lock `python:3.14-slim` and `postgres:17-bookworm` to specific digest hashes.

**Rationale**: Prevents surprise base image updates, ensures reproducible builds across all developers and CI/CD runners. Allows controlled upgrades.

**Trade-off**: Requires monthly digest review; base-image digests are updated with
the [`scripts/update-base-image-digest.sh`](../../../scripts/update-base-image-digest.sh) helper.

### 3. Adopt Docker Image Vulnerability Scanning (APPROVED)

**Choice**: Integrate **Trivy** (Aqua Security) + **pip-audit** (PyPA) for multi-layer security scanning.

**Rejected Alternatives**:
- Snyk: powerful but requires commercial subscription
- Clair: requires separate infrastructure
- Grype: good but Trivy is more Docker-optimized

### 4. Security Scanning in CI/CD (APPROVED)

**Choice**: GitHub Actions workflow: pip-audit on PR/push + Trivy scan after Docker build + SARIF reports surfaced as Code Scanning alerts.

---

## Consequences

### Positive

- 3-5x faster Docker rebuilds (BuildKit cache)
- Reproducible builds across team (digest pinning)
- Early vulnerability detection (pip-audit + Trivy)
- No additional infrastructure/cost (free tools)

### Negative

- Slight increase in build artifact size (~50MB)
- Manual coordination needed for base image upgrades
- Trivy scan adds ~30-60s to CI/CD pipeline
- Developers must use `export DOCKER_BUILDKIT=1` locally

### Mitigation

- Set `DOCKER_BUILDKIT=1` as default in `.env` or CI/CD config
- Monthly base image upgrade cadence (1st Monday)

---

## Implementation

Detailed setup instructions, tool installation, usage examples, troubleshooting, and CI/CD workflow YAMLs are in the Docker Security Scanning Setup guide (Track B — Engineering Execution).

---

## Related

- [ADR 001: Kafka vs RabbitMQ](001-kafka-vs-rabbitmq.md) (event streaming)
- Docker Security Scanning Setup (Setup Guide)
- [Base-image digest updater](../../../scripts/update-base-image-digest.sh)
