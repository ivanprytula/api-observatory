variable "project" {
  description = "Short project name."
  type        = string
}

variable "aws_region" {
  description = "AWS region."
  type        = string
}

variable "github_repository" {
  description = "GitHub repository in 'owner/repo' format. Used in OIDC trust policy."
  type        = string
}
