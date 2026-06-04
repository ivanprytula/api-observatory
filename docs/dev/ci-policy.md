# CI Policy: What Blocks PR vs Release

Last reviewed: 2025-07 | Owner: ingestor team

## What blocks a pull request (merge gate)

All of these must be green before merge to `develop` or `main`:

| Check | Workflow job | Blocks merge |
|---|---|---|
| Lint (ruff check + format) | `ci.yml / lint` | yes |
| Action ref validation | `ci.yml / action-ref-validation` | yes |
| Unit tests | `ci.yml / unit-tests` | yes |
| Python dep audit (pip-audit) | `ci.yml / python-deps` | yes |
| Docker build | `ci.yml / docker-build` | yes |
| Docker scan HIGH+CRITICAL (Trivy) | `ci.yml / docker-scan-security` | yes |
| CodeQL SAST | `ci.yml / codeql` | yes |
| Integration tests (Postgres + Redis) | `ci.yml / integration-tests` | yes |
| Secrets scan on changed lines | `security-secrets-lite.yml` | yes |
| Docker scan MEDIUM advisory (Trivy) | `ci.yml / docker-scan-advisory` | **no** (reported only) |

Branch protection requires: `CI gate (all checks passed)` + `Secrets Scan (changed lines)`.

## What blocks a release (`v*` tag on `main`)

All of these must pass before the release image is considered trusted:

| Check | Workflow job | Blocks release |
|---|---|---|
| Tag is on `origin/main` | `release.yml / verify-ci` | yes |
| CI passed on tagged commit | `release.yml / verify-ci` | yes |
| Image build + push to GHCR | `release.yml / build-and-push` | yes |
| Cosign image signing | `release.yml / sign-and-attest` | yes |
| Provenance attestation verified | `release.yml / sign-and-attest` | yes |
| SBOM generated and uploaded | `release.yml / sbom` | yes |

## What never blocks (advisory / scheduled)

- `docker-scan-advisory`: MEDIUM+ Trivy findings — reported in summary, exit 0.
- `security.yml`: daily full audit (pip-audit, CodeQL, Trivy) — scheduled, not a merge gate.
- `dependabot-age-guard.yml`: PyPI release age check — advisory comment + label, does not close PR.

## Promotion policy

Image is built **once** in `ci.yml` tagged `tree-${TREE_SHA}`. `release.yml` pulls that same candidate — no rebuild. `cd-prod.yml` deploys by immutable digest. No environment causes a rebuild.

## Local CI lane repro

```bash
just test-unit                          # unit lane
just test-integration                   # integration lane (Docker auto-provisions Postgres)
uv run ruff check services libs         # lint
uv run ruff format --check services libs
just deploy-audit                       # docker build + Trivy scan
```
