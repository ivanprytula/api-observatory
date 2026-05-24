# Phase 3 — Docker + CI/CD Pipeline

**Duration**: 2 weeks
**Goal**: Multi-stage Docker build, GitHub Actions CI/CD (lint → test → build → push to ECR)
**Success Metric**: CI pipeline <5 min, Docker image <150MB, 100% test pass rate on PR

---

## Core Learning Objective

Master containerization and GitOps: multi-stage builds (layer caching), secret management, GitHub Actions workflows, artifact registry integration.

---

## Interview Questions

### Core Q: "Design CI/CD Pipeline for Multi-Service Application"

**Expected Answer:**

- Trigger: Push to main → linting → unit tests → integration tests → docker build → push to registry
- Parallel jobs where possible (lint + unit test run concurrently)
- Docker multi-stage: compile/dependencies in builder stage, copy artifacts to runtime stage (keep image slim)
- Registry: ECR (AWS) or Docker Hub. ECR integrates with ECS/Fargate for deployment.
- Secrets: GitHub Secrets for registry credentials, never hardcoded
- Caching: Docker layer caching (dependencies layer separate from code)
- Status checks: PR requires pipeline pass before merge

**Talking Points:**

- Multi-stage builds: 1000MB builder → 50MB runtime (slim base image, no build tools in final)
- Layer caching: If requirements.txt unchanged, skip `pip install`, use cached layer
- Parallel matrix: Run tests on Python 3.10, 3.11, 3.12 simultaneously (matrix job)
- Failure fast: Lint fails → skip tests (save time). If lint passes, run tests.

---

### Follow-Up: "Docker Image 500MB. How Reduce to <150MB?"

**Expected Answer:**

- Use slim base image: `python:3.12-slim` (80MB) vs `python:3.12` (900MB)
- Multi-stage: Compile in builder, copy only runtime deps to final
- Remove build artifacts: `apt-get autoremove`, `pip cache purge`
- Layer ordering: Expensive deps first (reuse if code-only change)
- Distroless base (for production): `gcr.io/distroless/python3.12` (20MB, no shell, security)

**Talking Points:**

- Image layers: Each RUN statement = one layer. Minimize layers, consolidate RUN commands.
- `.dockerignore`: Exclude `.git`, `__pycache__`, `tests` from COPY to reduce context size.
- BuildKit: Enable experimental `docker buildx` for better caching and parallel builds.

---

### Follow-Up: "CI Job Fails on Merge. Rollback or Forward-Fix?"

**Expected Answer:**

- **Immediate**: Revert PR (git revert) if failure is prod-impacting (data corruption, auth broken)
- **Otherwise**: Fix forward (git commit) if failure is minor (test flake, formatting)
- **Prevent**: Pre-commit hooks (lint locally) + branch protection (require PR checks pass)
- **Post-incident**: Update CI to catch error (add test case, add lint rule)

**Talking Points:**

- Pre-commit hooks: Run linting/formatting before commit (faster feedback)
- GitHub branch protection: Require PR review + CI pass before merge (enforces quality)
- Flaky tests: Auto-retry 3× in CI (different from local, may pass on retry due to timing)
- Deployment gates: Stage deploy (dev → staging → prod) with manual approval per stage

---

## Real life production example — Production-Ready

### Architecture

```text
Push to main
  ↓
GitHub Actions (ci.yml) triggers
  ├─► Job: Lint (Ruff check + format check)
  │   └─► Pass/Fail → Status check
  │
  ├─► Job: Unit Tests (pytest, parallel on matrix)
  │   └─► Python 3.10, 3.11, 3.12 concurrent
  │
  ├─► Job: Docker Build (multi-stage)
  │   ├─► Builder: pip install all deps
  │   ├─► Runtime: copy only .wheels, source code
  │   └─► Tag: {REGISTRY}/app:{COMMIT_SHA}
  │
  └─► Job: Push to ECR
      └─► AWS ECR credentials (from GitHub Secrets)
          ├─► Push {REGISTRY}/app:{COMMIT_SHA}
          └─► Also tag as :latest
```

### Implementation Checklist

- [ ] **Dockerfile (multi-stage)**

