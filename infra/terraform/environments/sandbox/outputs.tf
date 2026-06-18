output "alb_dns_name" {
  description = "DNS name of the ALB (ingestor entry point)."
  value       = module.compute.alb_dns_name
}

output "ecr_repository_urls" {
  description = "ECR repository URLs keyed by service name."
  value       = module.ecr.repository_urls
}

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint (host:port)."
  value       = try(module.database[0].endpoint, null)
  sensitive   = true
}
