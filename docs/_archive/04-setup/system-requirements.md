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

# Docker CE GPG key + apt repo must be configured first — see system-setup.md#ubuntu-debian-install
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

See also: `scripts/setup/03-verify-system-requirements.sh`

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


## Floci-Specific Commands

```bash
just floci-up
TF_ENV=sandbox just tf plan
```

---

## Troubleshooting

### Docker permission denied

```bash
sudo usermod -aG docker "$USER"
newgrp docker
```

### Missing client tools

Install the missing apt package: `postgresql-client`, `mongodb-tools`, or `iproute2`.

---

## CI/CD Note

GitHub Actions Ubuntu runners already include Docker and common build tools. CI still relies on
project-level dependency installation (`uv sync`) and workflow-specific service setup.

---

## Next Steps

1. Run the verification script: `bash scripts/setup/03-verify-system-requirements.sh`
2. Verify with the checklist (or `just doctor`).
3. Start services: `just up`
4. Start Floci profile: `just floci-up`
5. Continue with Floci + AWS deployment workflow.

See [environment setup](environment-setup.md) for `.env` strategy.
