variable "aws_region" {
  description = "AWS region. Must be set explicitly via TF_VAR_aws_region env var or in terraform.tfvars."
  type        = string
}

variable "aws_profile" {
  description = "AWS named profile to use. Set via TF_VAR_aws_profile or CLI."
  type        = string
  default     = "data-zoo-dev"
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "AZs for the region. Set in terraform.tfvars or via TF_VAR_availability_zones."
  type        = list(string)
  default     = null
}

variable "github_repository" {
  type    = string
  default = "ivanprytula/data-pipeline-async"
}

variable "redis_auth_token" {
  description = "Redis AUTH token. Source from SSM or pass via TF_VAR_redis_auth_token."
  type        = string
  sensitive   = true
}

variable "acm_certificate_arn" {
  description = "ACM certificate ARN for the HTTPS ALB listener."
  type        = string
  default     = ""  # Must be set before applying compute module
}

variable "image_tag" {
  description = "Docker image tag to deploy."
  type        = string
  default     = "develop"
}

variable "enable_messaging" {
  description = "Enable MSK messaging module in dev. Disabled by default to reduce local sandbox cost."
  type        = bool
  default     = false
}
