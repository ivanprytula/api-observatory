# ── GitHub Actions OIDC Identity Provider ────────────────────────────────────
#
# Allows GitHub Actions workflows to authenticate to AWS without long-lived
# access keys. The trust policy restricts to this repo + specific branches.
#
# One-time setup: AWS only accepts one OIDC provider per URL.
# If another project already registered token.actions.githubusercontent.com,
# use a data source instead:
#
#   data "aws_iam_openid_connect_provider" "github" {
#     url = "https://token.actions.githubusercontent.com"
#   }
#   Then reference: data.aws_iam_openid_connect_provider.github.arn

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  # Thumbprint retrieved from GitHub's OIDC endpoint.
  # Verify against: https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/about-security-hardening-with-openid-connect
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

# ── IAM Role — GitHub Actions CI/CD ──────────────────────────────────────────
resource "aws_iam_role" "github_actions" {
  name        = "${var.project}-github-actions"
  description = "Assumed by GitHub Actions via OIDC. Grants ECR push + (future) ECS deploy."

  assume_role_policy = data.aws_iam_policy_document.github_actions_trust.json
}

data "aws_iam_policy_document" "github_actions_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Restrict to push events on main and develop branches only.
    # Pull request events get a different sub format; keep them out of this role.
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:${var.github_repository}:ref:refs/heads/main",
        "repo:${var.github_repository}:ref:refs/heads/develop",
      ]
    }
  }
}

# ── ECR Push Policy ───────────────────────────────────────────────────────────
resource "aws_iam_role_policy" "ecr_push" {
  name   = "ecr-push"
  role   = aws_iam_role.github_actions.id
  policy = data.aws_iam_policy_document.ecr_push.json
}

data "aws_iam_policy_document" "ecr_push" {
  # Allow token generation for all ECR repos in this account/region
  statement {
    sid     = "ECRAuth"
    effect  = "Allow"
    actions = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  # Allow image push to this project's repositories only
  statement {
    sid    = "ECRPush"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:CompleteLayerUpload",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = ["arn:aws:ecr:${var.aws_region}:${data.aws_caller_identity.current.account_id}:repository/${var.project}/*"]
  }
}

# ── ECS Deploy Policy (attached but actions are denied via SCP until needed) ──
# Uncomment when you're ready to enable CD from GitHub Actions.
#
# resource "aws_iam_role_policy" "ecs_deploy" {
#   name   = "ecs-deploy"
#   role   = aws_iam_role.github_actions.id
#   policy = data.aws_iam_policy_document.ecs_deploy.json
# }
#
# data "aws_iam_policy_document" "ecs_deploy" {
#   statement {
#     sid    = "ECSUpdate"
#     effect = "Allow"
#     actions = [
#       "ecs:UpdateService",
#       "ecs:DescribeServices",
#       "ecs:DescribeTaskDefinition",
#       "ecs:RegisterTaskDefinition",
#       "iam:PassRole",  # Required for ECS to assume the task execution role
#     ]
#     resources = [
#       "arn:aws:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:cluster/${var.project}-*",
#       "arn:aws:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:service/${var.project}-*/*",
#       "arn:aws:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:task-definition/${var.project}-*:*",
#     ]
#   }
# }

data "aws_caller_identity" "current" {}
