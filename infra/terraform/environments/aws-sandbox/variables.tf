variable "aws_region" {
  description = "AWS region (LocalStack ignores this but required by provider)"
  type        = string
  default     = "eu-central-1"
}

variable "project" {
  description = "Project name prefix for all resources"
  type        = string
  default     = "api-observatory"
}
