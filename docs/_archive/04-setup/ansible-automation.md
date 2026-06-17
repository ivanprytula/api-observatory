# Ansible Automation

This document describes the Ansible layer in `infra/ansible/` — what it does, how it is
structured, and how to run each playbook.

## Why Ansible

The project already has Terraform for cloud infrastructure and Docker Compose for runtime
orchestration. Ansible fills the gap between those two layers:

- Terraform provisions raw VMs and cloud resources but does not configure the OS or deploy
  the application.
- Docker Compose starts containers but assumes the host is already prepared.
- Ansible handles everything in between: system hardening, Docker installation, application
  deployment, `.env` generation from the Vault, and ongoing drift detection.

Using Ansible keeps host configuration in version control, idempotent, and auditable.

## Directory structure

```text
infra/ansible/
├── ansible.cfg                        # Ansible settings (inventory path, SSH, fact cache)
├── requirements.yml                   # Galaxy collections to install before first run
├── inventory/
│   ├── hosts.yml                      # Static inventory: dev, staging, production groups
│   └── group_vars/
│       └── all/
│           ├── vars.yml               # Non-sensitive variables shared across all hosts
│           └── vault.yml              # Encrypted secrets (must be encrypted before committing)
├── playbooks/
│   ├── bootstrap.yml                  # Full environment bootstrap — runs all four roles
│   ├── provision.yml                  # VM-only provisioning — common + docker roles only
│   ├── drift-check.yml                # Read-only configuration drift audit
│   └── secrets-bootstrap.yml          # Validates vault secrets before any deployment
└── roles/
    ├── common/                        # System packages, ulimits, sysctl, deploy user
    ├── docker/                        # Docker Engine + Compose plugin installation
    ├── app/                           # Application deployment: repo, .env, migrations, Compose
    └── secrets/                       # Vault variable validation (no plaintext secrets on disk)
```

## Inventory and variables

### Inventory groups

`inventory/hosts.yml` defines three groups:

| Group | Purpose | Default target |
| --- | --- | --- |
| `dev` | Local machine, `ansible_connection: local` | `localhost` |
| `staging` | Remote staging VM | `10.0.1.10` |
| `production` | Remote production VMs | _(empty, add before going live)_ |

Limit to a group with `--limit dev` or `--limit staging` on every `ansible-playbook` call.

### Variable separation (vars + vault pattern)

`inventory/group_vars/all/vars.yml` holds all non-sensitive variables. Every sensitive value
uses a Jinja2 reference to a `vault_` counterpart:

```yaml
# vars.yml — safe to commit
compose_env:
  database_url: "postgresql+asyncpg://postgres:{{ vault_db_password }}@127.0.0.1:5432/data_pipeline"
  jwt_secret: "{{ vault_jwt_secret }}"
```

```yaml
# vault.yml — MUST be encrypted with ansible-vault
vault_db_password: 'your-real-password'
vault_jwt_secret: 'your-real-secret-at-least-32-chars'
```

Secrets available in `vault.yml`:

| Variable | Used for |
| --- | --- |
| `vault_db_password` | PostgreSQL password in `DATABASE_URL` |
| `vault_jwt_secret` | JWT signing key (must be ≥ 32 characters) |
| `vault_api_v1_bearer_token` | `API_V1_BEARER_TOKEN` in `.env` |
| `vault_docs_password` | HTTP Basic Auth on `/docs` |
| `vault_openai_api_key` | `OPENAI_API_KEY` in `.env` |

## Roles

### `common` — system baseline

Runs first on every host. Tasks:

1. Updates the apt cache and installs required system packages (`curl`, `git`, `python3-pip`,
   `jq`, `htop`, and others).
2. Creates the `deploy` application user and adds them to the `docker` group.
3. Writes `/etc/security/limits.d/99-app.conf` to raise `nofile` limits to 65 536, which
   PostgreSQL and high-concurrency FastAPI services require.
