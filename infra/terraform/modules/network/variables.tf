variable "project" {
  description = "Short project name."
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev | prod)."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "List of AZs to deploy into."
  type        = list(string)
}

variable "nat_gateway_count" {
  description = "Number of NAT Gateways. Use 1 for dev (cost), len(AZs) for prod (resilience)."
  type        = number
  default     = 1
}

variable "app_port" {
  description = "Port the application containers expose."
  type        = number
  default     = 8000
}
