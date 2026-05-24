# Phase 8 — Infrastructure as Code (Terraform)

**Duration**: 2 weeks
**Goal**: Terraform multi-environment deployment (dev/staging/prod), state management, secrets rotation
**Success Metric**: `terraform plan` < 30s, zero manual AWS changes, all environments idempotent

---

## Core Learning Objective

Master infrastructure-as-code: Terraform modules, state locking, multi-environment patterns, secrets management, and GitOps deployment.

---

## Interview Questions

### Core Q: "Design Infrastructure as Code for Multi-Service App (Dev, Staging, Prod)"

**Expected Answer:**

- Terraform modules: `networking`, `rds`, `ecs`, `elb`, `secrets` (reusable across environments)
- Workspaces: `terraform workspace select prod` → separate tfstate per env
- State backend: Remote (S3 + DynamoDB lock) not local (prevent accidental commits)
- Secrets: AWS Secrets Manager (rotatable, audit trail) not hardcoded or .env files
- Approval gates: Manual approval in GitHub Actions for prod apply
- State lock: DynamoDB table prevents concurrent applies (corrupted state on collision)
- Drift detection: `terraform plan` in CI detects manual AWS console changes (enforce IaC-only)

**Talking Points:**

- Workspace vs separate code: Workspaces (same code, different state) simpler for similar envs. Separate code if envs drastically different (e.g., dev vs on-premises).
- State file as truth: Whoever controls tfstate controls infrastructure. Guard it (S3 encryption, DynamoDB lock).
- Modules = components: Each module is independently testable, versioned, reusable.

---

### Follow-Up: "Terraform State Locked for 2 Hours (Stuck Apply). Recovery?"

**Expected Answer:**

- Symptom: `terraform apply` hangs or fails with "state lock" error
- Diagnosis: `aws dynamodb query --table-name terraform-lock --key-condition-expression 'LockID = :id'`
- Root cause: Previous apply crashed, process killed, or manual interrupt without cleanup
- Recovery: `terraform force-unlock <LOCK_ID>` (only use if certain previous operation failed)
- Prevention: Set lock timeout (`dynamodb_table` + `skip_credentials_validation=false`)
- Post-recovery: Check logs, verify infrastructure state, re-run apply

**Talking Points:**

- Lock timeout: Default ~10min. If longer, previous operation still running (patience) vs stuck (unlock).
- Workspace lock: Each workspace has separate tfstate + lock (concurrent workspaces OK)
- Distributed teams: State lock enforces serialization—only one apply at a time per workspace

---

### Follow-Up: "Rollback Failed Deploy (Bad RDS Migration). Procedure?"

**Expected Answer:**

- Option 1: `terraform destroy` old infrastructure, redeploy (safest for immutable infrastructure)
- Option 2: `terraform state rm` + manual AWS cleanup (dangerous, state mismatch risk)
- Option 3: Git revert + `terraform apply` (cleanest if IaC changes caused issue)
- Procedure: (1) Identify bad change (git log → commit X), (2) `git revert X`, (3) `terraform plan` to verify, (4) `terraform apply` with approval, (5) Verify health checks pass
- Data strategy: RDS snapshots before major changes (restore if data corruption)

**Talking Points:**

- Immutable infrastructure: Built new resources instead of modifying. Old replaced atomically → fast rollback.
- Blue/green deployment: Keep old stack alive while new deploys, switch traffic instantly → zero downtime rollback.
- Database migrations: Decouple from app deployment (run migration separately before/after code deploy).

---

## Real life production example — Production-Ready

### Architecture

```text
Code repo (main branch)
  ↓
GitHub Actions: terraform plan
  ├─► Lint (terraform fmt, tflint)
  ├─► Validate (terraform validate)
  └─► Plan (terraform plan -out=tfplan) → comment on PR

Manual approval (required for prod)
  ↓
GitHub Actions: terraform apply
  ├─► Lock state (DynamoDB)
  ├─► Apply (terraform apply tfplan)
  ├─► Query outputs (RDS endpoint, Fargate service URL)
  └─► Unlock state

Instances
  ├─► VPC (networking module)
  ├─► RDS PostgreSQL 17
  ├─► Fargate cluster + ECS service
  ├─► ElastiCache (Redis)
  ├─► Secrets Manager (JWT key, API keys)
  └─► CloudWatch (logs, metrics)
```

### Implementation Checklist

