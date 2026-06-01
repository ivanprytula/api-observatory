# ══════════════════════════════════════════════════════════════════════════════
# Compute Module — Swappable Container Runtime Backends
# ══════════════════════════════════════════════════════════════════════════════
#
# This module supports multiple container runtime backends via the compute_type
# variable:
#   - ecs-fargate: Serverless container runtime (default, low-ops)
#   - ecs-ec2: ECS with EC2 instances (cost-optimized)
#   - eks: Kubernetes (full portability, higher ops burden)
#
# All backends expose the same output interface (cluster_id, cluster_arn, etc.),
# allowing seamless switching without changing the calling module code.
#
# ══════════════════════════════════════════════════════════════════════════════

# ── Shared: CloudWatch Log Groups ─────────────────────────────────────────────
# One log group per service
resource "aws_cloudwatch_log_group" "ingestor" {
  count             = contains(["ecs-fargate", "ecs-ec2"], var.compute_type) ? 1 : 0
  name              = "/ecs/${var.project}/${var.environment}/ingestor"
  retention_in_days = var.log_retention_days
  tags              = { Service = "ingestor" }
}

resource "aws_cloudwatch_log_group" "processor" {
  count             = contains(["ecs-fargate", "ecs-ec2"], var.compute_type) ? 1 : 0
  name              = "/ecs/${var.project}/${var.environment}/processor"
  retention_in_days = var.log_retention_days
  tags              = { Service = "processor" }
}

# ── Shared: IAM Roles (ECS Task Execution + Task) ──────────────────────────────
locals {
  msk_topic_base_arn = var.msk_cluster_arn != "" ? replace(var.msk_cluster_arn, ":cluster/", ":topic/") : ""
  msk_group_base_arn = var.msk_cluster_arn != "" ? replace(var.msk_cluster_arn, ":cluster/", ":group/") : ""
  msk_topic_arns     = var.msk_cluster_arn == "" ? [] : (
    length(var.kafka_topic_names) > 0
    ? [for topic in var.kafka_topic_names : "${local.msk_topic_base_arn}/${topic}"]
    : ["${local.msk_topic_base_arn}/*"]
  )
}

resource "aws_iam_role" "ecs_task_execution" {
  count = contains(["ecs-fargate", "ecs-ec2"], var.compute_type) ? 1 : 0
  name  = "${var.project}-${var.environment}-ecs-task-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution_managed" {
  count      = contains(["ecs-fargate", "ecs-ec2"], var.compute_type) ? 1 : 0
  role       = aws_iam_role.ecs_task_execution[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "ecs_task_execution_secrets" {
  count = contains(["ecs-fargate", "ecs-ec2"], var.compute_type) ? 1 : 0
  name  = "read-app-secrets"
  role  = aws_iam_role.ecs_task_execution[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue", "ssm:GetParameters"]
      Resource = ["arn:aws:secretsmanager:${var.aws_region}:*:secret:${var.project}/${var.environment}/*"]
    }]
  })
}

resource "aws_iam_role" "ecs_task" {
  count = contains(["ecs-fargate", "ecs-ec2"], var.compute_type) ? 1 : 0
  name  = "${var.project}-${var.environment}-ecs-task"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "ecs_task_msk" {
  count = contains(["ecs-fargate", "ecs-ec2"], var.compute_type) && var.msk_cluster_arn != "" ? 1 : 0
  name  = "msk-produce-consume"
  role  = aws_iam_role.ecs_task[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "kafka-cluster:Connect",
        "kafka-cluster:DescribeCluster",
        "kafka-cluster:DescribeTopic",
        "kafka-cluster:WriteData",
        "kafka-cluster:ReadData",
        "kafka-cluster:AlterGroup",
        "kafka-cluster:DescribeGroup",
      ]
      Resource = concat([var.msk_cluster_arn], local.msk_topic_arns, ["${local.msk_group_base_arn}/*"])
    }]
  })
}

# ── ECS: ALB (Fargate + EC2) ───────────────────────────────────────────────────
resource "aws_lb" "main" {
  count              = contains(["ecs-fargate", "ecs-ec2"], var.compute_type) ? 1 : 0
  name               = "${var.project}-${var.environment}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.sg_alb_id]
  subnets            = var.public_subnet_ids

  enable_deletion_protection = var.environment == "prod"

  access_logs {
    bucket  = var.alb_access_log_bucket
    prefix  = "${var.project}-${var.environment}-alb"
    enabled = var.alb_access_log_bucket != ""
  }

  tags = { Name = "${var.project}-${var.environment}-alb" }
}

resource "aws_lb_target_group" "ingestor" {
  count        = contains(["ecs-fargate", "ecs-ec2"], var.compute_type) ? 1 : 0
  name         = "${var.project}-${var.environment}-ingestor"
  port         = var.app_port
  protocol     = "HTTP"
  vpc_id       = var.vpc_id
  target_type  = var.compute_type == "ecs-fargate" ? "ip" : "instance"

  health_check {
    path                = "/health"
    protocol            = "HTTP"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    matcher             = "200"
  }

  deregistration_delay = 30

  tags = { Service = "ingestor" }
}

resource "aws_lb_listener" "http_redirect" {
  count             = contains(["ecs-fargate", "ecs-ec2"], var.compute_type) ? 1 : 0
  load_balancer_arn = aws_lb.main[0].arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

resource "aws_lb_listener" "https" {
  count             = contains(["ecs-fargate", "ecs-ec2"], var.compute_type) ? 1 : 0
  load_balancer_arn = aws_lb.main[0].arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.acm_certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.ingestor[0].arn
  }
}

# ══════════════════════════════════════════════════════════════════════════════
# BACKEND 1: ECS FARGATE (Serverless)
# ══════════════════════════════════════════════════════════════════════════════

