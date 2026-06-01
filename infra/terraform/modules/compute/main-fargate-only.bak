# ── ECS Cluster ───────────────────────────────────────────────────────────────
resource "aws_ecs_cluster" "main" {
  name = "${var.project}-${var.environment}"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = { Name = "${var.project}-${var.environment}-ecs" }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    base              = 1
    weight            = 1
    capacity_provider = var.environment == "prod" ? "FARGATE" : "FARGATE_SPOT"
  }
}

# ── CloudWatch Log Group ──────────────────────────────────────────────────────
resource "aws_cloudwatch_log_group" "ingestor" {
  name              = "/ecs/${var.project}/${var.environment}/ingestor"
  retention_in_days = var.log_retention_days
  tags              = { Service = "ingestor" }
}

# ── IAM — ECS Task Execution Role ────────────────────────────────────────────
# Used by the ECS agent to pull images from ECR and send logs to CloudWatch.
resource "aws_iam_role" "ecs_task_execution" {
  name = "${var.project}-${var.environment}-ecs-task-execution"

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
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Grant task execution role access to read the DB password secret
resource "aws_iam_role_policy" "ecs_task_execution_secrets" {
  name   = "read-app-secrets"
  role   = aws_iam_role.ecs_task_execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue", "ssm:GetParameters"]
      Resource = ["arn:aws:secretsmanager:${var.aws_region}:*:secret:${var.project}/${var.environment}/*"]
    }]
  })
}

# ── IAM — ECS Task Role ───────────────────────────────────────────────────────
# Runtime permissions for the app code itself (MSK IAM auth, SSM reads, etc.)
resource "aws_iam_role" "ecs_task" {
  name = "${var.project}-${var.environment}-ecs-task"

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
  name   = "msk-produce-consume"
  role   = aws_iam_role.ecs_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "kafka-cluster:Connect",
        "kafka-cluster:AlterCluster",
        "kafka-cluster:DescribeCluster",
        "kafka-cluster:*Topic*",
        "kafka-cluster:WriteData",
        "kafka-cluster:ReadData",
        "kafka-cluster:AlterGroup",
        "kafka-cluster:DescribeGroup",
      ]
      Resource = [
        var.msk_cluster_arn,
        "arn:aws:kafka:${var.aws_region}:*:topic/${var.msk_cluster_arn}/*",
        "arn:aws:kafka:${var.aws_region}:*:group/${var.msk_cluster_arn}/*",
      ]
    }]
  })
}

# ── ALB ───────────────────────────────────────────────────────────────────────
resource "aws_lb" "main" {
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
  name        = "${var.project}-${var.environment}-ingestor"
  port        = var.app_port
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"  # Required for Fargate (awsvpc network mode)

  health_check {
    path                = "/health"
    protocol            = "HTTP"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    matcher             = "200"
  }

  deregistration_delay = 30  # Drain connections quickly for fast deploys

  tags = { Service = "ingestor" }
}

# HTTP → HTTPS redirect
resource "aws_lb_listener" "http_redirect" {
  load_balancer_arn = aws_lb.main.arn
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

# HTTPS listener — routes to ingestor target group
# NOTE: Requires an ACM certificate. Set var.acm_certificate_arn before applying.
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.acm_certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.ingestor.arn
  }
}

# ── ECS Task Definition — Ingestor (Reference Pattern) ───────────────────────
#
# This is the canonical task definition pattern for all Data Zoo services.
# Duplicate this block for processor, ai-gateway, query-api, dashboard.
# Key decisions:
#   - network_mode = "awsvpc": each task gets its own ENI (required for Fargate)
#   - Secrets injected via secretsmanager: never in environment vars in plaintext
#   - readonly_root_filesystem = true: defense-in-depth
#   - Non-root user: runs as uid 1000 (set in Dockerfile)

resource "aws_ecs_task_definition" "ingestor" {
  family                   = "${var.project}-${var.environment}-ingestor"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.ingestor_cpu
  memory                   = var.ingestor_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "ingestor"
    image     = "${var.ecr_repository_url_ingestor}:${var.image_tag}"
    essential = true

    portMappings = [{
      containerPort = var.app_port
      protocol      = "tcp"
    }]

    # Secrets injected at container start from Secrets Manager / SSM.
    # These are NOT visible in the task definition or CloudWatch logs.
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
        "awslogs-group"         = aws_cloudwatch_log_group.ingestor.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
      }
    }

    # Security hardening
    readonlyRootFilesystem = true
    user                   = "1000:1000"

    # Graceful shutdown: 30s drain window matches deregistration_delay
    stopTimeout = 30

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

# ── ECS Service — Ingestor ────────────────────────────────────────────────────
resource "aws_ecs_service" "ingestor" {
  name            = "ingestor"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.ingestor.arn
  desired_count   = var.ingestor_desired_count

  # Fargate Spot in dev (cost); Fargate in prod (reliability)
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
    target_group_arn = aws_lb_target_group.ingestor.arn
    container_name   = "ingestor"
    container_port   = var.app_port
  }

  deployment_controller {
    type = "ECS"  # Rolling update (not CODE_DEPLOY / EXTERNAL)
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true  # Auto-rollback on consecutive failed deployments
  }

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  # Ignore task_definition and desired_count in plan after first deploy
  # (prevents Terraform fighting with auto-scaling or manual rollouts)
  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }

  depends_on = [aws_lb_listener.https]

  tags = { Service = "ingestor" }
}

data "aws_caller_identity" "current" {}
