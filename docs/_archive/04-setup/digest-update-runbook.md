# Monthly Digest Review & Update Runbook

Track: B — Engineering Execution

**Status**: Active (Starting April 2026)
**Frequency**: 1st Monday of each month
**Owner**: Infrastructure/Security team
**Duration**: ~30-45 minutes per cycle

---

## Overview

Base image digests (Python, PostgreSQL) must be reviewed monthly for security patches. This runbook guides scanning for vulnerabilities, identifying new digests, testing, and merging updates.

Why digest pinning matters:

- ✅ Ensures reproducible builds across team
- ✅ Allows detection of base image vulnerabilities
- ✅ Prevents silent breakage from image updates
- ⚠️ Requires intentional updates (manual process, not automatic)

---

## Monthly Schedule

| Date                     | Task                                  | Approx Time |
| ------------------------ | ------------------------------------- | ----------- |
| **1st Monday, 9:00 AM**  | Scan current base images for vulns    | 5 min       |
| **1st Monday, 9:10 AM**  | Research new digests if vulns found   | 10 min      |
| **1st Monday, 9:25 AM**  | Update Dockerfiles with new digests   | 5 min       |
| **1st Monday, 9:35 AM**  | Run local build & security tests      | 10-15 min   |
| **1st Monday, 10:00 AM** | Push to develop, create PR for review | 5 min       |

Calendar reminders: Set recurring calendar event on **1st Monday of month at 9:00 AM UTC**

---

## Step 1: Scan Current Base Images for Vulnerabilities

### Current Pinned Images

```bash
# Python base image
python:3.14-slim@sha256:bc389f7dfcb21413e72a28f491985326994795e34d2b86c8ae2f417b4e7818aa

# PostgreSQL base image (currently NOT pinned — ISSUE!)
postgres:17  # ← VULNERABLE (1 CRITICAL, 13 HIGH as of April 22, 2026)
```

### Scan Script

Run the scan script:

```bash
bash scripts/scan_base_images.sh
```

If vulnerabilities found → proceed to Step 2

---

## Step 2: Research New Base Image Digests

### Python Image: Find Latest Secure Digest

```bash
docker pull python:3.14-slim 2>&1 | grep "Digest:"
```

### PostgreSQL Image: Find Latest Secure Digest

```bash
docker pull postgres:17-alpine 2>&1 | grep "Digest:"
```

Decision: Alpine vs Bookworm?

| Variant                 | Size    | Vulns                  | Notes                                                                     |
| ----------------------- | ------- | ---------------------- | ------------------------------------------------------------------------- |
| `postgres:17-alpine`    | ~100 MB | Fewer (smaller base)   | ❌ Limited apk packages for pgvector build tools                           |
| `postgres:17-bookworm`  | ~250 MB | Fewer than postgres:17 | **✅ Chosen** — Debian tools available, full pgvector v0.7.4 compatibility |
| `postgres:17` (default) | ~250 MB | 1 CRITICAL + 13 HIGH   | ❌ Avoid; vulnerable                                                       |

**⚠️ Current status (April 22, 2026)**: Switched from `postgres:17` to `postgres:17-bookworm`.

- Alpine was initially considered (smaller image) but pgvector build requires `/bin/bash` and Debian build tools unavailable in Alpine apk
- Bookworm provides reliable builds with acceptable image size (~250MB) and pinned digest for reproducibility

### Document New Digests

Record the old and new digests along with vulnerability changes for the PR description.

---

## Step 3: Update Dockerfiles with New Digests

### Python Image Update (if new digest available)

Current line in all 6 Python Dockerfiles:

```dockerfile
FROM python:3.14-slim@sha256:bc389f7dfcb21413e72a28f491985326994795e34d2b86c8ae2f417b4e7818aa
```

Update to:

```dockerfile
FROM python:3.14-slim@sha256:NEW_DIGEST_HERE
```

Apply the new digest to all 6 Python service Dockerfiles.

### PostgreSQL Image Update (Special Case)

Current line in `/infra/database/Dockerfile`:

```dockerfile
FROM postgres:17
```

Update to:

```dockerfile
FROM postgres:17-alpine@sha256:NEW_POSTGRES_ALPINE_DIGEST
```

Why Alpine?

- 🎯 Smaller image (100 MB vs 250 MB)
- 🔒 Fewer OS packages → fewer vulnerabilities
- ⚡ Faster builds and deploys
- ✅ Fully compatible with pgvector extension

