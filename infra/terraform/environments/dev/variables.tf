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
  default = "ivanprytula/api-observatory"
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

variable "enable_iam" {
  description = "Enable IAM/OIDC module in dev. Disable for LocalStack MVP runs."
  type        = bool
  default     = false
}

variable "enable_database" {
  description = "Enable RDS database module in dev. Disable for LocalStack MVP runs."
  type        = bool
  default     = false
}

variable "enable_cache" {
  description = "Enable ElastiCache module in dev. Disable for LocalStack MVP runs."
  type        = bool
  default     = false
}

variable "nat_gateway_count" {
  description = "Number of NAT gateways for network module. Use 0 for LocalStack MVP runs."
  type        = number
  default     = 0
}

variable "ecr_services" {
  description = "ECR repositories to create in dev. Keep this list minimal for MVP."
  type        = list(string)
  default     = ["ingestor"]
}

variable "db_master_password" {
  description = "RDS master password when db_manage_master_user_password is false (LocalStack/dev sandbox)."
  type        = string
  sensitive   = true
  default     = null
}

variable "db_manage_master_user_password" {
  description = "Use AWS managed DB password (true for AWS, false for LocalStack)."
  type        = bool
  default     = true
}

variable "db_create_subnet_group" {
  description = "Create DB subnet group in module (true for AWS, often false for LocalStack)."
  type        = bool
  default     = true
}

variable "db_subnet_group_name" {
  description = "Existing DB subnet group name when db_create_subnet_group is false."
  type        = string
  default     = null
}
