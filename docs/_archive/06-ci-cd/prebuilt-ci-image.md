# Prebuilt CI Image — data-pipeline-ci

Track: B — Engineering Execution


This repository uses a prebuilt CI image to ensure a consistent, reproducible Python environment across all CI jobs and to speed up runs by pre-installing `uv`, wheel caches, and common build tools.

Image: `ghcr.io/${{ github.repository_owner }}/data-pipeline-ci`

Why use it

- Consistency: guarantees Python 3.14 interpreter and matching ABI for cp314 wheels.
- Speed: dependency resolution and wheel builds occur once at image build time instead of every job.
- Determinism: reduced flakiness from differing runner environments or missing system packages.
- Security: build the image in a controlled workflow and pin workflows to image digests for immutability.

Build & publish (local)

## Build locally and load into Docker (single-arch)

docker buildx build -f infra/ci/ci-base-image/Dockerfile \
  -t ghcr.io/${OWNER}/data-pipeline-ci:sha-$(git rev-parse --short HEAD) \
  --load .

## Push to GHCR (requires GHCR auth)

docker push ghcr.io/${OWNER}/data-pipeline-ci:sha-$(git rev-parse --short HEAD)

## Get the image digest (recommended for pinning)

docker pull ghcr.io/${OWNER}/data-pipeline-ci:sha-$(git rev-parse --short HEAD)
docker inspect --format='{{index .RepoDigests 0}}' ghcr.io/${OWNER}/data-pipeline-ci:sha-$(git rev-parse --short HEAD)

## Quick test (run a subset of prechecks inside the image)

docker run --rm -v "$PWD":/work -w /work ghcr.io/${OWNER}/data-pipeline-ci:sha-<short_sha> \
  sh -c "uv run ruff check . && uv run ty check"

## How to pin an image in workflows

Replace `container.image: ghcr.io/${{ github.repository_owner }}/data-pipeline-ci:latest` with a digest-based pin for immutability:

```yaml
container:
  image: ghcr.io/${{ github.repository_owner }}/data-pipeline-ci@sha256:<digest>
```

This ensures the workflow uses the exact image you validated and can be rolled back by switching the digest to a previous known-good value.

Rollback options

- Update the workflow to reference the previous image digest and commit the change.
- Re-tag a previous image as `latest` in GHCR (less preferred because tags are mutable).
- Keep a small registry of approved digests and their human-friendly names in an Approved CI Images list (optional).

Where the image is built in this repository

-- See workflow: [.github/workflows/ci.yml](../../.github/workflows/ci.yml)

Notes & best practices

- Test images locally before pushing and pin the digest in critical branches (main, release).
- Keep the image build workflow automated and gated (e.g., only push `latest` on successful CI runs).
- Use the container only for CI jobs that require the Python runtime; ephemeral workflows that need different runners can still use hosted runners.
