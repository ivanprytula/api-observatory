output "cluster_id" {
  description = "Cluster identifier (ECS cluster name or EKS cluster name)."
  value       = try(aws_ecs_cluster.main[0].name, null)
}

output "cluster_arn" {
  description = "Cluster ARN."
  value       = try(aws_ecs_cluster.main[0].arn, null)
}

output "alb_dns_name" {
  description = "ALB DNS name (ECS only) — point your domain's CNAME here."
  value       = try(aws_lb.main[0].dns_name, null)
}

output "alb_zone_id" {
  description = "ALB hosted zone ID for Route 53 alias records (ECS only)."
  value       = try(aws_lb.main[0].zone_id, null)
}

output "ecs_cluster_name" {
  description = "ECS cluster name (ECS only)."
  value       = try(aws_ecs_cluster.main[0].name, null)
}

output "ecs_cluster_arn" {
  description = "ECS cluster ARN (ECS only)."
  value       = try(aws_ecs_cluster.main[0].arn, null)
}

output "ingestor_task_definition_arn" {
  description = "ECS task definition ARN for ingestor (ECS only)."
  value       = try(aws_ecs_task_definition.ingestor_fargate[0].arn, null)
}

output "eks_cluster_endpoint" {
  description = "EKS cluster API endpoint (EKS only)."
  value       = null
}

output "eks_cluster_certificate_authority" {
  description = "EKS cluster CA certificate data (EKS only)."
  value       = null
  sensitive   = true
}

output "compute_type" {
  description = "Active compute backend (for reference)."
  value       = var.compute_type
}
