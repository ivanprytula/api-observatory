variable "aws_region" {
  description = "AWS region. Must be set explicitly via TF_VAR_aws_region env var or in terraform.tfvars."
  type        = string
}

variable "aws_profile" {
  type = string
  default = "data-zoo-prod"
}
variable "vpc_cidr" {
  type = string
  default = "10.1.0.0/16"
}
variable "availability_zones" {
  description = "AZs for the region. Set in terraform.tfvars or via TF_VAR_availability_zones. Prod typically uses 3 AZs for HA."
  type        = list(string)
  default     = null
}

variable "github_repository" {
  type = string
  default = "ivanprytula/api-observatory"
}
variable "redis_auth_token" {
  type = string
  sensitive = true
}
variable "acm_certificate_arn" {
  type = string
}
variable "image_tag" {
  type = string
  default = "latest"
}