**Tip:** For Python-heavy CI, prefer using the prebuilt CI image `ghcr.io/${{ github.repository_owner }}/data-pipeline-ci` to ensure interpreter parity and faster runs. See [docs/ci/prebuilt-ci-image.md](docs/ci/prebuilt-ci-image.md) for build/pin/rollback steps.

  ```dockerfile
  FROM python:3.12-slim as builder

  WORKDIR /app
  COPY requirements.txt .
  RUN pip install --user --no-cache-dir -r requirements.txt
  # User site-packages goes to /root/.local

  FROM python:3.12-slim

  COPY --from=builder /root/.local /root/.local
  COPY app/ /app/app
  COPY app/main.py /app/main.py
  ENV PATH=/root/.local/bin:$PATH

  EXPOSE 8000
  CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
  ```

- [ ] **.dockerignore**

  ```text
  .git
  __pycache__
  tests/
  docs/
  .pytest_cache
  .ruff_cache
  htmlcov/
  ```

- [ ] **.github/workflows/ci.yml**

  ```yaml
  name: CI

  on:
    push:
      branches: [main, develop]
    pull_request:
      branches: [main]

  jobs:
    lint:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-python@v4
          with:
            python-version: '3.12'
            cache: 'pip'
        - run: pip install ruff
        - run: ruff check app tests
        - run: ruff format --check app tests

    test:
      runs-on: ubuntu-latest
      strategy:
        matrix:
          python-version: ['3.10', '3.11', '3.12']
      services:
        postgres:
          image: postgres:17
          env:
            POSTGRES_PASSWORD: password
          options: >-
            --health-cmd pg_isready
            --health-interval 10s
            --health-timeout 5s
            --health-retries 5
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-python@v4
          with:
            python-version: ${{ matrix.python-version }}
            cache: 'pip'
        - run: pip install -e .[test]
        - run: pytest tests/ -v --cov=app

    docker-build:
      runs-on: ubuntu-latest
      needs: [lint, test]
      steps:
        - uses: actions/checkout@v4
        - uses: docker/setup-buildx-action@v3
        - uses: docker/build-push-action@v5
          with:
            context: .
            push: false
            tags: app:${{ github.sha }}
            cache-from: type=gha
            cache-to: type=gha,mode=max

    push-ecr:
      runs-on: ubuntu-latest
      if: github.ref == 'refs/heads/main'


  Tip: For maintainers, consider running the `lint` and `test` jobs inside the prebuilt CI image instead of using `actions/setup-python` on each job. Example:

```yaml
lint:
  container:
    image: ghcr.io/${{ github.repository_owner }}/data-pipeline-ci:latest
  steps:
    - uses: actions/checkout@<sha>
    - run: uv run ruff check .
```

This reduces per-job setup time and guarantees Python 3.14 parity for cp314 wheels.

```yaml
      needs: docker-build
      steps:
        - uses: actions/checkout@v4
        - uses: aws-actions/configure-aws-credentials@v2
          with:
            aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
            aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
            aws-region: eu-central-1
        - uses: docker/setup-buildx-action@v3
        - uses: aws-actions/amazon-ecr-login@v1
          id: login-ecr
        - uses: docker/build-push-action@v5
          with:
            context: .
            push: true
            tags: |
              ${{ steps.login-ecr.outputs.registry }}/app:${{ github.sha }}
              ${{ steps.login-ecr.outputs.registry }}/app:latest
            cache-from: type=gha
            cache-to: type=gha,mode=max
