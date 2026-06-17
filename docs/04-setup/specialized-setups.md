# Specialized Setups

Track: B — Engineering Execution

Optional setup guides for HTTPS parity, security scanning, database extensions, and ingress hardening.

---

## Local HTTPS (Edge Proxy)

Enables production parity for SameSite cookies, HSTS, and HTTPS-only integrations.

### Setup

```bash
sudo apt-get install -y mkcert libnss3-tools
mkcert -install
cd infra/certs && mkcert localhost 127.0.0.1 "*.local"
just up-https        # starts edge proxy on :443
```

Verify: `curl -vk https://127.0.0.1/api/api/v1/observations`

**Architecture:** TLS termination at the Nginx edge proxy (`:443`). The edge proxies to internal services over plain HTTP inside Docker network.

**Certificate details:** 825-day validity, auto-trusted by mkcert CA. Regenerate with `mkcert localhost 127.0.0.1 "*.local"` in `infra/certs/`.

---

## Docker Security Scanning

### BuildKit

BuildKit is enabled by default in Docker 24+. For explicit activation:

```bash
export DOCKER_BUILDKIT=1   # add to ~/.bashrc
```

### pip-audit (Python Dependencies)

```bash
uv pip install pip-audit
pre-commit install         # runs pip-audit on every commit
pre-commit run --all-files # manual run
```

### Trivy (Container Images)

```bash
sudo apt-get install -y trivy
trivy image ingestor:latest               # scan local image
trivy image --severity HIGH,CRITICAL ...  # block only on critical
```

For CI/CD: Trivy outputs SARIF format → GitHub Code Scanning dashboard.

### Pre-commit

```bash
pre-commit install
pre-commit run --all-files
```

Hooks: pip-audit, Ruff, mypy, end-of-file fixer, trailing-whitespace fixer, secrets scanner.

---

## pgvector Setup (Vector Search)

PostgreSQL 17 with pgvector extension — automatically installed via custom Docker image at `infra/database/Dockerfile`.

### Quick Start

```bash
docker compose up -d db                     # start PostgreSQL with pgvector
uv run alembic upgrade head                  # create embeddings table
```

### Architecture

Custom Dockerfile builds from `postgres:17-bookworm` and compiles `pgvector v0.7.4` from source. Init script at `docker-entrypoint-initdb.d/01-init.sql` creates the extension.

### Indexing

```sql
-- HNSW (best for high-dim, <10M vectors)
CREATE INDEX ON embeddings USING hnsw (embedding vector_cosine_ops);

-- IVFFlat (faster build, lower recall)
CREATE INDEX ON embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

---

## Ollama + Qdrant (Semantic Search for IDE)

Local AI gateway for VSCode Kilo extension semantic search.

```bash
docker compose up -d qdrant ollama
docker exec ollama ollama pull nomic-embed-text
```

MCP config in `.kilo/mcp.json` (if using Kilo): sets `OLLAMA_URL=http://127.0.0.1:11434`, `QDRANT_URL=http://127.0.0.1:6333`.

Health checks:
- `curl http://127.0.0.1:6333/health` (Qdrant)
- `curl http://127.0.0.1:11434/api/tags` (Ollama)

---

## Pre-Production Ingress Checklist

Before promoting to cloud/VPS, harden the Nginx edge proxy:

### DNS / Upstream Resolution
- Dev: static upstreams (fast, no DNS re-resolution)
- Prod: dynamic resolution with `resolver 127.0.0.11 valid=10s` via `set $upstream_ingestor http://ingestor:8000`

### SSL/TLS
- Replace mkcert with Let's Encrypt / ACM
- Enforce HTTPS redirect
- Set explicit `server_name`

### Connection Tuning
- Raise keepalive to 64/128 per upstream worker
- Adjust rate-limiting zones for production SLA thresholds

### Security Headers
```nginx
server_tokens off;
add_header X-Content-Type-Options nosniff;
add_header X-Frame-Options DENY;
add_header X-XSS-Protection "1; mode=block";
```

---

## Ansible Automation

The Ansible layer in `infra/ansible/` fills the gap between Terraform (cloud resources) and Docker Compose (containers).

### Structure

- `inventory/`: groups for `dev` (localhost), `staging` (10.0.1.10), `production` (empty)
- `vars.yml` + `vault.yml`: envars pattern, vault encrypted with `ansible-vault`
- **Roles:** `common` (apt, ulimits, sysctl), `docker` (install CE + Compose), `app` (clone repo, render .env, `uv sync`, `docker compose up -d`), `secrets` (vault bootstrap)
- **Playbooks:** `bootstrap.yml`, `provision.yml`, `drift-check.yml`, `secrets-bootstrap.yml`

### First Run

```bash
ansible-galaxy collection install -r infra/ansible/requirements.yml
ansible-vault edit infra/ansible/inventory/group_vars/all/vault.yml
ansible-playbook infra/ansible/playbooks/secrets-bootstrap.yml  # validate vault
ansible-playbook infra/ansible/playbooks/bootstrap.yml           # full provision
ansible-playbook infra/ansible/playbooks/drift-check.yml         # read-only audit
```

---

## Monthly Base Image Digest Update

**When:** 1st Monday of each month (~30 min). Picks up security patches.

```bash
# 1. Scan current digests
bash scripts/scan_base_images.sh

# 2. Find new digests
docker pull python:3.14-slim 2>&1 | grep "Digest:"
docker pull postgres:17-bookworm 2>&1 | grep "Digest:"

# 3. Update Dockerfiles: 6 Python services + infra/database/Dockerfile
# 4. Test
bash scripts/test_digest_updates.sh
# 5. Create PR with branch chore/update-base-image-digests-$(date +%Y-%m)
```

Current Python digest is pinned to `python:3.14-slim@sha256:bc389f7dfcb...`. PostgreSQL uses `postgres:17-bookworm` (no pin yet — ~1 CRITICAL + 13 HIGH vulns).

---

## References

See `docs/_archive/04-setup/references.md` for a curated list of external docs organized by pillar: FastAPI, Pydantic, PostgreSQL, SQLAlchemy, Alembic, Docker, Terraform, OpenTelemetry, OWASP, uv, and more.