4. Writes `/etc/sysctl.d/99-app.conf` with:
   - `vm.overcommit_memory = 1` — required for Cache to avoid OOM kills.
   - `net.core.somaxconn = 1024` — raises the TCP connection backlog.

### `docker` — Docker Engine

Installs the official Docker Engine from `download.docker.com`. Tasks:

1. Adds the Docker GPG key and apt repository.
2. Installs `docker-ce`, `docker-ce-cli`, `containerd.io`, `docker-buildx-plugin`, and
   `docker-compose-plugin`.
3. Adds configured users (default: `deploy`) to the `docker` group.
4. Ensures the `docker` systemd service is enabled and started.

### `app` — application deployment

Deploys and starts the application. Tasks in order:

1. Creates `{{ app_dir }}` (default: `/opt/api-observatory`) with correct ownership.
2. Clones or updates the git repository to `{{ app_version }}` (default: `main`).
3. Renders `{{ app_dir }}/.env` from `roles/app/templates/env.j2` using variables from
   `vars.yml` and decrypted `vault.yml` values. The file is written with mode `0640` so it
   is not world-readable.
4. Installs `uv` if not already present.
5. Runs `uv sync --frozen` to install pinned Python dependencies from `uv.lock`.
6. Pulls all Docker Compose images defined in `{{ docker_compose_file }}`
   (default: `docker-compose.prod-like.yml`).
7. Runs `alembic upgrade head` to apply any pending schema migrations.
8. Starts all Compose services with `docker compose up -d`.

A handler restarts Compose when the repository or `.env` changes.

### `secrets` — vault validation

A guard role that runs assertions before any deployment. It does **not** write plaintext
secrets anywhere. Tasks:

1. Asserts `vault_db_password` is defined and not `CHANGEME`.
2. Asserts `vault_jwt_secret` is defined, not `CHANGEME`, and is at least 32 characters.
3. Asserts `vault_api_v1_bearer_token` and `vault_docs_password` are replaced.
4. Checks the rendered `{{ app_dir }}/.env` on the target host for any remaining `CHANGEME`
   strings and fails if any are found.

## Playbooks

### Playbook invocation

All playbooks follow the same pattern:

```bash
ansible-playbook infra/ansible/playbooks/<name>.yml --ask-vault-pass --limit <env>
```

Available playbooks:

| Playbook | Purpose |
| --- | --- |
| `bootstrap.yml` | Full environment bootstrap (common → docker → secrets → app) |
| `provision.yml` | VM-only provisioning (common + docker roles) |
| `drift-check.yml` | Read-only configuration drift audit |
| `secrets-bootstrap.yml` | Validates vault secrets before any deployment |

These playbooks each document their specific purpose and behavior in the sections that follow.

## Quick-start: first run on a new host

Install Galaxy collections (`ansible-galaxy collection install -r infra/ansible/requirements.yml`), then edit `vault.yml` and replace `CHANGEME` values. The recommended playbook sequence: `secrets-bootstrap.yml` → `bootstrap.yml` → `drift-check.yml`, each invoked with `--ask-vault-pass --limit <env>`. See `scripts/` for automated orchestration.

## Vault workflow

```bash
# Edit an encrypted vault file interactively (encrypt/decrypt are rarely needed)
ansible-vault edit infra/ansible/inventory/group_vars/all/vault.yml
```

> **Note**: `vault.yml` must be encrypted before every `git commit`. The `.gitignore` does
> not exclude it because the encrypted file must be version-controlled.

## Relationship to other infrastructure tools

| Tool | Responsibility |
| --- | --- |
| Terraform (`infra/terraform/`) | Cloud resource provisioning (VMs, networking, DNS) |
| Ansible (`infra/ansible/`) | OS configuration, Docker install, application deployment |
| Docker Compose | Container runtime, service wiring, resource limits |
| GitHub Actions | CI pipeline, image builds, automated tests |

Terraform outputs (VM IPs, SSH keys) feed into the Ansible inventory. Ansible prepares the
host and starts Compose. GitHub Actions pushes images to a registry that Ansible pulls
during deployment.

