# Pillar 3: Ops & Infrastructure

Track: E — Archive and Historical Snapshots

**Tier**: Foundation (🟢) + Middle (🟡) + Senior (🔴)
**Project**: Proves production-readiness
**Building in**: `Dockerfile`, `docker-compose.yml`, `.github/workflows/`, infra manifests

---

## Foundation (🟢)

### Docker

**Multi-stage build** (builder + runtime)

- Separate layer for deps compilation (larger)
- Separate layer for runtime (smaller final image)
- Reduces final image size

```dockerfile
FROM python:3.14-slim as builder
RUN pip install uv
COPY . /app
WORKDIR /app
RUN uv venv && uv pip install -r requirements.txt

FROM python:3.14-slim
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
RUN useradd -m appuser && chown -R appuser /app
USER appuser
CMD ["uvicorn", "app.main:app"]
```

**Key config**:

- `USER appuser` = run as non-root (security)
- `.dockerignore` = exclude large files (tests, **pycache**, .git)
- Layer ordering = dependencies first (cacheable), code last (changes often)

---

### Git

**Conventional commits**: `feat:`, `fix:`, `chore:`, `docs:`

- Enables semantic versioning + auto-changelog
- Example: `feat: add cursor pagination to list endpoint`

---

### Linux

**Essential tools for debugging**:

- `ps`, `top`, `htop` = process inspection
- `grep`, `awk` = text parsing logs
- `jq` = JSON parsing

---

## Middle Tier (🟡)

### CI/CD — GitHub Actions

**Workflow structure**:

```yaml
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run tests
        run: uv run pytest tests/ --cov=app
```

**Key patterns**:

- Matrix: `matrix: { python-version: ['3.12', '3.13'] }`
- Caching: cache `uv` venv between runs
- Secrets: `secrets.OPENAI_API_KEY` (set in GitHub)

---

### Cloud Basics (AWS/GCP)

**For api-observatory**: Deploy to **Google Cloud Run** (simplest):

```bash
gcloud run deploy api-observatory \
  --source . \
  --platform managed \
  --region us-central1 \
  --set-env-vars DATABASE_URL=postgresql+asyncpg://...
```

**For AWS**: ECR (image registry) + ECS Fargate (container runtime) + RDS (PostgreSQL)

---

## Senior (🔴)

### Kubernetes

**Minimal production deployment**:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-observatory-app
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: app
        image: gcr.io/project/api-observatory:latest
        resources:
          requests: {cpu: 100m, memory: 128Mi}
          limits: {cpu: 500m, memory: 512Mi}
        livenessProbe:
          httpGet: {path: /health, port: 8000}
          initialDelaySeconds: 15
        readinessProbe:
          httpGet: {path: /readyz, port: 8000}
          initialDelaySeconds: 5
```

**Key concepts**:

- Resource requests = guaranteed; limits = cap
- Probes = signal when pod is alive/ready
- Rolling updates = `maxSurge: 1, maxUnavailable: 0`

---

### Terraform

Provision one resource (e.g., Cloud Run service):

```hcl
resource "google_cloud_run_service" "app" {
  name     = "api-observatory"
  location = "us-central1"

  template {
    spec {
      containers {
        image = "gcr.io/project/api-observatory:latest"
        env {
          name  = "DATABASE_URL"
          value = var.database_url
        }
      }
    }
  }
}
```

---

## You Should Be Able To

✅ Write Dockerfile with multi-stage builds, non-root user, proper caching
✅ Use `docker compose` for local dev (app + postgres + cache)
✅ Debug container issues: `docker logs`, `docker exec`
✅ Create GitHub Actions workflow for lint → test → build
✅ Deploy containerized FastAPI to Cloud Run or ECS
✅ Understand Kubernetes Deployment + Service + Ingress
✅ Provision infrastructure with Terraform
✅ Explain why you'd use rolling updates vs blue-green

---

## References

- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- [GitHub Actions](https://docs.github.com/en/actions)
- [Google Cloud Run](https://cloud.google.com/run/docs)
- [Kubernetes Docs](https://kubernetes.io/docs/)
- [Terraform AWS/GCP Providers](https://www.terraform.io/language/providers)

---

## Checklist — Pillar 3: Ops & Infrastructure

### Foundation 🟢

- [ ] Write a multi-stage Docker build that separates dependencies from source
  - [ ] Know that copying `pyproject.toml` before source enables layer caching
- [ ] Use `docker compose up --build`, `down`, `down -v`, `exec`, `logs -f`
- [ ] Write conventional commits: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`
- [ ] Know basic Linux tools: `ps aux`, `lsof -i :8000`, `df -h`, `du -sh`

### Middle 🟡

- [ ] Write a GitHub Actions workflow with `jobs`, `steps`, `needs:`, `env:`, `secrets:`
  - [ ] Know how `needs:` creates sequential job dependencies
  - [ ] Know `secrets.GITHUB_TOKEN` is auto-injected
- [ ] Use `docker compose profiles` to start selective service subsets
- [ ] Optimize Docker image size: `--no-cache`, `.dockerignore`, `COPY --chown`
- [ ] Set up pre-commit hooks: `ruff`, `trailing-whitespace`, `end-of-file-fixer`
  - [ ] Know that `pre-commit install` installs git hooks, not just the tool

### Senior 🔴

- [ ] Write Terraform: `resource`, `variable`, `output`, `module`, `data`
  - [ ] Explain `terraform plan` vs `apply` vs `destroy`
  - [ ] Know that state drift happens when infra changes outside Terraform
- [ ] Explain blue/green vs canary deployment strategies with trade-offs
- [ ] Configure RBAC for GitHub Actions with `permissions:` key
- [ ] Know the difference between Docker secrets and environment variables for sensitive data

### Pre-Interview Refresh ✏️

- [ ] Why does multi-stage Docker build reduce image size?
- [ ] Explain `COPY pyproject.toml ./` before `COPY . .` — why this order?
- [ ] What does `docker compose profiles` solve that plain `depends_on` does not?
- [ ] What does `needs:` accomplish in a GitHub Actions job?
- [ ] Blue/green vs canary — which has faster rollback and why?
