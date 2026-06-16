# Kubernetes Local Deploy Scaffolding

This directory provides Kubernetes deployment assets for the data-zoo services, targeting a **k3d** cluster for local sandbox development.

## Architecture

| Service | Port | Source code | Deployed in k3s |
|---------|------|-------------|------------------|
| **ingestor** | 8000 | `services/ingestor/` | ✅ |
| **dashboard** | 8003 | `services/dashboard/` | ✅ |
| **postgresql** | 5432 | bitnami Helm chart | ✅ (infra) |
| **redis** | 6379 | bitnami Helm chart | ✅ (infra) |
| **redpanda** | 9092 | redpanda Helm chart | ✅ (infra) |

Services without source code in this repo (analytics, inference, processor, webhook) are **not deployed** in the local k3s sandbox.

## Prerequisites

- [k3d](https://k3d.io/) (v5.x) — lightweight k3s in Docker
- [Helm](https://helm.sh/) (v3.x) — package manager for Kubernetes
- [kubectl](https://kubernetes.io/docs/tasks/tools/) — Kubernetes CLI
- [Docker](https://docs.docker.com/get-docker/) — container runtime

```bash
# macOS
brew install k3d helm kubectl

# Linux (k3d)
curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash
```

## Quick Start

One command to create the cluster, build images, deploy infrastructure, and deploy apps:

```bash
just k3s-up
```

Wait ~2 minutes for PostgreSQL, Redis, and Redpanda to initialize, then verify:

```bash
just k3s-status
```

Ingress is available at:

| Host | Port | Service |
|------|------|---------|
| `ingestor.127.0.0.1.nip.io` | 8080 | ingestor:8000 |
| `dashboard.127.0.0.1.nip.io` | 8080 | dashboard:8003 |

```bash
curl -s http://ingestor.127.0.0.1.nip.io:8080/health
curl -s http://dashboard.127.0.0.1.nip.io:8080
```

## Step-by-step

```bash
# 1. Create cluster
just k3s-cluster-create

# 2. Build images
just k3s-build

# 3. Load images into cluster
just k3s-load-images

# 4. Deploy infrastructure (PostgreSQL, Redis, Redpanda)
just k3s-deploy-infra

# 5. Apply secrets (edit secret.example.yaml first for custom values)
just k3s-secret

# 6. Deploy app services
just k3s-deploy
```

## Justfile recipes

| Recipe | Description |
|--------|-------------|
| `k3s-up` | Full lifecycle: create → build → load → deploy infra → deploy apps |
| `k3s-down` | Delete the k3d cluster |
| `k3s-cluster-create` | Create the k3d cluster |
| `k3s-cluster-delete` | Delete the k3d cluster |
| `k3s-build` | Build Docker images for ingestor + dashboard |
| `k3s-load-images` | Import images into the k3d cluster |
| `k3s-deploy-infra` | Install PostgreSQL, Redis, Redpanda via Helm |
| `k3s-secret` | Apply app secrets from template |
| `k3s-deploy` | Apply kustomize overlay + wait for rollout |
| `k3s-status` | Show pods, deployments, services, ingress |
| `k3s-logs <service>` | Tail logs for a deployment |
| `k3s-port-forward <svc> <local> <remote>` | Port-forward a service |

## Included assets

- `k3d.yaml` — k3d cluster definition (1 server, port mappings, built-in registry)
- `overlays/local/kustomization.yaml` — kustomize overlay (namespace, RBAC, ConfigMap, deployments, ingress)
- `overlays/local/secret.example.yaml` — secret template (edit before deploy)
- `overlays/local/config.yaml` — app ConfigMap (ingestor_url)
- `helm-values/postgresql.yaml` — PostgreSQL Helm values
- `helm-values/redis.yaml` — Redis Helm values
- `helm-values/redpanda.yaml` — Redpanda Helm values
- `manifests/` — base manifests for reference (deployment, service, HPA, network policies)

## Horizontal Pod Autoscaler (HPA)

The `ingestor` deployment includes an HPA (`overlays/local/ingestor-hpa.yaml`) with `minReplicas: 2`, `maxReplicas: 10`, targeting 60% CPU.

HPA requires `metrics-server`. k3d includes it by default. If missing:

```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
kubectl -n kube-system patch deployment metrics-server --type='json' \
  -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
```

## NetworkPolicy

`manifests/network-policies/` contains zero-trust NetworkPolicy manifests with a default-deny-all-ingress baseline and explicit allow rules for ingestor and dashboard.

## Tear down

```bash
just k3s-down
```

To also remove the local registry:

```bash
k3d registry delete k3d-data-zoo-registry
```
