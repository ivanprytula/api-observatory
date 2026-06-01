variable "project" { type = string }
variable "environment" { type = string }

variable "private_subnet_ids" {
  type = list(string)
}

variable "sg_cache_id" {
  type = string
}

variable "node_type" {
  description = "ElastiCache node type. cache.t3.micro for dev."
  type        = string
  default     = "cache.t3.micro"
}

variable "num_cache_clusters" {
  description = "Number of nodes. 1 for dev (no HA), 2+ for prod (automatic failover)."
  type        = number
  default     = 1
}

variable "auth_token" {
  description = "Redis AUTH token. Store in SSM and pass as a sensitive variable."
  type        = string
  sensitive   = true
}
