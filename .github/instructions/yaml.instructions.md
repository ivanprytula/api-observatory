---
name: yaml-standards
description:
  'Apply to: Docker Compose, Kubernetes, Prometheus, GitHub Actions (*.yml, *.yaml). Enforces
  consistent indentation, clear schema, and best practices for infrastructure-as-code.'
applyTo: '**/*.yml, **/*.yaml, infra/**'
---

# YAML Code Standards

## Formatting & Structure

### Indentation & Syntax

- **Indentation**: 2 spaces (never tabs).
- **Quote strings**: Use double quotes for strings with special characters or ambiguous values.
- **Keys**: Lowercase with underscores for readability (e.g., `image_name`, `health_check`).
- **Comments**: Use `#` to explain non-obvious configuration.

### Example: Docker Compose

```yaml
version: '3.9'

services:
  web:
    image: 'python:3.14-slim'
    container_name: 'web_service'
    ports:
      - '8000:8000'
    environment:
      - DATABASE_URL=postgresql+asyncpg://user:password@db:5432/dbname
      - REDIS_URL=redis://cache:6379
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ['CMD', 'curl', '-f', 'http://localhost:8000/health']
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - backend
    volumes:
      - ./backend:/app
    command: 'uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload'

  db:
    image: 'postgres:16-alpine'
    container_name: 'postgres_db'
    environment:
      POSTGRES_USER: 'user'
      POSTGRES_PASSWORD: 'password'
      POSTGRES_DB: 'dbname'
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./database/init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - '5432:5432'
    healthcheck:
      test: ['CMD-SHELL', 'pg_isready -U user']
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - backend

  cache:
    image: 'redis:7-alpine'
    container_name: 'redis_cache'
    ports:
      - '6379:6379'
    networks:
      - backend

volumes:
  postgres_data:

networks:
  backend:
    driver: bridge
```

---

## Docker Compose Best Practices

### Health Checks

- Always include `healthcheck` for services that depend on each other.
- Use `depends_on` with `condition: service_healthy` for ordering.

### Environment Variables

- Define via `environment` block (not `.env` in compose).
- Use meaningful variable names (uppercase with underscores).
- Never commit secrets; use `.env.local` (gitignored) or secret management.

### Networks & Volumes

- Explicit `networks` (prefer named networks over default bridge).
- Named `volumes` for persistence, bind mounts for development.
- Use meaningful names (e.g., `postgres_data`, not `vol1`).

### Resource Limits

```yaml
services:
  web:
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: '512M'
        reservations:
          cpus: '0.5'
          memory: '256M'
```

### Hierarchical Container Naming

When managing multiple scenarios or related services, use hierarchical `container_name` patterns to
make containers easily navigable in Docker CLI and VS Code Docker extension.

**Pattern for multi-scenario projects:**

```
<project>-<scenario>-<service>
```

**Example for api-observatory:**

```yaml
services:
  db:
    container_name: dp-db
    image: postgres:15-alpine

  backend:
    container_name: dp-backend
    image: 'python:3.14-slim'

  prometheus:
    container_name: dp-prometheus
    image: prom/prometheus:v2.47.0

  k6:
    container_name: dp-k6
    image: grafana/k6:latest
```

**Benefits:**

- Easy filtering in Docker CLI: `docker ps | grep scenario-1`
- Grouped display in VS Code Docker extension (hierarchical tree view)
- Clear ownership—each container belongs to a specific scenario
- Support multiple scenarios running simultaneously without name conflicts

---

## GitHub Actions Workflows (\*.yml)

### Workflow Structure

```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready --health-interval 10s --health-timeout 5s --health-retries 5
        ports:
          - 5432:5432

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v4
        with:
          python-version: '3.14'
      - run: pip install uv && uv sync
      - run: ruff check --fix src/ && ruff format src/
      - run: ty check src/
      - run: pytest tests/ -v --cov=src
```

### Best Practices

- Use semantic version tags for actions (`@v4`, not `@main`).
- Set explicit `python-version`.
- Define services in `services` block (over separate containers).
- Use meaningful job names (`test`, `lint`, `deploy`).
 - For Python-heavy CI jobs, consider using the prebuilt CI image `ghcr.io/${{ github.repository_owner }}/data-pipeline-ci` (via `container.image`) to guarantee Python 3.14 parity and faster job startup. See `docs/ci/prebuilt-ci-image.md` for build and pinning instructions.

---

## Prometheus Configuration

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    cluster: 'architecture-patterns-lab'

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'fastapi'
    static_configs:
      - targets: ['web:8000']
    metrics_path: '/metrics'
    scrape_interval: 10s
```

---

## Common Pitfalls

- **Mixing quote styles**: Use double quotes consistently.
- **Ambiguous values**: Quote booleans and numbers that should be strings (`"true"`, `"5432"`).
- **Indentation errors**: Always 2 spaces; check with `yamllint`.
- **Missing healthchecks**: Always add health checks for dependent services.
