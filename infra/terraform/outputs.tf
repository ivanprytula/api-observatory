output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer (ingestor entry point)."
  value       = module.compute.alb_dns_name
}

output "ecr_repository_urls" {
  description = "ECR repository URLs keyed by service name."
  value       = module.ecr.repository_urls
}

output "github_actions_role_arn" {
  description = "IAM role ARN for GitHub Actions OIDC authentication."
  value       = module.iam.github_actions_role_arn
}

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint (host:port)."
  value       = module.database.endpoint
  sensitive   = true
}
