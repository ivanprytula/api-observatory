output "primary_endpoint" {
  description = "Redis primary endpoint address."
  value       = aws_elasticache_replication_group.redis.primary_endpoint_address
  sensitive   = true
}

output "port" {
  value = 6379
}
