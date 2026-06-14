variable "aws_region" {
  type    = string
  default = "eu-central-1"
}

variable "aws_profile" {
  description = "AWS named profile for sandbox — use [sandbox] credential block."
  type        = string
  default     = "sandbox"
}

variable "emulator_endpoint" {
  description = "Local emulator base URL (Floci, LocalStack, etc.)."
  type        = string
  default     = "http://localhost:4566"
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "availability_zones" {
  type    = list(string)
  default = ["eu-central-1a", "eu-central-1b"]
}

variable "github_repository" {
  type    = string
  default = "ivanprytula/api-observatory"
}

variable "image_tag" {
  type    = string
  default = "develop"
}

variable "ecr_services" {
  type    = list(string)
  default = ["ingestor", "dashboard"]
}

variable "enable_messaging" {
  type    = bool
  default = false
}

variable "enable_iam" {
  type    = bool
  default = false
}

variable "enable_database" {
  type    = bool
  default = true
}

variable "enable_cache" {
  type    = bool
  default = false
}

variable "db_master_password" {
  type      = string
  sensitive = true
  default   = "local-dev-db-password"
}

variable "db_subnet_group_name" {
  type    = string
  default = null
}

variable "redis_auth_token" {
  type      = string
  sensitive = true
  default   = "local-dev-redis-token"
}
