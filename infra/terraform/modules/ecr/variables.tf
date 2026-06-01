variable "project" {
  description = "Short project name used in repository path prefix."
  type        = string
}

variable "services" {
  description = "Service names that should get an ECR repository."
  type        = list(string)
  default     = ["ingestor", "processor", "ai-gateway", "query-api", "dashboard"]
}