- [ ] **Terraform Project Structure**

  ```text
  infra/
  ├── main.tf (provider, state backend)
  ├── variables.tf (input vars)
  ├── outputs.tf (RDS endpoint, service URL)
  ├── terraform.tfvars (local defaults)
  ├── dev.tfvars (dev env)
  ├── staging.tfvars (staging env)
  ├── prod.tfvars (prod env)
  └── modules/
      ├── networking/
      │   ├── main.tf (VPC, subnets, security groups)
      │   ├── variables.tf
      │   └── outputs.tf
      ├── rds/
      │   ├── main.tf (PostgreSQL 17)
      │   ├── variables.tf
      │   └── outputs.tf
      ├── ecs/
      │   ├── main.tf (Fargate cluster, service, task definition)
      │   ├── variables.tf
      │   └── outputs.tf
      ├── alb/
      │   ├── main.tf (Application Load Balancer)
      │   ├── variables.tf
      │   └── outputs.tf
      └── secrets/
          ├── main.tf (Secrets Manager + rotation)
          ├── variables.tf
          └── outputs.tf
  ```

- [ ] **Backend Configuration (S3 + DynamoDB)**

  ```hcl
  # infra/main.tf
  terraform {
    backend "s3" {
      bucket         = "data-pipeline-tfstate"
      key            = "terraform.tfstate"
      region         = "eu-central-1"
      dynamodb_table = "terraform-lock"
      encrypt        = true
    }
  }

  provider "aws" {
    region = var.aws_region

    default_tags {
      tags = {
        Environment = var.environment
        ManagedBy   = "Terraform"
        Project     = "DataZoo"
      }
    }
  }
  ```

- [ ] **Module: Networking**

  ```hcl
  # infra/modules/networking/main.tf
  resource "aws_vpc" "main" {
    cidr_block           = var.vpc_cidr
    enable_dns_hostnames = true
    enable_dns_support   = true

    tags = { Name = "${var.environment}-vpc" }
  }

  resource "aws_subnet" "private" {
    count             = length(var.availability_zones)
    vpc_id            = aws_vpc.main.id
    cidr_block        = var.private_subnet_cidrs[count.index]
    availability_zone = var.availability_zones[count.index]

    tags = { Name = "${var.environment}-private-${count.index + 1}" }
  }

  resource "aws_security_group" "app" {
    vpc_id = aws_vpc.main.id

    ingress {
      from_port   = 8000
      to_port     = 8000
      protocol    = "tcp"
      cidr_blocks = [aws_vpc.main.cidr_block]
    }

    egress {
      from_port   = 0
      to_port     = 0
      protocol    = "-1"
      cidr_blocks = ["0.0.0.0/0"]
    }
  }
  ```

- [ ] **Module: RDS (PostgreSQL 17)**

  ```hcl
  # infra/modules/rds/main.tf
  resource "aws_db_instance" "postgres" {
    identifier            = "${var.environment}-postgres"
    allocated_storage    = var.db_storage
    storage_type         = "gp3"
    engine               = "postgres"
    engine_version       = "17"
    instance_class       = var.db_instance_class
    username             = "postgres"
    password             = random_password.db_password.result

    db_subnet_group_name   = aws_db_subnet_group.main.name
    vpc_security_group_ids = [aws_security_group.rds.id]

    multi_az               = var.multi_az
    storage_encrypted      = true
    backup_retention_period = var.backup_retention_days
    skip_final_snapshot     = var.environment == "dev"

    tags = { Name = "${var.environment}-postgres" }
  }

  resource "random_password" "db_password" {
    length  = 32
    special = true
  }

  resource "aws_secretsmanager_secret" "db_password" {
    name = "${var.environment}/rds/password"
  }

  resource "aws_secretsmanager_secret_version" "db_password" {
    secret_id      = aws_secretsmanager_secret.db_password.id
    secret_string  = random_password.db_password.result
  }
  ```

- [ ] **Module: ECS Fargate**

  ```hcl
  # infra/modules/ecs/main.tf
  resource "aws_ecs_cluster" "main" {
    name = "${var.environment}-cluster"

    setting {
      name  = "containerInsights"
      value = "enabled"
    }
  }

  resource "aws_ecs_task_definition" "app" {
    family                   = "${var.environment}-app"
    network_mode             = "awsvpc"
    requires_compatibilities = ["FARGATE"]
    cpu                      = var.task_cpu
    memory                   = var.task_memory
    execution_role_arn       = aws_iam_role.ecs_task_exec.arn
    task_role_arn            = aws_iam_role.ecs_task.arn

    container_definitions = jsonencode([{
      name      = "app"
      image     = var.image_uri
      essential = true
      portMappings = [{
        containerPort = 8000
        hostPort      = 8000
        protocol      = "tcp"
      }]
      environment = [
        { name = "DATABASE_URL", value = var.database_url },
        { name = "LOG_LEVEL", value = var.log_level }
      ]
    }])
  }

  resource "aws_ecs_service" "app" {
    name            = "${var.environment}-app-service"
    cluster         = aws_ecs_cluster.main.id
    task_definition = aws_ecs_task_definition.app.arn
    desired_count   = var.desired_count
    launch_type     = "FARGATE"

    network_configuration {
      subnets          = var.private_subnet_ids
      security_groups  = [aws_security_group.app.id]
      assign_public_ip = false
    }

    load_balancer {
      target_group_arn = var.alb_target_group_arn
      container_name   = "app"
      container_port   = 8000
    }
  }
  ```

