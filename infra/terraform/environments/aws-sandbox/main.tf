terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.52"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }
}

provider "aws" {
  region                      = var.aws_region
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  endpoints {
    ec2 = "http://localhost:4566"
    sts = "http://localhost:4566"
  }
}

# Disposable AWS API rehearsal only. This is not parity with aws-dev and does
# not prove that the real account, state backend, IAM, or EC2 rollout is ready.
resource "aws_vpc" "main" {
  #checkov:skip=CKV2_AWS_11:Disposable emulator does not implement VPC flow logs
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name    = "${var.project}-vpc"
    Project = var.project
  }
}

resource "aws_default_security_group" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name    = "${var.project}-default-sg"
    Project = var.project
  }
}

# ─── IAM ──────────────────────────────────────────────────────────────────────

resource "aws_iam_role" "ec2_instance" {
  name = "${var.project}-ec2-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "ec2_ssm_read" {
  name = "${var.project}-ec2-ssm-read"
  role = aws_iam_role.ec2_instance.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["ssm:GetParameters", "ssm:GetParameter"]
      Effect   = "Allow"
      Resource = [
        aws_ssm_parameter.ses_smtp_user.arn,
        aws_ssm_parameter.ses_smtp_password.arn,
      ]
    }]
  })
}

resource "aws_iam_instance_profile" "ec2_instance" {
  name = "${var.project}-ec2-profile"
  role = aws_iam_role.ec2_instance.name
}

# ─── Security Group ───────────────────────────────────────────────────────────

resource "aws_security_group" "app" {
  name        = "${var.project}-app-sg"
  description = "Ingestor app security group"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.ssh_allowed_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name    = "${var.project}-app-sg"
    Project = var.project
  }
}

# ─── SSH Key Pair ─────────────────────────────────────────────────────────────

resource "tls_private_key" "deployer" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "aws_key_pair" "deployer" {
  key_name   = "${var.project}-deployer"
  public_key = tls_private_key.deployer.public_key_openssh
}

# ─── AMI ──────────────────────────────────────────────────────────────────────

data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["amzn2-ami-hvm-*-x86_64-gp2"]
  }
}

# ─── EC2 Instance ─────────────────────────────────────────────────────────────

