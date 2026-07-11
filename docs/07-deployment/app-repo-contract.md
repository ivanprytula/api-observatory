# App Repository — Infrastructure Contract Checklist

## Container Image Contract

Each service image must satisfy these requirements for the infra manifests to function correctly.

### User & Filesystem

- [ ] **Container runs as UID 10001** (not 1001, not root) — matches `runAsUser: 10001` in manifests
- [ ] **UID 10001 has write access** to `/tmp` — the infra mounts `emptyDir` there for services with `readOnlyRootFilesystem: true`
- [ ] **No hardcoded UID assumptions** in app code — do not look up users by name; use `os.getuid()` or equivalent
- [ ] **`/etc/passwd` entry for UID 10001** (e.g. `nobody:x:10001:10001:nobody:/:/sbin/nologin`) — prevents `whoami` and certain library failures

### Health & Probes

- [ ] **`GET /health` returns 200** on port 8000 (ingestor), 8001 (inference), 8002 (processor), 8003 (dashboard), 8004 (webhook), 8005 (analytics)
- [ ] **`GET /readyz` returns 200** when the service is ready to receive traffic (distinct from /health — checks dependencies like DB, broker)
- [ ] **Startup probe grace period** honoured: inference/failureThreshold: 30, webhook/processor/failureThreshold: 18, others: 6

### Security

- [ ] **Application reads secrets from environment variables** — infra injects `DATABASE_URL`, `INTERNAL_JWT_SECRET`, `BROKER_URL`, `ADMIN_TOKEN` via `secretKeyRef` (not files). The `inference` service (real as of the AI-augmented observatory Phase 2) uses pgvector on the shared `DATABASE_URL` Postgres instance — no separate `QDRANT_URL`/Qdrant deployment; see `docs/.plans/ai-augmented-observatory-agent-mcp.md` for why.
- [ ] **No secrets in logs** — log scrubbing for env var values is the app's responsibility
- [ ] **No `root` required** — app must work with `runAsNonRoot: true`, `readOnlyRootFilesystem: true`, `allowPrivilegeEscalation: false`, and `capabilities.drop: [ALL]`
- [ ] **No privileged ports** (<1024) — apps bind to ephemeral/high ports only

#### Secret Source in Production

- **Local dev**: `infra/kubernetes/overlays/local/secret.example.yaml` is a static, plaintext,
  dummy-value `Secret` — never used outside `k3d` local sandboxes.
- **Production**: the infra repo replaces the static `Secret` with one synced from Azure Key Vault,
  via either the **Azure Key Vault Provider for Secrets Store CSI Driver** (mounts secrets as files
  and can sync them into a native `Secret` via `secretObjects`) or **External Secrets Operator**
  with an Azure Key Vault `SecretStore`/`ClusterSecretStore` (reconciles Key Vault entries into a
  native `Secret` on a poll interval). Both land the same native `Secret` object that
  `secretKeyRef` already consumes.
- Either mechanism is infra-repo-owned. The app repo's obligation stays exactly what it is today:
  read secrets from environment variables via `secretKeyRef`, never assume a specific delivery
  mechanism. This mirrors the UID 10001 boundary above — the app repo declares the *contract*
  (env var names, `secretKeyRef` usage), the infra repo owns the *delivery mechanism*.

### Observability

- [ ] **OpenTelemetry-compatible** — services that emit traces expect `OTEL_EXPORTER_OTLP_ENDPOINT` env var (set via config map)
- [ ] **Prometheus `/metrics` endpoint** on a separate port or same port — if exposed, infra should know the scrape port

## CI/CD Image Tagging Contract

- [ ] **Tags follow `tree-<SHA>` format** — CI in the app repo builds and pushes images tagged with the short commit SHA prefixed by `tree-`
- [ ] **`latest` is never pushed** to production registries — `latest` is used only for local `k3d import`
- [ ] **Image pull policy is `Always`** in production — guaranteed fresh pods on rollout
- [ ] **Container registry matches target cloud** — `acr.azure.io/*` for Azure, `*.dkr.ecr.*.amazonaws.com/*` for AWS

## Communication Contract

- [ ] **Services discover each other via DNS** — Kubernetes service names (e.g. `http://ingestor:8000`), not external URLs
- [ ] **Ingestor is the public entry point** for external webhook data; dashboard is the public UI; webhook is an internal gateway
- [ ] **Broker (Redpanda/Kafka) and database URLs** are injected at deploy time — never hardcoded

## Deviations from Ideal (Known Gaps)

| Check | Rule | Reason Skipped | Fix Owner |
|-------|------|---------------|-----------|
| CKV_K8S_35 | Secrets as files, not env vars | App reads from `os.environ`; requires sidecar/rewrite | App repo |
| CKV_K8S_14 | Fixed image tag (`:latest` in dev) | Local dev workflow uses `k3d import latest` | — |
| CKV_K8S_43 | Image digest pinning | Same root cause as CKV_K8S_14; prod CI uses `tree-<SHA>` | — |
| CKV_K8S_21 | `default` namespace | config.yaml + secret.example.yaml resolved by kustomize | — |