```

- [ ] **GitHub Secrets (set in repo settings)**
  - `AWS_ACCESS_KEY_ID`
  - `AWS_SECRET_ACCESS_KEY`
  (Use IAM user with ECR push permission only, not root credentials)

- [ ] **pyproject.toml** (test extras)

  ```toml
  [project.optional-dependencies]
  test = [
      "pytest>=7.0",
      "pytest-asyncio>=0.21",
      "pytest-cov>=4.0",
      "httpx>=0.24",
  ]
  ```

- [ ] **docker-compose.yml** (development)

  ```yaml
  services:
    web:
      build: .
      ports: ["8000:8000"]
      environment:
        DATABASE_URL: postgresql+asyncpg://postgres:password@db:5432/app
      depends_on:
        - db

    db:
      image: postgres:17
      environment:
        POSTGRES_PASSWORD: password
  ```

---

## Weekly Checklist

### Week 1: Docker + Lint/Test CI

- [ ] Dockerfile: multi-stage, slim base, <150MB final image
- [ ] .dockerignore: exclude unnecessary files
- [ ] ci.yml: lint job (Ruff check + format)
- [ ] ci.yml: test job with matrix (Python 3.10/3.11/3.12)
- [ ] Local test: `docker build -t app .` → verify <150MB
- [ ] CI run: First push to main → verify pipeline passes
- [ ] Interview Q: "Design CI/CD for multi-service?" → Answer drafted
- [ ] Commits: 6–8 (Dockerfile, ci.yml setup, lint job, test job)

### Week 2: ECR Push + Performance Tuning

- [ ] ci.yml: docker-build job (caching via BuildKit)
- [ ] ci.yml: push-ecr job (AWS credentials, only on main)
- [ ] BuildKit caching: Verify layer cache reuse (should skip `pip install` on code-only change)
- [ ] Performance: Re-run CI, measure time (target <5 min total)
- [ ] GitHub branch protection: Require CI pass before merge
- [ ] AWS ECR: Verify image pushed and tagged correctly
- [ ] Interview Q: "Reduce 500MB image to 150MB?" → Full answer ready
- [ ] Commits: 5–7 (ECR setup, caching tuning, branch protection docs)
- [ ] Portfolio item + LinkedIn post

---

## Success Metrics

| Metric          | Target  | How to Measure                                                    |
| --------------- | ------- | ----------------------------------------------------------------- |
| CI time         | <5 min  | GitHub Actions run time (lint + test + build + push)              |
| Image size      | <150MB  | `docker images` output, app:latest size column                    |
| Layer cache hit | 80%+    | Second CI run on code-only change should skip `pip install` layer |
| Test pass       | 100%    | All matrix jobs (3.10/3.11/3.12) pass                             |
| Image push      | Success | ECR dashboard shows image with correct tags                       |
| Lint pass       | 100%    | No Ruff warnings on every push                                    |
| Commit count    | 11–15   | 1 per feature + docs                                              |

---

## Gotchas + Fixes

### Gotcha 1: "Docker Layer Cache Not Working"

**Symptom**: Second CI run still takes 2min on `pip install` (should be <5s cached).
**Cause**: Docker BuildKit caching not enabled, or cache-from/cache-to missing in workflow.
**Fix**: Add to workflow: `with: cache-from: type=gha, cache-to: type=gha,mode=max`.

### Gotcha 2: "ECR Push Fails: Unauthorized"

**Symptom**: AWS credentials invalid or IAM policy missing.
**Cause**: GitHub Secrets not set, or IAM user lacks `ecr:PutImage` permission.
**Fix**: Create IAM user with inline policy: `{ "Action": ["ecr:*"], "Resource": "arn:aws:ecr:*:*:repository/app" }`.

### Gotcha 3: "Matrix Tests Fail Intermittently"

**Symptom**: Python 3.11 test fails randomly, 3.10 passes (flaky, not deterministic).
**Cause**: Test has timing dependency (asyncio.sleep without mocking) or port conflict.
**Fix**: Mock time in tests, use pytest-asyncio event_loop fixture. Or add retry: `- run: pytest --tb=short -v` (pytest-repeat plugin).

### Gotcha 4: "Base Image Security Update Breaks Build"

**Symptom**: `python:3.12-slim` updated to new patch, build suddenly fails (apt package removed).
**Cause**: Pinning base image without version (uses floating tag, pulls new patch).
**Fix**: Pin: `FROM python:3.12.1-slim` (specific patch). Rotate pin quarterly.

---

## Cleanup (End of Phase 3)

```bash
# ECR cleanup (old untagged images)
aws ecr describe-images --repository-name app --query 'imageDetails[?length(imageTags)==`0`].imageId' | \
  jq '.[] | "--image-ids imageTag={imageTag}\n"' | \
  xargs -I {} aws ecr batch-delete-image --repository-name app {}
```

---

## Metrics to Monitor Ongoing

- CI pipeline duration: Alert if > 6 min (slowdown indicates CI regression)
- Docker build cache hit rate: Monitor via GitHub Actions logs
- Test flakiness: Alert if >1% flaky (requires investigation)
- Image security scans: ECR image scanning for CVEs (enable in ECR repo settings)

---

## Next Phase

**Phase 4: AI + Vector Database**
Use Phase 2 scraped data → generate embeddings → store in Qdrant. Implement semantic search endpoint. Use Phase 3 CI/CD to deploy.

**Reference**: Phase 3 CI/CD stable = ready for Phase 4. If CI takes >10 min, optimize before Phase 4.