- [ ] **Variables per Environment**

  ```hcl
  # infra/dev.tfvars
  environment           = "dev"
  aws_region            = "eu-central-1"
  vpc_cidr              = "10.0.0.0/16"
  db_instance_class     = "db.t3.micro"
  db_storage            = 20
  multi_az              = false
  task_cpu              = 256
  task_memory           = 512
  desired_count         = 1

  # infra/prod.tfvars
  environment           = "prod"
  aws_region            = "eu-central-1"
  vpc_cidr              = "10.0.0.0/16"
  db_instance_class     = "db.r5.xlarge"  # More resources
  db_storage            = 500
  multi_az              = true             # High availability
  task_cpu              = 2048
  task_memory           = 4096
  desired_count         = 3
  ```

- [ ] **.github/workflows/terraform.yml**

  ```yaml
  name: Terraform Deploy

  on:
    push:
      branches: [main]
      paths: [infra/**, .github/workflows/terraform.yml]
    workflow_dispatch:  # Manual trigger

  env:
    TF_VERSION: 1.6.0
    AWS_REGION: eu-central-1

  jobs:
    plan:
      runs-on: ubuntu-latest
      outputs:
        plan_exit_code: ${{ steps.plan.outputs.exit_code }}
      steps:
        - uses: actions/checkout@v4

        - uses: hashicorp/setup-terraform@v2
          with:
            terraform_version: ${{ env.TF_VERSION }}

        - uses: aws-actions/configure-aws-credentials@v2
          with:
            aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
            aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
            aws-region: ${{ env.AWS_REGION }}

        - name: Terraform Format Check
          run: terraform -chdir=infra fmt -check

        - name: Terraform Validate
          run: terraform -chdir=infra validate

        - name: Terraform Plan
          id: plan
          run: |
            terraform -chdir=infra plan \
              -var-file=prod.tfvars \
              -out=tfplan \
              -exit-code

        - name: Comment PR
          if: github.event_name == 'pull_request'
          uses: actions/github-script@v6
          with:
            script: |
              github.rest.issues.createComment({
                issue_number: context.issue.number,
                owner: context.repo.owner,
                repo: context.repo.repo,
                body: '✅ Terraform plan successful. Manual approval required for apply.'
              })

    apply:
      runs-on: ubuntu-latest
      needs: plan
      if: github.ref == 'refs/heads/main'
      environment:
        name: production
        # Requires manual approval in GitHub
      steps:
        - uses: actions/checkout@v4

        - uses: hashicorp/setup-terraform@v2
          with:
            terraform_version: ${{ env.TF_VERSION }}

        - uses: aws-actions/configure-aws-credentials@v2
          with:
            aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
            aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
            aws-region: ${{ env.AWS_REGION }}

        - name: Terraform Apply
          run: |
            terraform -chdir=infra apply \
              -var-file=prod.tfvars \
              -auto-approve

        - name: Get Outputs
          id: outputs
          run: |
            RDS_ENDPOINT=$(terraform -chdir=infra output -raw rds_endpoint)
            FARGATE_URL=$(terraform -chdir=infra output -raw fargate_service_url)
            echo "rds_endpoint=${RDS_ENDPOINT}" >> $GITHUB_OUTPUT
            echo "fargate_url=${FARGATE_URL}" >> $GITHUB_OUTPUT

        - name: Health Check
          run: |
            sleep 30
            curl -f ${{ steps.outputs.outputs.fargate_url }}/health || exit 1
  ```

---

## Weekly Checklist

### Week 1: Terraform Modules + State

- [ ] Create base infrastructure (VPC, subnets, security groups)
- [ ] Create modules: networking, RDS, ECS, ALB
- [ ] Set up S3 backend + DynamoDB state lock
- [ ] Test local: `terraform init`, `terraform plan dev.tfvars`
- [ ] Verify no hardcoded secrets (all in Secrets Manager)
- [ ] Interview Q: "Design multi-env Terraform structure?" → Answer drafted
- [ ] Commits: 6–8 (modules, backend setup, state lock, tests)

### Week 2: CI/CD + Deployment

- [ ] GitHub Actions workflow: plan → approve → apply
- [ ] Test full cycle: code change → plan → manual approval → apply
- [ ] Verify workspaces: `terraform workspace list` shows dev/staging/prod
- [ ] Rollback test: Revert Terraform code, re-apply, verify previous infra restored
- [ ] Manual change detection: Change RDS in AWS console, run `terraform plan`, verify drift detected
- [ ] Secrets rotation: Update JWT key in Secrets Manager, verify app uses new key
- [ ] Interview Q: "State locked 2 hours. Recovery?" → Full answer ready
- [ ] Commits: 5–7 (workflows, drift detection, rollback tests)
- [ ] Portfolio item + LinkedIn post (feature: "Infrastructure as Code for multi-env deployment")

