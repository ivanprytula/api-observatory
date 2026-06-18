output "alb_dns_name" {
  description = "DNS name of the ALB (ingestor entry point)."
  value       = module.compute.alb_dns_name
}

output "ecr_repository_urls" {
  description = "ECR repository URLs keyed by service name."
  value       = module.ecr.repository_urls
}

output "github_actions_role_arn" {
  description = "IAM role ARN for GitHub Actions OIDC authentication."
  value       = try(module.iam[0].github_actions_role_arn, null)
}

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint (host:port)."
  value       = try(module.database[0].endpoint, null)
  sensitive   = true
}
