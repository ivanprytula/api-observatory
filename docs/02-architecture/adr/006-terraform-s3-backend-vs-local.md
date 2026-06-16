# ADR 006: Terraform Remote S3 Backend with Native Lockfile vs Local State

Track: C — Architecture and Platform Strategy


**Date**: April 22, 2026
**Status**: Accepted
**Context**: Phase 7 requires team-safe infrastructure management. Terraform state must be safe from concurrent edits, versioned, and accessible across team members and CI/CD pipelines.

---

## Problem

Where should Terraform state be stored?

- **Local (default)**: `terraform.tfstate` in project directory
- **Remote S3 + lockfile**: State in S3 bucket, locking via S3 native lockfile (team-safe)

---

## Decision

#### Use remote S3 backend with native lockfile state locking.

### Rationale

| Factor | Local State | S3 + lockfile | Winner |
|--------|------------|---------------|--------|
| **Concurrent Edits** | Dangerous (merge conflicts) | Safe (lockfile mutex) | S3 + lockfile |
| **Accidental Overwrite** | Easy (git merge, manual edit) | Prevented (lock prevents apply) | S3 + lockfile |
| **Version History** | Manual (commit to git) | Automatic (S3 versioning) | S3 + lockfile |
| **Team Collaboration** | Hard (one laptop owns state) | Easy (everyone reads from S3) | S3 + lockfile |
| **CI/CD Integration** | Requires passing state file | State lives in AWS (CI/CD reads) | S3 + lockfile |
| **Security** | Plaintext in git (secrets exposed) | Encrypted at rest, access controlled | S3 + lockfile |
| **Setup Time** | 0 min (instant) | 15 min (create S3 bucket + backend config) | Local |
| **Cost** | Free | low monthly S3 storage cost | Local |

### Why Remote S3 Backend?

1. **Prevents Concurrent Edits**
   - Two engineers can't apply Terraform simultaneously
  - S3 native lockfile acts as mutex
   - One engineer acquires lock → applies → releases lock

2. **Team Scalability**
   - Any team member can deploy without needing state file
   - CI/CD pipeline automatically reads latest state
   - No "state file lives on Sarah's laptop" problem

3. **Disaster Recovery**
   - State versioned in S3 (unlimited snapshots)
   - Can revert to previous state if something broke
   - Audit trail of who deployed what when

4. **Security**
   - State file often contains secrets (database passwords, API keys)
   - S3 backend encrypts at rest (default AES-256)
   - Access controlled via IAM (not plaintext in git)

5. **CI/CD Integration**
   - GitHub Actions needs to read latest state
   - S3 backend seamlessly integrates via AWS credentials
   - No state file copying or checkout needed

---

## Implementation

### AWS Setup (one-time per account)

```bash
# Create S3 bucket for state
aws s3api create-bucket \
  --bucket data-zoo-terraform-state-dev \
  --region eu-central-1

# Enable versioning (can revert to previous state)
aws s3api put-bucket-versioning \
  --bucket data-zoo-terraform-state-dev \
  --versioning-configuration Status=Enabled

# Enable encryption at rest
aws s3api put-bucket-encryption \
  --bucket data-zoo-terraform-state-dev \
  --server-side-encryption-configuration \
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

```

### Terraform Configuration

```hcl
# infra/terraform/main.tf

terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    # These values passed via init flags (not hardcoded)
    # bucket         = "data-zoo-terraform-state-dev"
    # key            = "data-zoo/dev/terraform.tfstate"
    # region         = "eu-central-1"
    # use_lockfile   = true
    # encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region
}

# Rest of Terraform code...
```

### First-Time Initialization

```bash
cd infra/terraform/environments/dev

terraform init \
  -backend-config="bucket=data-zoo-terraform-state-dev" \
  -backend-config="key=data-zoo/dev/terraform.tfstate" \
  -backend-config="region=eu-central-1" \
  -backend-config="use_lockfile=true" \
  -backend-config="encrypt=true"

# Subsequent runs don't need flags; Terraform reads state from S3
```

### .gitignore

Add `terraform.tfstate`, `terraform.tfstate.*`, `.terraform/`, and `.terraform.lock.hcl`
to `.gitignore`. `terraform.tfvars.example` is safe to commit.

---

## Consequences

### Positive

- ✅ **Prevents merge conflicts**: lockfile lock prevents concurrent applies
- ✅ **Team-safe**: Multiple engineers can deploy without state file conflicts
- ✅ **Audit trail**: S3 versioning + CloudTrail logs all changes
- ✅ **CI/CD friendly**: Pipeline doesn't need state file checked out
- ✅ **Secrets safe**: State encrypted in S3, never in git
- ✅ **Disaster recovery**: Can revert to any previous state snapshot

### Negative

- ❌ **Network dependency**: Terraform needs AWS credentials to read/write state
- ❌ **Setup overhead**: S3 bucket hardening + backend config (15 min one-time)
- ❌ **Cost**: low monthly S3 storage cost (negligible but non-zero)
- ❌ **Harder local debugging**: Can't inspect `.tfstate` file directly (it's in S3)
- ❌ **Destroy risks**: If S3 bucket deleted, state is lost (but S3 versioning helps)

---

## State File Security Warning

**Never commit `terraform.tfstate` to git!** It contains:

- ❌ Database passwords
- ❌ API keys
- ❌ Private key material
- ❌ OAuth tokens

If accidentally committed: remove the file from git history using `git filter-repo` or
`git filter-branch` (requires force-push), then rotate all secrets immediately.

---

## When Local State Is OK

1. **Throwaway environments** (local dev, testing)
2. **Solo developer** (no team collaboration)
3. **No secrets in state** (hard-coded values only)
4. **No CI/CD** (never deployed automatically)

#### For any production or team project: use remote state.

---

## Migration Path (if switching from local)

1. **Create S3 bucket** (use script above)
2. **Initialize with remote backend** (Terraform automatically migrates)
3. **Verify state in S3** (`aws s3 ls`)
4. **Delete local state file** (after confirming S3 copy exists)
5. **Commit `.gitignore` changes** (prevent accidental commits)
6. **Team members** do `terraform init` to sync

---

## Alternatives Considered

### 1. Local State File (Committed to Git)
- ✅ Zero setup
- ❌ Secrets exposed in git
- ❌ Merge conflicts if two people deploy simultaneously
- ❌ No versioning
- ❌ CI/CD can't read latest state

### 2. Terraform Cloud / Enterprise
- ✅ Fully managed (no bucket setup)
- ✅ Great UI + state history
- ❌ Requires subscription ($20+/month)
- ❌ Vendor lock-in (state lives on Terraform Cloud)

### 3. Other Backends (Azure Blob Storage, GCS, etc.)
- ✅ Works if already using Azure/GCP
- ❌ Overkill if only using AWS
- ❌ Requires learning another cloud

---

## Related Decisions

- [ADR 008: ECS Fargate vs EKS](008-ecs-fargate-vs-eks.md) (what we're managing with Terraform)
- [ADR 005: GitHub OIDC vs Long-Lived Keys](005-github-oidc-vs-long-lived-keys.md) (how CI/CD accesses state)
- [Phase 7: Cloud Deployment](../cloud-deployment.md) (complete S3 backend setup guide)

---

## References

- [Terraform S3 Backend Documentation](https://www.terraform.io/language/settings/backends/s3)
- [Terraform State Locking](https://www.terraform.io/language/state/locking)
- [AWS S3 Versioning](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Versioning.html)
- [Terraform State Best Practices](https://www.terraform.io/language/state)
