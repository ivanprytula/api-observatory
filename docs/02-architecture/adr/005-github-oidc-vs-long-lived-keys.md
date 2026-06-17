# ADR 005: GitHub Actions OIDC vs Long-Lived AWS Access Keys

Track: C — Architecture and Platform Strategy


**Date**: April 22, 2026
**Status**: Accepted
**Context**: Phase 7 CI/CD pipeline needs to authenticate with AWS to push container images to ECR and deploy to ECS. Need to choose between OIDC provider (workload identity) vs traditional long-lived access keys.

---

## Problem

How should GitHub Actions authenticate with AWS in the CI/CD pipeline?

- **GitHub OIDC Provider**: GitHub generates a JWT per workflow run; exchange it for temporary AWS credentials
- **Long-Lived Access Keys**: Store AWS `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` in GitHub Secrets

---

## Decision

#### Use GitHub OIDC Provider with temporary AWS credentials.

### Rationale

| Factor | GitHub OIDC | Long-Lived Keys | Winner |
|--------|-------------|-----------------|--------|
| **Security Risk** | Low (JWT valid 5 min, scoped) | High (keys valid forever, full AWS account) | OIDC |
| **Credential Rotation** | Automatic (token refreshes per run) | Manual (must rotate every 90 days) | OIDC |
| **Audit Trail** | CloudTrail records every assume-role | CloudTrail shows "user" but not which workflow | OIDC |
| **Accidental Exposure** | Limited blast radius (5 min window) | Entire AWS account compromised until rotated | OIDC |
| **Setup Time** | 30 min (IAM provider + role + trust policy) | 5 min (copy-paste keys) | Keys |
| **Team Scaling** | One setup per AWS account | Keys per env (keys × envs) | OIDC |
| **Revocation** | Delete provider or role (instant) | Rotate all keys everywhere (hours) | OIDC |

### Why GitHub OIDC?

1. **Workload Identity Federation** (industry standard)
   - GitHub Action runs as specific workload (main branch, develop branch, etc.)
   - AWS IAM role trusts only that workload
   - No human user involved

2. **Temporary Credentials**
   - JWT valid for 5 minutes
   - STS token expires after 1 hour
   - Compromise window is small

3. **Audit Trail**
   - CloudTrail logs: `"principal": "arn:aws:iam::123456:role/github-actions-role"`
   - Can trace which workflow / branch deployed what
   - Much better than generic "user" entries

4. **Scalability**
   - Add new repository: update trust policy (one-time)
   - No new keys to rotate
   - Works across teams

---

## Implementation

### AWS Setup (Terraform)

```hcl
# Create OIDC provider in AWS
resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]  # GitHub's public cert
}

# Create role that GitHub can assume
resource "aws_iam_role" "github_actions" {
  name = "data-zoo-github-actions"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = aws_iam_openid_connect_provider.github.arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          }
          StringLike = {
            "token.actions.githubusercontent.com:sub" = "repo:YOUR_ORG/api-observatory:ref:refs/heads/main"
          }
        }
      }
    ]
  })
}

# Attach ECR push policy
resource "aws_iam_role_policy" "ecr_push" {
  name = "ecr-push"
  role = aws_iam_role.github_actions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:PutImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload"
        ]
        Resource = "*"
      }
    ]
  })
}
```

### GitHub Actions Workflow

```yaml
name: Build and Push to ECR

on:
  push:
    branches: [main, develop]

jobs:
  build:
    runs-on: ubuntu-latest

    permissions:
      contents: read
      id-token: write  # Critical: allows GitHub to generate JWT

    steps:
      - uses: actions/checkout@v4

      - name: Assume AWS role via OIDC
        uses: aws-actions/configure-aws-credentials@v2
        with:
          role-to-assume: arn:aws:iam::123456789012:role/data-zoo-github-actions
          aws-region: eu-central-1

      - name: Login to ECR
        run: aws ecr get-login-password --region eu-central-1 | docker login --username AWS --password-stdin 123456789012.dkr.ecr.eu-central-1.amazonaws.com

      - name: Build and push
        run: docker push 123456789012.dkr.ecr.eu-central-1.amazonaws.com/data-zoo:${{ github.sha }}
```

### GitHub Secrets Required

Only **non-sensitive** values:

| Secret | Value | Why it's OK to expose |
|--------|-------|-----|
| `AWS_ACCOUNT_ID` | `123456789012` | No secrets; public info once you deploy |
| `AWS_ROLE_ARN` | `arn:aws:iam::123456789012:role/data-zoo-github-actions` | Role name is deployment detail; no credentials |

#### NO secrets needed:

- ❌ `AWS_ACCESS_KEY_ID`
- ❌ `AWS_SECRET_ACCESS_KEY`

---

## Consequences

### Positive

- ✅ **No credential rotation**: Automatic token refresh per run
- ✅ **Smaller blast radius**: 5-minute window if token leaked
- ✅ **Full audit trail**: CloudTrail logs which workflow did what
- ✅ **Scales to multiple repos**: One setup, works for all
- ✅ **Industry standard**: Used by GitHub, Google Cloud, AWS, HashiCorp, etc.
- ✅ **No accidental exposure**: Keys never stored in GitHub Secrets

### Negative

- ❌ **More setup**: 30 minutes to configure provider + role + trust policy
- ❌ **Harder to debug**: JWT exchange requires understanding OpenID Connect
- ❌ **Branch-specific permissions**: If you need different envs (main → prod, develop → dev), you need separate roles or policy conditions

---

## Migration Path (if switching from keys)

1. **Keep old keys in GitHub Secrets** (don't delete yet)
2. **Set up OIDC provider + role** (30 minutes)
3. **Update GitHub Actions workflow** to use OIDC
4. **Test in develop branch** (confirm pushes work)
5. **Monitor CloudTrail** for 1 week
6. **Delete old access keys** from AWS IAM

---

## Alternatives Considered

### 1. AWS IAM User with Long-Lived Keys

- ✅ Simpler setup (5 min)
- ❌ No audit trail (generic "user")
- ❌ Manual rotation burden
- ❌ Scales poorly across repos
- ❌ If exposed, entire AWS account at risk

### 2. AWS Temporary Credentials (STS via CLI)

- ❌ Requires human to pre-generate credentials
- ❌ Still need to store in GitHub Secrets
- ❌ Defeats the purpose

### 3. GitHub Environments with Manual Approval

- ❌ Slows down deployment (wait for approval)
- ❌ Still needs credentials for approval context
- ✅ Good for prod (require approval before deploying)

### 4. AWS CloudFormation Service Role

- ❌ More complex than OIDC
- ❌ Requires service-linked role creation
- ✅ Useful if deploying CloudFormation instead of Terraform

---

## Related Decisions

- [ADR 008: ECS Fargate vs EKS](008-ecs-fargate-vs-eks.md) (compute choice)
- [Deployment Guide](../../07-deployment/deployment-guide.md) (comprehensive setup guide)

---

## References

- [GitHub Actions OIDC Documentation](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/about-security-hardening-with-openid-connect)
- [AWS IAM OIDC Provider Docs](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc.html)
- [GitHub Security Best Practices](https://securitylab.github.com/research/github-actions-preventing-pwn-requests/)
- [HashiCorp on Workload Identity Federation](https://www.hashicorp.com/blog/workload-identity-federation)