## Ansible with a cloud Kubernetes deployment

When the application moves to a managed Kubernetes cluster (EKS, GKE, AKS, or similar),
Docker Compose is no longer the runtime. The `app` role is replaced by Ansible tasks that
drive `kubectl` and Helm. Everything else — secrets validation, OS-level node preparation,
and drift checks — stays the same.

### What Ansible still owns on Kubernetes

| Concern | Ansible task | Alternative |
| --- | --- | --- |
| Kubeconfig provisioning | Write a per-environment kubeconfig from vault | `aws eks update-kubeconfig` in CI |
| Namespace and RBAC bootstrap | Create namespaces, `ServiceAccount`, `Role`, `RoleBinding` once | Terraform Kubernetes provider |
| External secret injection | Create `Secret` objects from vault variables before Helm deploy | External Secrets Operator |
| Helm chart deploy / upgrade | `community.kubernetes.helm` module with idempotent `--atomic` | ArgoCD / Flux |
| Post-deploy smoke check | `kubectl rollout status`, health probe assertion | Kubernetes readiness probes |
| Node pool configuration | Install node-level daemons (log agents, security scanners) | Daemonset + cloud init |
| Alembic migrations | Run as a Kubernetes `Job` via `kubectl apply` | Init container in the Deployment |

The project already has manifests in `infra/kubernetes/` and Helm charts in
`infra/kubernetes/charts/`. Ansible orchestrates the sequence: inject secrets → apply
namespaces/RBAC → run migrations Job → upgrade Helm releases → verify rollout.

### New inventory structure for Kubernetes

Add a `k8s` group alongside the existing VM groups. The `ansible_connection: local` variant
is correct here because Ansible talks to the cluster through the Kubernetes API, not SSH.

```yaml
# inventory/hosts.yml
all:
  children:
    dev:
      hosts:
        localhost:
          ansible_connection: local

    k8s_staging:
      hosts:
        k8s-staging:
          ansible_connection: local
          kubeconfig_context: 'staging-cluster'
          k8s_namespace: 'data-pipeline-staging'

    k8s_production:
      hosts:
        k8s-prod:
          ansible_connection: local
          kubeconfig_context: 'prod-cluster'
          k8s_namespace: 'data-pipeline-production'
```

Add matching `group_vars/k8s_staging/vars.yml` and `group_vars/k8s_production/vars.yml`
with cluster-specific values (image tag, replica counts, resource limits).

### New `k8s_app` role

Create `roles/k8s_app/` to replace the `app` role for Kubernetes targets. Suggested task
sequence:

```yaml
# roles/k8s_app/tasks/main.yml (outline)

- name: 'Write kubeconfig from vault'
  # Writes vault_kubeconfig to ~/.kube/config-{{ kubeconfig_context }}
  # Sets KUBECONFIG env var for subsequent tasks

- name: 'Create application namespace'
  kubernetes.core.k8s:
    api_version: v1
    kind: Namespace
    name: '{{ k8s_namespace }}'
    state: present

- name: 'Apply RBAC manifests'
  kubernetes.core.k8s:
    src: '{{ playbook_dir }}/../../kubernetes/manifests/role.yaml'
    namespace: '{{ k8s_namespace }}'
    state: present

- name: 'Inject application secrets'
  kubernetes.core.k8s:
    definition:
      apiVersion: v1
      kind: Secret
      metadata:
        name: app-secrets
        namespace: '{{ k8s_namespace }}'
      type: Opaque
      stringData:
        DATABASE_URL: '{{ compose_env.database_url }}'
        JWT_SECRET: '{{ vault_jwt_secret }}'
        API_V1_BEARER_TOKEN: '{{ vault_api_v1_bearer_token }}'
    state: present

- name: 'Run Alembic migration Job'
  kubernetes.core.k8s:
    definition: '{{ lookup("template", "migration-job.yaml.j2") }}'
    state: present
    wait: true
    wait_condition:
      type: Complete
      status: 'True'
    wait_timeout: 120

- name: 'Deploy ingestor via Helm'
  kubernetes.core.helm:
    chart_ref: '{{ playbook_dir }}/../../kubernetes/charts/ingestor'
    release_name: ingestor
    release_namespace: '{{ k8s_namespace }}'
    atomic: true
    wait: true
    values:
      image:
        tag: '{{ app_version }}'
      replicaCount: '{{ k8s_replica_count | default(2) }}'

- name: 'Verify rollout is healthy'
  ansible.builtin.command:
    argv:
      - kubectl
      - rollout
      - status
      - deployment/ingestor
      - --namespace={{ k8s_namespace }}
      - --timeout=120s
  changed_when: false
```

