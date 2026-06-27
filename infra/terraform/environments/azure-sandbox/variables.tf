variable "project" {
  description = "Project name prefix"
  type        = string
  default     = "api-observatory"
}

variable "location" {
  description = "Azure region (emulated locally by floci-az)"
  type        = string
  default     = "polandcentral"
}
