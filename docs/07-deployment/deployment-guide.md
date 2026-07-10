# Deployment Guide (Azure Free Tier)

## Overview

The API Observatory deploys to a single Azure B1s VM running Docker Compose. CI builds and pushes images to Azure Container Registry (ACR). CD deploys via SSH to the VM.

## Architecture

```text
GitHub Actions CI                    Azure Free Tier
┌──────────────┐                    ┌──────────────────────┐
│ lint, test,  │                    │  B1s VM (Docker)     │
│ build, scan  │──push images──►   │  ├─ ingestor:8000    │
│              │                    │  ├─ dashboard:8501   │
│  ACR push    │                    │  ├─ postgres:5432    │
└──────┬───────┘                    │  ├─ redis:6379       │
       │                            │  └─ nginx:80/443     │
       │  CD (SSH deploy)           └──────────────────────┘
       └────────────────────────────►  docker compose up -d
```

## Prerequisites

- Azure CLI installed and logged in: `az login`
- SSH key pair (generated during VM provisioning)
- GitHub repo secrets configured (see `docs/06-ci-cd/github-secrets-setup.md`)

## First-Time Setup

### 1. Provision Infrastructure

Real-cloud provisioning now lives in the sibling `api-observatory-infra` repo:

```bash
cd ../api-observatory-infra
TF_ENV=azure-dev just tf apply         # resource group, VNet, NSG, VM, PostgreSQL Flexible Server
just ansible-run provision-azure-vm    # Ubuntu 24.04 + Docker on the provisioned VM
```

See that repo's `README.md` and `ansible/playbooks/provision-azure-vm.yml` for details.

### 2. Configure GitHub Secrets

Follow the checklist in `docs/06-ci-cd/github-secrets-setup.md`:

- `ACR_LOGIN_SERVER`, `ACR_USERNAME`, `ACR_PASSWORD`
- `AZURE_CREDENTIALS`, `AZURE_VM_SSH_KEY`, `AZURE_VM_HOST_KEY`
- Create `dev` environment with approval gate

### 3. Deploy Docker Compose to VM

```bash
VM_IP=$(az vm show --resource-group api-observatory-rg --name api-observatory-vm --show-details --query publicIps -o tsv)
scp docker-compose.yml .env azureuser@${VM_IP}:~/app/
ssh azureuser@${VM_IP} "cd ~/app && docker compose up -d"
```

### 4. Verify

```bash
curl http://${VM_IP}:8000/health
curl http://${VM_IP}:8501/_stcore/health
```

## CI/CD Flow

1. Push to `develop` → CI runs (lint, test, Docker build + push to ACR, Trivy scan)
2. CI passes → CD triggers with manual approval gate
3. CD: SSH into VM → `docker login` to ACR → `docker pull` → `docker compose up -d` → health check → smoke test

## Manual Deploy

```bash
VM_IP=$(az vm show --resource-group api-observatory-rg --name api-observatory-vm --show-details --query publicIps -o tsv)
TREE_SHA=$(git rev-parse HEAD^{tree} | cut -c1-7)
ACR="${ACR_LOGIN_SERVER:-CHANGEME.azurecr.io}"

ssh azureuser@${VM_IP} bash -s <<EOF
set -euo pipefail
cd ~/app
docker pull ${ACR}/api-observatory/ingestor:tree-${TREE_SHA}
docker pull ${ACR}/api-observatory/dashboard:tree-${TREE_SHA}
docker tag ${ACR}/api-observatory/ingestor:tree-${TREE_SHA} api-observatory/ingestor:latest
docker tag ${ACR}/api-observatory/dashboard:tree-${TREE_SHA} api-observatory/dashboard:latest
docker compose down --timeout 30
docker compose up -d
docker image prune -f --filter "until=48h"
EOF
```

## Local Development (Emulator)

```bash
CLOUD=azure just sandbox-up          # start floci-az emulator + data-plane
CLOUD=azure just sandbox-dev         # hot-reload dev against emulator
CLOUD=azure just sandbox-validate    # verify emulator health
just cloud-preflight                 # verify real Azure credentials
```

## Terraform

```bash
TF_ENV=azure-sandbox just tf init    # local emulator (this repo)
TF_ENV=azure-sandbox just tf plan
TF_ENV=azure-sandbox just tf apply
```

Real Azure provisioning (`azure-dev`) lives in the `api-observatory-infra` repo — see
[Provision Infrastructure](#1-provision-infrastructure) above.

## Cost

All resources within Azure Free Tier (12-month window):

| Resource | Free Limit | Usage |
|----------|-----------|-------|
| B1s VM | 750 hrs/month | ~730 hrs (always-on) |
| ACR Standard | 1 unit/day | Image pushes on deploy |
| Blob Storage (Hot LRS) | 5 GB | Backups, archives |
| Data Transfer Out | 15 GB/month | API + dashboard traffic |

Estimated monthly cost: **$0** (within free tier limits).

## Troubleshooting

### VM not responding

```bash
az vm start --resource-group api-observatory-rg --name api-observatory-vm
```

### Docker Compose issues on VM

```bash
ssh azureuser@${VM_IP} "cd ~/app && docker compose logs --tail=50"
```

### ACR login expired on VM

```bash
ssh azureuser@${VM_IP} "az acr login --name CHANGEME"
```
