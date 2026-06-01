variable "aws_region" {
  description = "AWS region for all resources. Set via TF_VAR_aws_region env var or -var flag. No default to enforce explicit selection."
  type        = string
}

variable "project" {
  description = "Short project name used in resource naming."
  type        = string
  default     = "data-zoo"
}

variable "environment" {
  description = "Deployment environment (dev | prod)."
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be 'dev' or 'prod'."
  }
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "List of AZs to use. Set via TF_VAR_availability_zones env var or -var flag. If not set, will use default AZs for the region."
  type        = list(string)
  default     = null  # When null, AZ selection logic in env-specific terraform.tfvars applies
}

variable "app_port" {
  description = "Port the ingestor container listens on."
  type        = number
  default     = 8000
}

variable "github_repository" {
  description = "GitHub repo in 'owner/repo' format, used for OIDC trust policy."
  type        = string
  default     = "ivanprytula/api-observatory"
}