Update `infra/database/Dockerfile` with the new base image digest.

---

## Step 4: Test Locally

### Build All Services with New Digests

Run the test script:

```bash
bash scripts/test_digest_updates.sh
```

---

## Step 5: Push & Create PR

### Commit Changes

```bash
git checkout -b chore/update-base-image-digests-$(date +%Y-%m)
git add Dockerfile services/*/Dockerfile infra/database/Dockerfile
git commit -m "chore(deps): update base image digests — $(date +%Y-%m-%d)"
```

### Push to develop

```bash
git push origin chore/update-base-image-digests-$(date +%Y-%m)
```

### Create PR

```bash
# GitHub CLI (if installed)
gh pr create \
  --base develop \
  --title "chore(deps): update base image digests — $(date +%Y-%m)" \
  --body "$(cat /tmp/digest_update_checklist.md)" \
  --label "type/dependency" \
  --label "area/docker-images"
```

Or manually:

1. Go to **Pull Requests** → **New Pull Request**
2. Base: `develop`, Compare: `chore/update-base-image-digests-...`
3. Title: `chore(deps): update base image digests — YYYY-MM`
4. Description: Include vulnerability scan results
5. Reviewers: Assign team lead
6. Labels: `type/dependency`, `area/docker-images`

### Merge Checklist

Before merging:

- [ ] All CI checks passing (build, lint, tests)
- [ ] Security scan shows no new vulns
- [ ] Code review approved
- [ ] Local testing confirmed
- [ ] SBOM generated (Phase 3) and reviewed

---

## Digest Update Decision Tree

```sh
┌─────────────────────────────────────────────┐
│ Monthly Digest Review                       │
└──────────────┬──────────────────────────────┘
               │
               ▼
    ┌──────────────────────┐
    │ Scan base images     │
    │ for vulnerabilities  │
    └──────────┬───────────┘
               │
        ┌──────┴──────┐
        ▼             ▼
    No vulns     Vulns found
        │             │
        │             ▼
        │    ┌──────────────────────┐
        │    │ Research new digests │
        │    │ (Docker Hub, skopeo) │
        │    └──────────┬───────────┘
        │               │
        │               ▼
        │    ┌──────────────────────┐
        │    │ Update Dockerfiles   │
        │    │ with new digests     │
        │    └──────────┬───────────┘
        │               │
        └───────┬───────┘
                │
                ▼
        ┌──────────────────────┐
        │ Test locally         │
        │ - Build all services │
        │ - Trivy scan         │
        │ - docker-compose up  │
        └──────────┬───────────┘
                   │
        ┌──────────┴──────────┐
        ▼                     ▼
    Tests pass          Tests FAIL
        │                     │
        │                     ▼
        │          ┌─────────────────────┐
        │          │ Investigate failure │
        │          │ Check error logs    │
        │          │ Revert & reschedule │
        │          └─────────────────────┘
        │
        ▼
    ┌──────────────────────┐
    │ Commit + push PR     │
    │ to develop           │
    └──────────┬───────────┘
               │
               ▼
    ┌──────────────────────┐
    │ Review + merge to    │
    │ develop              │
    └──────────────────────┘
```

---

## Troubleshooting

### Issue: "Failed to get digest from Docker Hub"

Solution:

```sh
# Ensure Docker is running
docker ps

# Re-authenticate if needed
docker login

# Try manual inspect
docker pull python:3.14-slim
docker inspect $(docker images -q python:3.14-slim | head -1)
```

### Issue: New image fails to build

Solution:

```sh
# Get full build output
DOCKER_BUILDKIT=0 docker build -f Dockerfile . --progress=plain

# Check for base image compatibility issues
docker run --rm python:3.14-slim python --version  # Verify Python version
docker run --rm postgres:17-alpine psql --version   # Verify PostgreSQL version
```

### Issue: postgres:17-alpine incompatible with pgvector

Solution: Alpine is fully compatible. If you see errors:

```sh
# Test pgvector build in Alpine
docker build -f infra/database/Dockerfile . -t postgres-pgvector:test
docker run --rm postgres-pgvector:test psql -U postgres -c "CREATE EXTENSION pgvector;"
```

If Alpine fails, fall back to `postgres:17-bookworm@sha256:...` (Debian-based, more tested).

---

## Calendar & Reminders

**Monthly tasks** (1st Monday of each month):