---

## Success Metrics

| Metric              | Target      | How to Measure                                                        |
| ------------------- | ----------- | --------------------------------------------------------------------- |
| Terraform plan time | <30s        | Time `terraform plan` output                                          |
| State lock timeout  | Never stuck | No manual `force-unlock` needed over 2 weeks                          |
| Manual AWS changes  | 0 detected  | `terraform plan` reports zero drift daily                             |
| Workspace isolation | 3 separate  | `terraform workspace list` shows dev/staging/prod with separate state |
| Secrets in code     | 0           | `git log -S "sk_\|AKIA"` finds nothing                                |
| Approval gates      | Required    | Prod apply requires manual GitHub approval, tracked in logs           |
| Rollback time       | <5 min      | Revert code + apply takes <5 min (tested)                             |
| Commit count        | 11–15       | 1 per module / workflow update                                        |

---

## Gotchas + Fixes

### Gotcha 1: "State Lock Stuck After Crashed Apply"

**Symptom**: `terraform apply` fails, next apply hangs with lock error.
**Cause**: Previous process didn't release lock (crashed, timeout, or manual kill).
**Fix**: `terraform force-unlock <LOCK_ID>`. Check DynamoDB table for stale lock entries.
**Prevention**: Set `skip_credentials_validation=false` + timeout monitoring.

### Gotcha 2: "Manual RDS Change Not Detected by Terraform"

**Symptom**: DBA modifies RDS in AWS console, `terraform plan` reports no changes.
**Cause**: Terraform state cached from last apply, not synced with AWS reality.
**Fix**: `terraform refresh` or `terraform apply -refresh-only` to sync state with AWS.
**Prevention**: Enforce IaC-only changes (no console access for prod).

### Gotcha 3: "Secrets Appear in Terraform Plan Output"

**Symptom**: Sensitive value (password, API key) printed in `terraform plan` logs.
**Cause**: Terraform logging verbose, or secret passed as regular variable.
**Fix**: Mark variables `sensitive = true`, suppress logging in CI (`TF_LOG=error`).
**Prevention**: All secrets in Secrets Manager, never in tfvars.

### Gotcha 4: "Workspace Switching Doesn't Apply Correct tfvars"

**Symptom**: `terraform workspace select prod` but dev resources deployed.
**Cause**: `-var-file` not specified per workspace, defaults to terraform.tfvars.
**Fix**: Always use `-var-file=prod.tfvars` in commands (don't rely on workspace).
**Prevention**: Wrapper script: `tf-apply prod` auto-applies `-var-file=prod.tfvars`.

---

## Cleanup (End of Phase 8)

```bash
# Destroy non-prod infra
terraform -chdir=infra destroy -var-file=dev.tfvars -auto-approve

# Verify state lock released
aws dynamodb scan --table-name terraform-lock
# Should be empty or only prod workspaces
```

---

## Metrics to Monitor Ongoing

- Terraform plan duration: Alert if > 60s (infrastructure complexity grew)
- State lock held time: Alert if > 5 min (stuck apply)
- Manual console changes: `terraform plan` drift report (weekly audit)
- Secrets rotation compliance: Last rotation date in Secrets Manager (alert if >90d)

---

## Project Completion Checkpoint

**All 8 phases complete:**

- ✅ Phase 1: Event streaming (Redpanda, 10M events/day)
- ✅ Phase 2: Data scraping (GraphQL + Playwright, rate limiting)
- ✅ Phase 3: Docker + CI/CD (multi-stage, ECR, GitHub Actions)
- ✅ Phase 4: AI + Vector DB (embeddings, Qdrant, semantic search)
- ✅ Phase 5: Testing (pytest, 100% coverage, async mocking)
- ✅ Phase 6: Database (40 SQL patterns, <50ms p99 latency)
- ✅ Phase 7: Security (JWT + refresh tokens, rate limiting)
- ✅ Phase 8: Infrastructure (Terraform, multi-env, GitOps)

**Artifacts Delivered:**

- 100+ commits (12–15 per phase, all tracked)
- 8 LinkedIn posts (technical tone, metrics-driven)
- 8 portfolio items (GitHub links, interview prep)
- 100% test coverage
- Zero CVEs in dependencies
- Production-ready infrastructure (Terraform-driven)

**Interview Readiness:**

- Core Q + 2 follow-ups per phase (all articulated)
- CV narrative: "Backend engineer shipping multi-service data platforms. Specialized in event streaming, async Python, embeddings, database optimization, infrastructure automation."

---

END OF DATA ZOO PLATFORM — 8-PHASE LEARNING COMPLETION
