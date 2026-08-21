variable "instance_type" {
  description = "EC2 instance type for the application host"
  type        = string
  default     = "t3.medium"
}

variable "ssh_allowed_cidr" {
  description = "CIDR block allowed for SSH access"
  type        = string
  default     = "0.0.0.0/0"
}

variable "ses_sender_email" {
  description = "Verified sender email address for SES"
  type        = string
  default     = "admin@example.com"
}

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
