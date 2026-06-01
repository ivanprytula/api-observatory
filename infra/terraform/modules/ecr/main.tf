# One ECR repository per service.
# All repos share lifecycle policy: keep last 10 tagged + auto-expire untagged after 7 days.

locals {
  services = var.services

  lifecycle_policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Remove untagged images after 7 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 7
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep last 10 tagged images per repo"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["v", "sha-", "develop", "latest"]
          countType     = "imageCountMoreThan"
          countNumber   = 10
        }
        action = { type = "expire" }
      }
    ]
  })
}

resource "aws_ecr_repository" "services" {
  for_each = toset(local.services)

  name                 = "${var.project}/${each.key}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    # Scan on every push — catches known CVEs before deploy
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = { Service = each.key }
}

resource "aws_ecr_lifecycle_policy" "services" {
  for_each   = aws_ecr_repository.services
  repository = each.value.name
  policy     = local.lifecycle_policy
}