resource "aws_ecs_cluster" "main" {
  count = var.compute_type == "ecs-fargate" ? 1 : 0
  name  = "${var.project}-${var.environment}"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = { Name = "${var.project}-${var.environment}-ecs" }
}

resource "aws_ecs_cluster_capacity_providers" "fargate" {
  count              = var.compute_type == "ecs-fargate" ? 1 : 0
  cluster_name       = aws_ecs_cluster.main[0].name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    base              = 1
    weight            = 1
    capacity_provider = var.environment == "prod" ? "FARGATE" : "FARGATE_SPOT"
  }
}

resource "aws_ecs_task_definition" "ingestor_fargate" {
  count                    = var.compute_type == "ecs-fargate" ? 1 : 0
  family                   = "${var.project}-${var.environment}-ingestor"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.ingestor_cpu
  memory                   = var.ingestor_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution[0].arn
  task_role_arn            = aws_iam_role.ecs_task[0].arn

  container_definitions = jsonencode([{
    name      = "ingestor"
    image     = "${var.ecr_repository_url_ingestor}:${var.image_tag}"
    essential = true

    portMappings = [{
      containerPort = var.app_port
      protocol      = "tcp"
    }]

    secrets = [
      {
        name      = "DATABASE_URL"
        valueFrom = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:${var.project}/${var.environment}/database-url"
      },
      {
        name      = "REDIS_URL"
        valueFrom = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:${var.project}/${var.environment}/redis-url"
      },
    ]

    environment = [
      { name = "LOG_LEVEL", value = var.environment == "prod" ? "INFO" : "DEBUG" },
      { name = "DB_ECHO", value = "false" },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.ingestor[0].name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
      }
    }

    readonlyRootFilesystem = true
    user                   = "1000:1000"
    stopTimeout            = 30

    healthCheck = {
      command     = ["CMD-SHELL", "curl -sf http://localhost:${var.app_port}/health || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 15
    }
  }])

  tags = { Service = "ingestor" }
}

# ── ECS: Processor Task Definition (port 8002) ────────────────────────────────
resource "aws_ecs_task_definition" "processor_fargate" {
  count                    = var.compute_type == "ecs-fargate" ? 1 : 0
  family                   = "${var.project}-${var.environment}-processor"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.processor_cpu
  memory                   = var.processor_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution[0].arn
  task_role_arn            = aws_iam_role.ecs_task[0].arn

  container_definitions = jsonencode([{
    name      = "processor"
    image     = "${var.ecr_repository_url_processor}:${var.image_tag}"
    essential = true

    portMappings = [{
      containerPort = 8002
      protocol      = "tcp"
    }]

    secrets = [
      {
        name      = "KAFKA_BOOTSTRAP_SERVERS"
        valueFrom = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:${var.project}/${var.environment}/kafka-bootstrap-servers"
      },
      {
        name      = "DATABASE_URL"
        valueFrom = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:${var.project}/${var.environment}/database-url"
      },
    ]

    environment = [
      { name = "LOG_LEVEL", value = var.environment == "prod" ? "INFO" : "DEBUG" },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.processor[0].name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
      }
    }

    readonlyRootFilesystem = true
    user                   = "1000:1000"
    stopTimeout            = 30

    healthCheck = {
      command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8002/health', timeout=5)\""]
      interval    = 30
      timeout     = 10
      retries     = 3
      startPeriod = 30
    }
  }])

  tags = { Service = "processor" }
}

resource "aws_ecs_service" "processor_fargate" {
  count           = var.compute_type == "ecs-fargate" ? 1 : 0
  name            = "processor"
  cluster         = aws_ecs_cluster.main[0].id
  task_definition = aws_ecs_task_definition.processor_fargate[0].arn
  desired_count   = var.processor_desired_count

  capacity_provider_strategy {
    capacity_provider = var.environment == "prod" ? "FARGATE" : "FARGATE_SPOT"
    weight            = 1
    base              = 1
  }

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.sg_app_id]
    assign_public_ip = false
  }

  deployment_controller {
    type = "ECS"
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }

  tags = { Service = "processor" }
}

resource "aws_ecs_service" "ingestor_fargate" {
  count           = var.compute_type == "ecs-fargate" ? 1 : 0
  name            = "ingestor"
  cluster         = aws_ecs_cluster.main[0].id
  task_definition = aws_ecs_task_definition.ingestor_fargate[0].arn
  desired_count   = var.ingestor_desired_count

  capacity_provider_strategy {
    capacity_provider = var.environment == "prod" ? "FARGATE" : "FARGATE_SPOT"
    weight            = 1
    base              = 1
  }

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.sg_app_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.ingestor[0].arn
    container_name   = "ingestor"
    container_port   = var.app_port
  }

  deployment_controller {
    type = "ECS"
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }

  depends_on = [aws_lb_listener.https]

  tags = { Service = "ingestor" }
}

# ══════════════════════════════════════════════════════════════════════════════
# BACKEND 2: ECS EC2 (Cost-Optimized)
# ══════════════════════════════════════════════════════════════════════════════

# TODO: Implement ECS EC2 backend with launch template, auto-scaling group, and
# cluster capacity provider for EC2. This will allow cost-optimized deployments
# using reserved instances or Spot instances.
#
# See: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-clusters.html

# ══════════════════════════════════════════════════════════════════════════════
# BACKEND 3: EKS (Kubernetes — Full Portability)
# ══════════════════════════════════════════════════════════════════════════════

# TODO: Implement EKS cluster with managed node group. This will enable
# Kubernetes-native deployments and portability across cloud providers.
#
# See: https://docs.aws.amazon.com/eks/latest/userguide/getting-started.html

# ── Data Source ────────────────────────────────────────────────────────────────
data "aws_caller_identity" "current" {}
