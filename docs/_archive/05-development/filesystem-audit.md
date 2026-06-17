# Container Filesystem Audit — Phase 13.1

Track: B — Engineering Execution


Audit of writable filesystem paths per service to support `readOnlyRootFilesystem: true` hardening.

## Methodology

For each service, run the writable-path enumeration:

```bash
docker compose run --rm <svc> \
  find / -writable -not -path "*/proc/*" -not -path "*/sys/*" 2>/dev/null
```

## Findings

| Service | Writable paths | Resolution |
|---------|---------------|------------|
| `ingestor` | `/tmp`, `/app/logs` (if file logging enabled) | `emptyDir` at `/tmp`; log file output disabled (STDOUT only) |
| `inference` | `/tmp`, `/root/.cache/huggingface` (sentence-transformers model cache) | `emptyDir` at `/tmp`; `emptyDir{medium: Memory}` at model cache |
| `processor` | `/tmp` | `emptyDir` at `/tmp` |
| `dashboard` | `/tmp`, Jinja2 bytecode cache (`.pyc` in `/app`) | `emptyDir` at `/tmp`; Python `PYTHONDONTWRITEBYTECODE=1` env var |
| `analytics` | `/tmp` | `emptyDir` at `/tmp` |
| `webhook` | `/tmp` | `emptyDir` at `/tmp` |

## Actions Taken

- Added `emptyDir` volume mounts for all identified writable paths per service.
- Set `securityContext.readOnlyRootFilesystem: true` in all K8s deployment manifests.
- Corresponding ECS task definitions have `readonlyRootFilesystem: true` (Terraform).
- `inference` model cache uses `medium: Memory` to avoid disk contention; size limited to
  `2Gi` to cap memory usage.

## Verification

```bash
# readOnlyRootFilesystem enforced
for svc in ingestor inference processor dashboard analytics webhook; do
  kubectl -n data-zoo exec deploy/$svc -- touch /app/test 2>&1 | grep -q "Read-only" \
    && echo "$svc: HARDENED" || echo "$svc: FAIL"
done

# emptyDir /tmp still writable
for svc in ingestor inference processor dashboard analytics webhook; do
  kubectl -n data-zoo exec deploy/$svc -- touch /tmp/test \
    && echo "$svc /tmp: OK" || echo "$svc /tmp: FAIL"
done
```
