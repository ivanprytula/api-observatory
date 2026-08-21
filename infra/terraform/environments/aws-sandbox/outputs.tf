output "vpc_id" {
  description = "VPC ID (LocalStack)"
  value       = aws_vpc.main.id
}

output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.app.id
}

output "instance_public_ip" {
  description = "EC2 public IP"
  value       = aws_instance.app.public_ip
}

output "ebs_volume_device" {
  description = "EBS device name (Xen-normalized on the instance)"
  value       = "/dev/xvdf"
}

output "ebs_mount_point" {
  description = "Mount point for PostgreSQL data on EBS"
  value       = "/mnt/ebs/postgres"
}

# EBS volumes + mount points for the monitoring stack. Each must be formatted
# and mounted at /mnt/ebs/<svc> on the instance to match the aws-env compose.
output "monitoring_ebs" {
  description = "Monitoring EBS volumes, device names, and intended mount points"
  value = {
    prometheus   = { device = "/dev/sdg", mount = "/mnt/ebs/prometheus", volume_id = aws_ebs_volume.prometheus_data.id }
    grafana      = { device = "/dev/sdh", mount = "/mnt/ebs/grafana", volume_id = aws_ebs_volume.grafana_data.id }
    loki         = { device = "/dev/sdi", mount = "/mnt/ebs/loki", volume_id = aws_ebs_volume.loki_data.id }
    promtail     = { device = "/dev/sdj", mount = "/mnt/ebs/promtail", volume_id = aws_ebs_volume.promtail_data.id }
    tempo        = { device = "/dev/sdk", mount = "/mnt/ebs/tempo", volume_id = aws_ebs_volume.tempo_data.id }
    alertmanager = { device = "/dev/sdl", mount = "/mnt/ebs/alertmanager", volume_id = aws_ebs_volume.alertmanager_data.id }
    mailpit      = { device = "/dev/sdm", mount = "/mnt/ebs/mailpit", volume_id = aws_ebs_volume.mailpit_data.id }
  }
}

output "ses_sender_email" {
  description = "SES verified sender identity"
  value       = aws_ses_email_identity.sender.email
}
