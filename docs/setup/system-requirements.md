# System Requirements & Package Installation

Track: B — Engineering Execution

This document lists Ubuntu/Debian system packages and CLI tools required for setup, daily development,
database operations, chaos testing, and Floci integration.

---

## Scope

- Install commands: Ubuntu/Debian (`apt-get`). Use `brew` on macOS or WSL2 on Windows for equivalent installs.
- All tools listed work cross-platform; only the install method differs.
- Shell: bash or zsh
- Minimum baseline: Ubuntu 22.04 LTS or newer
- Automated check command: `just doctor`

---

## Quick Install (Ubuntu/Debian)

```bash
sudo apt-get update
sudo apt-get install -y \
  postgresql-client redis-tools mongodb-tools \
  util-linux iproute2 \
  docker-ce docker-ce-cli containerd.io docker-compose-plugin \
  libgdal-dev gdal-bin python3-gdal \
  graphviz \
  curl jq git

# Docker CE GPG key + apt repo must be configured first — see docs/01-system-setup.md#ubuntu-debian-install
```

Install uv:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
```

Install Floci wrappers and project dependencies:

```bash
uv tool install awscli-local  # Floci CLI wrapper
uv sync                                        # Project Python dependencies
```

---

## Required Packages by Category

### Core Development

| Package | Apt package | Purpose |
| ------- | ----------- | ------- |
| Docker | `docker-ce docker-ce-cli containerd.io` | Container runtime for all services |
| Docker Compose | `docker-compose-plugin` | Multi-service orchestration (v2 plugin) |
| Python 3.14+ | `python3.14 python3.14-dev python3.14-venv` | Runtime and tooling |
| uv | install script | Python package manager and runner |
| Git | `git` | Source control |
| curl | `curl` | HTTP checks and Floci health probing |
| jq | `jq` | JSON parsing from CLI output |
| mkcert (optional) | `mkcert libnss3-tools` | Local HTTPS certificates |

### Data/Infra Operations

| Package | Apt package | Purpose | Used by |
| ------- | ----------- | ------- | ------- |
| PostgreSQL client tools | `postgresql-client` | `pg_dump`, `pg_restore`, `psql` | `infra/scripts/backup.sh`, `infra/scripts/restore.sh` |
| MongoDB tools | `mongodb-tools` | `mongodump`, `mongorestore` | `infra/scripts/backup.sh`, `infra/scripts/restore.sh` |
| Cache tools | `redis-tools` | `redis-cli` for cache inspection | daily ops |
| GDAL | `libgdal-dev gdal-bin python3-gdal` | Geospatial support in portal service | portal runtime/dev |

### Chaos Testing

| Package | Apt package | Purpose | Used by |
| ------- | ----------- | ------- | ------- |
| util-linux | `util-linux` | `nsenter` for network namespace access | `infra/scripts/chaos.sh` |
| iproute2 | `iproute2` | `tc` traffic control for latency/loss | `infra/scripts/chaos.sh` |

### Floci Integration

| Tool | Install method | Purpose |
| ---- | -------------- | ------- |
| AWS CLI v2 | direct installer | Base AWS CLI commands |
| Terraform | HashiCorp apt repo | IaC execution |
| boto3 | `uv sync` | Python AWS SDK for integration tests |

---

## Ubuntu/Debian Installation Steps (Detailed)

### 1. Install system packages

```bash
# Configure Docker CE apt repo first (one-time)
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y \
  python3.14 python3.14-dev python3.14-venv \
  postgresql-client redis-tools mongodb-tools \
  docker-ce docker-ce-cli containerd.io docker-compose-plugin \
  util-linux iproute2 \
  libgdal-dev gdal-bin python3-gdal \
  curl jq git
```

### 2. Install AWS CLI v2

```bash
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip
unzip -o awscliv2.zip
sudo ./aws/install
```

### 3. Install Terraform

```bash
wget -O- https://apt.releases.hashicorp.com/gpg | gpg --dearmor | sudo tee /usr/share/keyrings/hashicorp-archive-keyring.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt-get update
sudo apt-get install -y terraform
```

### 4. Install uv and project dependencies

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
uv sync
```

### 5. Install Floci wrapper

```bash
uv tool install awscli-local
```

### 6. Allow Docker without sudo

See [01 — System Setup](../01-system-setup.md#enable-docker-without-sudo) for Docker group configuration.

---

## Verification Checklist

```bash
docker --version
docker compose version
python3.14 --version
uv --version
aws --version
terraform version

pg_dump --version
redis-cli --version
mongodump --version
nsenter --version
tc --version
gdal-config --version

python3 -c "import boto3; print(boto3.__version__)"
```

Optional automated check:

```bash
bash scripts/setup/03-verify-system-requirements.sh
# or
just doctor
```

## Local Debug Artifacts

Use `.local-dev/` for verbose local outputs and raw dumps during troubleshooting.
The folder is gitignored and can be created/recreated by `just doctor`.

---

## Script-by-Script Package Requirements

### `infra/scripts/backup.sh`

```bash
# Required
pg_dump
gzip

# Optional
mongodump
```

### `infra/scripts/restore.sh`

```bash
# Required
pg_restore
psql
gzip / zcat

# Optional
mongorestore
```

### `infra/scripts/chaos.sh`

```bash
# Required
docker
nsenter
tc
```

---

## Floci-Specific Commands

```bash
just floci-up
aws s3 ls
aws sqs list-queues
TF_ENV=sandbox just tf plan
```

If wrapper is missing:

```bash
uv tool install awscli-local
```

---

## Troubleshooting

### Docker permission denied

```bash
sudo usermod -aG docker "$USER"
newgrp docker
docker ps
```

### `pg_dump: command not found`

```bash
sudo apt-get install -y postgresql-client
```

### `mongodump: command not found`

```bash
sudo apt-get install -y mongodb-tools
```

### `tc: command not found`

```bash
sudo apt-get install -y iproute2
```

---

## CI/CD Note

GitHub Actions Ubuntu runners already include Docker and common build tools. CI still relies on
project-level dependency installation (`uv sync`) and workflow-specific service setup.

---

## Next Steps

1. Install packages and tools from the Ubuntu/Debian steps above.
2. Verify with the checklist.
3. Start services: `just up`
4. Start Floci profile: `just floci-up`
5. Continue with [Floci + AWS deployment workflow](../floci-aws-deployment-workflow.md).

See [environment setup](environment-setup.md) for `.env` strategy.
