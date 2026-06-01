output "endpoint" {
  description = "RDS endpoint in host:port format."
  value       = "${try(aws_db_instance.main_managed[0].address, aws_db_instance.main_unmanaged[0].address)}:${try(aws_db_instance.main_managed[0].port, aws_db_instance.main_unmanaged[0].port)}"
  sensitive   = true
}

output "address" {
  description = "RDS hostname."
  value       = try(aws_db_instance.main_managed[0].address, aws_db_instance.main_unmanaged[0].address)
  sensitive   = true
}

output "port" {
  description = "RDS port."
  value       = try(aws_db_instance.main_managed[0].port, aws_db_instance.main_unmanaged[0].port)
}

output "db_name" {
  description = "Database name."
  value       = try(aws_db_instance.main_managed[0].db_name, aws_db_instance.main_unmanaged[0].db_name)
}

output "master_user_secret_arn" {
  description = "ARN of the Secrets Manager secret holding the master password (managed by RDS)."
  value       = try(aws_db_instance.main_managed[0].master_user_secret[0].secret_arn, null)
  sensitive   = true
}
