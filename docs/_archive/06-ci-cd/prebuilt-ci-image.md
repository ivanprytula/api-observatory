# Retired Prebuilt CI Image

This document records a retired approach. The repository formerly built
`infra/ci/ci-base-image/Dockerfile` and published a GHCR CI image to pre-install
Python tooling and dependencies.

The active workflows now run on GitHub-hosted runners, install the pinned `uv`
toolchain, and use `uv.lock` with `uv sync --frozen`. The image had no active
workflow consumer and still referenced removed service manifests, so it was
deleted in the CI/CD cleanup commit. Do not restore it unless measured runner
setup time justifies owning a separate image build, publishing, scanning, and
digest-rotation lifecycle.