### New `playbooks/k8s-deploy.yml`

```yaml
---
# Cloud Kubernetes deployment playbook.
#
# Usage:
#   ansible-playbook playbooks/k8s-deploy.yml \
#     -i inventory/hosts.yml \
#     --ask-vault-pass \
#     --limit k8s_staging \
#     -e app_version=sha-abc1234

- name: 'Deploy api-observatory to Kubernetes'
  hosts: all
  gather_facts: false

  roles:
    - role: 'secrets'      # validate vault variables first
    - role: 'k8s_app'      # namespace, RBAC, secrets, migrations, Helm deploy
```

### Required Galaxy collections for Kubernetes

Add these to `requirements.yml`:

```yaml
collections:
  - name: 'kubernetes.core'
    version: '>=3.0.0'
```

Install with `ansible-galaxy collection install -r infra/ansible/requirements.yml`.

### Drift check on Kubernetes

The existing `drift-check.yml` is VM-oriented. For Kubernetes, add a separate
`playbooks/k8s-drift-check.yml` that asserts cluster state:

```yaml
- name: 'Kubernetes drift check'
  hosts: all
  gather_facts: false

  tasks:
    - name: 'Assert ingestor Deployment is available'
      kubernetes.core.k8s_info:
        api_version: apps/v1
        kind: Deployment
        name: ingestor
        namespace: '{{ k8s_namespace }}'
      register: _deploy_info

    - name: 'Assert desired replicas are ready'
      ansible.builtin.assert:
        fail_msg: 'ingestor deployment is not fully available.'
        that:
          - '_deploy_info.resources | length > 0'
          - '_deploy_info.resources[0].status.availableReplicas == _deploy_info.resources[0].spec.replicas'

    - name: 'Assert app-secrets Secret exists'
      kubernetes.core.k8s_info:
        api_version: v1
        kind: Secret
        name: app-secrets
        namespace: '{{ k8s_namespace }}'
      register: _secret_info

    - name: 'Assert secret is present'
      ansible.builtin.assert:
        fail_msg: 'app-secrets Secret is missing from {{ k8s_namespace }}.'
        that:
          - '_secret_info.resources | length > 0'
```

### Kubernetes deployment tool map

| Tool | Responsibility |
| --- | --- |
| Terraform | Cluster provisioning, node pools, cloud IAM, DNS |
| Ansible | Secrets injection, namespace/RBAC bootstrap, Helm deploy, post-deploy verify |
| Helm (`infra/kubernetes/charts/`) | Kubernetes manifest templating and versioned releases |
| kubectl / kustomize | Low-level manifest apply, local overlay (`overlays/local/`) |
| GitHub Actions | Image build, push to registry, trigger Ansible deploy playbook |
| Kubernetes (HPA) | Runtime autoscaling based on CPU/memory metrics |

Ansible sits between Terraform and the running cluster: Terraform hands off a kubeconfig,
Ansible bootstraps namespaces and secrets once, then upgrades Helm releases on every
deployment. For fully GitOps-style workflows (where ArgoCD or Flux watches the repository),
Ansible can be limited to the one-time bootstrap steps only — secrets injection, RBAC, and
initial namespace creation — while Argo/Flux handle ongoing reconciliation.
