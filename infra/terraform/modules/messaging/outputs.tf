output "bootstrap_brokers" {
  description = "MSK Serverless bootstrap broker string (IAM/TLS)."
  value       = aws_msk_serverless_cluster.main.bootstrap_brokers_sasl_iam
  sensitive   = true
}

output "cluster_arn" {
  value = aws_msk_serverless_cluster.main.arn
}
