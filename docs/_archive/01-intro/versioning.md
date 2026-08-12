# Versioning: Contracts and Service Provenance

This project uses a strict, simple versioning scheme to avoid confusing
fallbacks during development and in CI/CD.

Contracts version (canonical)

- Source: `libs/contracts/VERSION` (required)
- This file MUST exist and contain the SemVer for the contracts (e.g. `0.1.3`).

Service version (provenance)
Only two sources are allowed (in order of precedence):

1. `SERVICE_VERSION` environment variable (recommended for CI / production)
   - CI should set this during build/deploy. Example (GitHub Actions):

```bash
echo "SERVICE_VERSION=$(git describe --tags --always --dirty --abbrev=7)" >> $GITHUB_ENV
```

1. `VERSION` file at the repository root (convenient for local development)
   - Create a text file named `VERSION` containing the SemVer string (e.g. `1.2.3+gdeadbee`).

Behavior

- The code will fail fast if neither source is present, making misconfiguration
  obvious during CI or local runs.
- Use SemVer for `SERVICE_VERSION` where possible; append a short git SHA
  (`+g<short-sha>`) for quick `git bisect` provenance when debugging.

Why this approach

- Minimal options reduce confusion for developers and CI systems.
- CI-driven `SERVICE_VERSION` scales well to multi-repo/multi-team setups.
