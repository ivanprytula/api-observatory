variable "project_id" {
  description = "GCP project ID (floci-gcp uses 'floci-local')"
  type        = string
  default     = "floci-local"
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "europe-central2"
}

variable "project" {
  description = "Project name prefix for all resources"
  type        = string
  default     = "api-observatory"
}