resource "aws_instance" "app" {
  ami           = data.aws_ami.amazon_linux.id
  instance_type = var.instance_type
  key_name      = aws_key_pair.deployer.key_name
  vpc_security_group_ids = [aws_security_group.app.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2_instance.name

  user_data = <<-EOF
              #!/bin/bash
              yum update -y
              yum install -y docker git
              service docker start
              usermod -aG docker ec2-user
              EOF

  tags = {
    Name    = "${var.project}-app"
    Project = var.project
  }
}

# ─── EBS Volume ───────────────────────────────────────────────────────────────

resource "aws_ebs_volume" "postgres_data" {
  availability_zone = aws_instance.app.availability_zone
  size              = 20
  type              = "gp3"
  encrypted         = true

  tags = {
    Name    = "${var.project}-postgres-data"
    Project = var.project
  }
}

resource "aws_volume_attachment" "postgres_data" {
  device_name = "/dev/sdf"
  volume_id   = aws_ebs_volume.postgres_data.id
  instance_id = aws_instance.app.id
}

# ─── Monitoring EBS Volumes ──────────────────────────────────────────────────
# Cloud-parity counterpart of the named Docker volumes in docker-compose.yml
# and the /mnt/ebs/<svc> bind mounts in deployment/aws-mvp/docker-compose.yml.
# Each volume backs one monitoring tool's data dir. You must also format and
# mount each at /mnt/ebs/<svc> on the instance (extend user_data / bootstrap).
# Device names start at /dev/sdg — /dev/sdf is taken by PostgreSQL.

resource "aws_ebs_volume" "prometheus_data" {
  availability_zone = aws_instance.app.availability_zone
  size              = 20
  type              = "gp3"
  encrypted         = true

  tags = {
    Name    = "${var.project}-prometheus-data"
    Project = var.project
  }
}

resource "aws_volume_attachment" "prometheus_data" {
  device_name = "/dev/sdg"
  volume_id   = aws_ebs_volume.prometheus_data.id
  instance_id = aws_instance.app.id
}

resource "aws_ebs_volume" "grafana_data" {
  availability_zone = aws_instance.app.availability_zone
  size              = 10
  type              = "gp3"
  encrypted         = true

  tags = {
    Name    = "${var.project}-grafana-data"
    Project = var.project
  }
}

resource "aws_volume_attachment" "grafana_data" {
  device_name = "/dev/sdh"
  volume_id   = aws_ebs_volume.grafana_data.id
  instance_id = aws_instance.app.id
}

resource "aws_ebs_volume" "loki_data" {
  availability_zone = aws_instance.app.availability_zone
  size              = 20
  type              = "gp3"
  encrypted         = true

  tags = {
    Name    = "${var.project}-loki-data"
    Project = var.project
  }
}

resource "aws_volume_attachment" "loki_data" {
  device_name = "/dev/sdi"
  volume_id   = aws_ebs_volume.loki_data.id
  instance_id = aws_instance.app.id
}

resource "aws_ebs_volume" "promtail_data" {
  availability_zone = aws_instance.app.availability_zone
  size              = 5
  type              = "gp3"
  encrypted         = true

  tags = {
    Name    = "${var.project}-promtail-data"
    Project = var.project
  }
}

resource "aws_volume_attachment" "promtail_data" {
  device_name = "/dev/sdj"
  volume_id   = aws_ebs_volume.promtail_data.id
  instance_id = aws_instance.app.id
}

resource "aws_ebs_volume" "tempo_data" {
  availability_zone = aws_instance.app.availability_zone
  size              = 10
  type              = "gp3"
  encrypted         = true

  tags = {
    Name    = "${var.project}-tempo-data"
    Project = var.project
  }
}

resource "aws_volume_attachment" "tempo_data" {
  device_name = "/dev/sdk"
  volume_id   = aws_ebs_volume.tempo_data.id
  instance_id = aws_instance.app.id
}

resource "aws_ebs_volume" "alertmanager_data" {
  availability_zone = aws_instance.app.availability_zone
  size              = 5
  type              = "gp3"
  encrypted         = true

  tags = {
    Name    = "${var.project}-alertmanager-data"
    Project = var.project
  }
}

resource "aws_volume_attachment" "alertmanager_data" {
  device_name = "/dev/sdl"
  volume_id   = aws_ebs_volume.alertmanager_data.id
  instance_id = aws_instance.app.id
}

resource "aws_ebs_volume" "mailpit_data" {
  availability_zone = aws_instance.app.availability_zone
  size              = 5
  type              = "gp3"
  encrypted         = true

  tags = {
    Name    = "${var.project}-mailpit-data"
    Project = var.project
  }
}

resource "aws_volume_attachment" "mailpit_data" {
  device_name = "/dev/sdm"
  volume_id   = aws_ebs_volume.mailpit_data.id
  instance_id = aws_instance.app.id
}

# ─── SES ──────────────────────────────────────────────────────────────────────

resource "aws_ses_email_identity" "sender" {
  email = var.ses_sender_email
}

# ─── SSM Parameters ───────────────────────────────────────────────────────────

resource "aws_ssm_parameter" "ses_smtp_user" {
  name        = "/api-observatory/${var.project}/runtime/ses/ses_smtp_user"
  description = "SES SMTP username (operator-populated)"
  type        = "SecureString"
  value       = "CHANGE_ME"

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "ses_smtp_password" {
  name        = "/api-observatory/${var.project}/runtime/ses/ses_smtp_password"
  description = "SES SMTP password (operator-populated)"
  type        = "SecureString"
  value       = "CHANGE_ME"

  lifecycle {
    ignore_changes = [value]
  }
}
