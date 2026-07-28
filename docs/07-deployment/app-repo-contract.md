# App Repository — Infrastructure Contract Checklist

## Primary Deployment Target

AWS is the primary portfolio deployment direction. Stage 0 runs Docker Compose on
EC2 with RDS PostgreSQL and private ECR images; ECS/Fargate remains a Stage 2
option after a demonstrated service-extraction need. Azure assets remain secondary
reference material and are not removed by this decision.

The machine-readable Stage-0 service contract is
[`infra/deployment/aws-stage0-services.json`](../../infra/deployment/aws-stage0-services.json).
It defines the three deployable HTTP services: `ingestor`, `inference`, and
`dashboard`. `mcp` is deliberately excluded because it is a locally spawned
stdio process, not an HTTP deployment.

### Environment Ownership

- **App repository:** environment-variable names, safe defaults, Dockerfiles, ports,
  and health/readiness behavior.
- **Infra repository:** ECR repositories, EC2/Compose runtime values, RDS endpoints,
  IAM, and secret delivery. No value belongs in either repository's workflow files.

## Container Image Contract

Each service image must satisfy these requirements for the infra manifests to function correctly.

### User & Filesystem

- [ ] **Container runs as UID 10001** (not 1001, not root) — matches `runAsUser: 10001` in manifests
- [ ] **UID 10001 has write access** to `/tmp` — the infra mounts `emptyDir` there for services with `readOnlyRootFilesystem: true`
- [ ] **No hardcoded UID assumptions** in app code — do not look up users by name; use `os.getuid()` or equivalent
- [ ] **`/etc/passwd` entry for UID 10001** (e.g. `nobody:x:10001:10001:nobody:/:/sbin/nologin`) — prevents `whoami` and certain library failures

### Health & Probes

- [ ] **`GET /health` returns 200** on port 8000 (ingestor) and 8001 (inference)
- [ ] **Dashboard responds on port 8501** — Streamlit does not expose the same FastAPI probe contract
- [ ] **`services/mcp` is stdio-only in v1, deliberately** — the MCP server (Phase 5 of
      `docs/.plans/ai-augmented-observatory-agent-mcp.md`) is a locally-run CLI process an MCP
      client (e.g. Claude Desktop) spawns directly; it has no HTTP surface, no port, no
      docker-compose entry, no `/health`/`/readyz`. Port **8006** is reserved as the next-free
      slot for if/when a `streamable-http` mode is added (a config flip, not a rewrite — see
      `services/mcp/main.py`) — not a missing row here by oversight.
- [ ] **`GET /readyz` returns 200** when the service is ready to receive traffic (distinct from /health — checks dependencies like DB, broker)
- [ ] **Startup probe grace period** matches the current infra manifest for each deployed service

### Security

- [ ] **Application reads secrets from environment variables** — delivery may use EC2/Compose or a
      Kubernetes `secretKeyRef`, but application code does not assume the delivery mechanism.
      Inference uses pgvector and owns its database configuration separately from ingestor as
      recorded in [ADR 015](../02-architecture/adr/015-inference-dedicated-pgvector-postgres.md);
      Qdrant is not part of the current runtime.
- [ ] **No secrets in logs** — log scrubbing for env var values is the app's responsibility
- [ ] **No `root` required** — app must work with `runAsNonRoot: true`, `readOnlyRootFilesystem: true`, `allowPrivilegeEscalation: false`, and `capabilities.drop: [ALL]`
- [ ] **No privileged ports** (<1024) — apps bind to ephemeral/high ports only

#### Secret Source by Runtime

- **Local dev**: `infra/kubernetes/overlays/local/secret.example.yaml` is a static, plaintext,
  dummy-value `Secret` — never used outside `k3d` local sandboxes.
- **AWS Stage 0:** the infra repo supplies values to the EC2 Compose runtime. This remains a
  deployment decision/configuration claim until a live run is separately approved and verified.
  A later ECS/Kubernetes stage should use AWS Secrets Manager with task-role or external-secret
  delivery. The app continues to read environment variables and must not assume a delivery mechanism.
- Either mechanism is infra-repo-owned. The app repo's obligation stays exactly what it is today:
  read secrets from environment variables and never assume a specific delivery mechanism. The app
  repo declares names and behavior; the infra repo owns delivery.

### Observability

- [ ] **OpenTelemetry-compatible** — services that emit traces expect `OTEL_EXPORTER_OTLP_ENDPOINT` env var (set via config map)
- [ ] **Prometheus `/metrics` endpoint** on a separate port or same port — if exposed, infra should know the scrape port

## CI/CD Image Tagging Contract

- [ ] **Candidates use full-tree tags and deployed digests** — manual CD creates `tree-<full-tree-SHA>` candidates only after exact-commit CI verification, while Stage 0 Compose receives `repository@sha256:...` references only.
- [ ] **`latest` is never pushed** to production registries — `latest` is used only for local `k3d import`
- [ ] **Image pull policy is `Always`** in production — guaranteed fresh pods on rollout
- [ ] **Primary registry is ECR** — `${AWS_ECR_REGISTRY}/api-observatory/{ingestor,inference,dashboard}`; CD resolves each approved candidate to an immutable digest.
  Azure ACR remains a secondary/reference target only.

### Stage 0 Rollout Contract

[`docker-compose.aws-stage0.yml`](../../docker-compose.aws-stage0.yml) is the AWS-only delivery
file. It starts only the three HTTP services from required `repository@sha256:...` image
references. Runtime values remain infra-owned; in particular, `DATABASE_URL` stays the ingestor
database while `INFERENCE_DATABASE_URL` is mapped only to inference.

For each approved image set, CD records the currently running image references, pulls the new
digests, then runs these forward-only migration commands before replacing containers:

```text
docker compose run --rm --no-deps ingestor alembic upgrade head
docker compose run --rm --no-deps inference alembic upgrade head
```

It then waits for `/readyz` on ingestor and inference and the dashboard health endpoint, runs an
API smoke check, and records redacted evidence. If migration, rollout, readiness, or smoke fails,
CD restarts the captured image references. Database schema rollback is intentionally excluded;
migrations must preserve expand/contract compatibility with the previous application images.

## Communication Contract

- [ ] **Services discover each other via DNS** — Kubernetes service names (e.g. `http://ingestor:8000`), not external URLs
- [ ] **Ingestor is the public API entry point** and dashboard is the public UI; no standalone webhook gateway exists
- [ ] **Broker (Redpanda/Kafka) and database URLs** are injected at deploy time — never hardcoded

## Deviations from Ideal (Known Gaps)

| Check | Rule | Reason Skipped | Fix Owner |
|-------|------|---------------|-----------|
| CKV_K8S_35 | Secrets as files, not env vars | App reads from `os.environ`; requires sidecar/rewrite | App repo |
| CKV_K8S_14 | Fixed image tag (`:latest` in dev) | Local dev workflow uses `k3d import latest` | — |
| CKV_K8S_43 | Image digest pinning | Same root cause as CKV_K8S_14; prod CI uses `tree-<SHA>` | — |
| CKV_K8S_21 | `default` namespace | config.yaml + secret.example.yaml resolved by kustomize | — |
