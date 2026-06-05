variable "project" { type = string }
variable "environment" { type = string }
variable "aws_region" { type = string }

variable "vpc_id" { type = string }
variable "public_subnet_ids" { type = list(string) }
variable "private_subnet_ids" { type = list(string) }
variable "sg_alb_id" { type = string }
variable "sg_app_id" { type = string }

variable "app_port" {
  type    = number
  default = 8000
}

# ── Compute Backend Selection ──────────────────────────────────────────────────
variable "compute_type" {
  description = "Container runtime backend: 'ecs-fargate' (serverless), 'ecs-ec2' (cost-optimized), or 'eks' (Kubernetes)."
  type        = string
  default     = "ecs-fargate"

  validation {
    condition     = contains(["ecs-fargate", "ecs-ec2", "eks"], var.compute_type)
    error_message = "compute_type must be 'ecs-fargate', 'ecs-ec2', or 'eks'."
  }
}

variable "ecr_repository_url_ingestor" {
  description = "ECR URL for the ingestor image (from modules/ecr output)."
  type        = string
}

variable "ecr_repository_url_dashboard" {
  description = "ECR URL for the dashboard image (from modules/ecr output)."
  type        = string
}

variable "image_tag" {
  description = "Image tag to deploy. Typically the git SHA or 'latest'."
  type        = string
  default     = "latest"
}

variable "msk_cluster_arn" {
  description = "MSK Serverless cluster ARN for IAM auth policy."
  type        = string
  default     = ""
}

variable "kafka_topic_names" {
  description = "Optional explicit Kafka topic names for least-privilege IAM topic access. When empty, all topics in the cluster are allowed."
  type        = list(string)
  default     = []
}

variable "acm_certificate_arn" {
  description = "ACM certificate ARN for the HTTPS ALB listener. Required before apply."
  type        = string
}

variable "alb_access_log_bucket" {
  description = "S3 bucket name for ALB access logs. Empty string disables logging."
  type        = string
  default     = ""
}

variable "log_retention_days" {
  description = "Days to retain CloudWatch logs."
  type        = number
  default     = 30
}

# ── Ingestor sizing ────────────────────────────────────────────────────────────
variable "ingestor_cpu" {
  description = "Fargate CPU units (256 = 0.25 vCPU). Valid: 256, 512, 1024, 2048, 4096."
  type        = number
  default     = 256
}

variable "ingestor_memory" {
  description = "Fargate memory in MiB. Must be compatible with cpu setting."
  type        = number
  default     = 512
}

variable "ingestor_desired_count" {
  description = "Desired number of ingestor tasks (ECS only)."
  type        = number
  default     = 1
}

# ── Dashboard sizing ────────────────────────────────────────────────────────────
variable "dashboard_cpu" {
  description = "Fargate CPU units for dashboard (256 = 0.25 vCPU)."
  type        = number
  default     = 256
}

variable "dashboard_memory" {
  description = "Fargate memory in MiB for dashboard."
  type        = number
  default     = 512
}

variable "dashboard_desired_count" {
  description = "Desired number of dashboard tasks (ECS only)."
  type        = number
  default     = 1
}

variable "ingestor_service_name" {
  description = "ECS service discovery name for ingestor (used by dashboard to reach API)."
  type        = string
  default     = "ingestor"
}

# ── ECS EC2 Backend ────────────────────────────────────────────────────────────
variable "ec2_instance_type" {
  description = "EC2 instance type for ECS cluster (e.g., 't3.medium'). Only used if compute_type='ecs-ec2'."
  type        = string
  default     = "t3.medium"
}

variable "ec2_desired_capacity" {
  description = "Desired number of EC2 instances in the ECS cluster. Only used if compute_type='ecs-ec2'."
  type        = number
  default     = 1
}

variable "ec2_min_capacity" {
  description = "Minimum number of EC2 instances. Only used if compute_type='ecs-ec2'."
  type        = number
  default     = 1
}

variable "ec2_max_capacity" {
  description = "Maximum number of EC2 instances for auto-scaling. Only used if compute_type='ecs-ec2'."
  type        = number
  default     = 5
}

variable "ec2_use_spot" {
  description = "Use EC2 Spot instances (cost-optimized, interruptible). Only used if compute_type='ecs-ec2'."
  type        = bool
  default     = false
}

# ── EKS Backend ────────────────────────────────────────────────────────────────
variable "eks_version" {
  description = "Kubernetes version for EKS cluster (e.g., '1.29'). Only used if compute_type='eks'."
  type        = string
  default     = "1.29"
}

variable "eks_instance_type" {
  description = "EC2 instance type for EKS worker nodes (e.g., 't3.medium'). Only used if compute_type='eks'."
  type        = string
  default     = "t3.medium"
}

variable "eks_desired_size" {
  description = "Desired number of worker nodes in EKS node group. Only used if compute_type='eks'."
  type        = number
  default     = 2
}

variable "eks_min_size" {
  description = "Minimum number of worker nodes. Only used if compute_type='eks'."
  type        = number
  default     = 1
}

variable "eks_max_size" {
  description = "Maximum number of worker nodes for auto-scaling. Only used if compute_type='eks'."
  type        = number
  default     = 5
}
