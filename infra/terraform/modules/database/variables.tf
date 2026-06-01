variable "project" {
  type = string
}

variable "environment" {
  type = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for the DB subnet group."
  type        = list(string)
}

variable "create_subnet_group" {
  description = "Whether to create an RDS DB subnet group in this module. Disable for LocalStack where DB subnet groups may be unsupported."
  type        = bool
  default     = true
}

variable "db_subnet_group_name" {
  description = "Existing DB subnet group name to use when create_subnet_group is false."
  type        = string
  default     = null
}

variable "sg_db_id" {
  description = "Security group ID for the RDS instance."
  type        = string
}

variable "instance_class" {
  description = "RDS instance class. db.t3.micro for dev, db.t3.medium+ for prod."
  type        = string
  default     = "db.t3.micro"
}

variable "db_name" {
  description = "Initial database name."
  type        = string
  default     = "data_pipeline"
}

variable "db_username" {
  description = "Master DB username."
  type        = string
  default     = "datazoo_admin"
}

variable "allocated_storage_gb" {
  type    = number
  default = 20
}

variable "max_allocated_storage_gb" {
  description = "Upper limit for storage autoscaling."
  type        = number
  default     = 100
}

variable "multi_az" {
  description = "Enable Multi-AZ for high availability (prod: true, dev: false)."
  type        = bool
  default     = false
}

variable "backup_retention_days" {
  description = "Days to retain automated backups. 0 disables backups."
  type        = number
  default     = 7
}

variable "manage_master_user_password" {
  description = "Use AWS-managed master password in Secrets Manager."
  type        = bool
  default     = true
}

variable "master_password" {
  description = "Master DB password used only when manage_master_user_password is false."
  type        = string
  sensitive   = true
  default     = null

  validation {
    condition     = var.manage_master_user_password || var.master_password != null
    error_message = "master_password must be set when manage_master_user_password is false."
  }
}
