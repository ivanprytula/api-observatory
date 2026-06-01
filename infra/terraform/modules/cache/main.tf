resource "aws_elasticache_subnet_group" "main" {
  name       = "${var.project}-${var.environment}-cache-subnet"
  subnet_ids = var.private_subnet_ids
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "${var.project}-${var.environment}-redis"
  description          = "Redis cache for ${var.project} ${var.environment}"

  node_type            = var.node_type
  num_cache_clusters   = var.num_cache_clusters  # 1 for dev, 2+ for prod
  port                 = 6379
  parameter_group_name = "default.redis7"
  engine_version       = "7.1"

  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [var.sg_cache_id]

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token                 = var.auth_token  # Strong random token, stored in SSM

  automatic_failover_enabled = var.num_cache_clusters > 1

  # Maintenance during off-peak hours
  maintenance_window       = "sun:05:00-sun:06:00"
  snapshot_retention_limit = var.environment == "prod" ? 7 : 1
  snapshot_window          = "04:00-05:00"

  tags = { Name = "${var.project}-${var.environment}-redis" }
}
