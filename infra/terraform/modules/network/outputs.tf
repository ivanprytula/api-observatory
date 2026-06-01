output "vpc_id" {
  description = "VPC ID."
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "IDs of public subnets."
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "IDs of private subnets."
  value       = aws_subnet.private[*].id
}

output "sg_alb_id" {
  description = "Security group ID for the ALB."
  value       = aws_security_group.alb.id
}

output "sg_app_id" {
  description = "Security group ID for ECS app tasks."
  value       = aws_security_group.app.id
}

output "sg_db_id" {
  description = "Security group ID for RDS."
  value       = aws_security_group.db.id
}

output "sg_cache_id" {
  description = "Security group ID for ElastiCache."
  value       = aws_security_group.cache.id
}

output "sg_msk_id" {
  description = "Security group ID for MSK."
  value       = aws_security_group.msk.id
}
