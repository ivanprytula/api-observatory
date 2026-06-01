# ── Subnet Group ─────────────────────────────────────────────────────────────
resource "aws_db_subnet_group" "main" {
  count      = var.create_subnet_group ? 1 : 0
  name       = "${var.project}-${var.environment}-db-subnet-group"
  subnet_ids = var.private_subnet_ids

  tags = { Name = "${var.project}-${var.environment}-db-subnet-group" }
}

# ── Parameter Group ───────────────────────────────────────────────────────────
resource "aws_db_parameter_group" "pg17" {
  name        = "${var.project}-${var.environment}-pg17"
  family      = "postgres17"
  description = "Custom parameters for ${var.project} ${var.environment}"

  parameter {
    # Log slow queries (>1s) for performance monitoring
    name  = "log_min_duration_statement"
    value = "1000"
  }

  parameter {
    name  = "log_connections"
    value = "1"
  }

  tags = { Name = "${var.project}-${var.environment}-pg17-params" }
}

# ── RDS Instance (AWS managed password) ───────────────────────────────────────
resource "aws_db_instance" "main_managed" {
  count = var.manage_master_user_password ? 1 : 0

  identifier = "${var.project}-${var.environment}-postgres"

  engine         = "postgres"
  engine_version = "17"
  instance_class = var.instance_class

  # Storage — gp3 for better baseline IOPS/throughput vs gp2
  allocated_storage     = var.allocated_storage_gb
  max_allocated_storage = var.max_allocated_storage_gb
  storage_type          = "gp3"
  storage_encrypted     = true
  # KMS: leave null → uses AWS-managed key (aws/rds)

  db_name  = var.db_name
  username = var.db_username
  manage_master_user_password = true

  db_subnet_group_name   = var.create_subnet_group ? aws_db_subnet_group.main[0].name : var.db_subnet_group_name
  vpc_security_group_ids = [var.sg_db_id]
  parameter_group_name   = aws_db_parameter_group.pg17.name

  # Availability
  multi_az            = var.multi_az
  publicly_accessible = false

  # Backups
  backup_retention_period   = var.backup_retention_days
  backup_window             = "03:00-04:00"  # UTC — low-traffic window
  maintenance_window        = "Mon:04:00-Mon:05:00"
  delete_automated_backups  = false

  # Logging → CloudWatch
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]

  # Protection
  deletion_protection      = var.environment == "prod"
  skip_final_snapshot      = var.environment != "prod"
  final_snapshot_identifier = var.environment == "prod" ? "${var.project}-${var.environment}-final-snapshot" : null

  apply_immediately = var.environment != "prod"

  tags = { Name = "${var.project}-${var.environment}-postgres" }
}

# ── RDS Instance (explicit password for LocalStack/dev) ──────────────────────
resource "aws_db_instance" "main_unmanaged" {
  count = var.manage_master_user_password ? 0 : 1

  identifier = "${var.project}-${var.environment}-postgres"

  engine         = "postgres"
  engine_version = "17"
  instance_class = var.instance_class

  # Storage — gp3 for better baseline IOPS/throughput vs gp2
  allocated_storage     = var.allocated_storage_gb
  max_allocated_storage = var.max_allocated_storage_gb
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name   = var.db_name
  username  = var.db_username
  password  = var.master_password

  db_subnet_group_name   = var.create_subnet_group ? aws_db_subnet_group.main[0].name : var.db_subnet_group_name
  vpc_security_group_ids = [var.sg_db_id]
  parameter_group_name   = aws_db_parameter_group.pg17.name

  # Availability
  multi_az            = var.multi_az
  publicly_accessible = false

  # Backups
  backup_retention_period  = var.backup_retention_days
  backup_window            = "03:00-04:00"  # UTC — low-traffic window
  maintenance_window       = "Mon:04:00-Mon:05:00"
  delete_automated_backups = false

  # Logging → CloudWatch
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]

  # Protection
  deletion_protection       = var.environment == "prod"
  skip_final_snapshot       = var.environment != "prod"
  final_snapshot_identifier = var.environment == "prod" ? "${var.project}-${var.environment}-final-snapshot" : null

  apply_immediately = var.environment != "prod"

  tags = { Name = "${var.project}-${var.environment}-postgres" }
}
